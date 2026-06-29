import re
import logging
from core.schemas import RemitoData, OvenData, CaliberData
from core.constants import CONFIDENCE_WARN_THRESHOLD, HUMIDITY_MAX
from engine.vision import preprocess_document, preprocess_display, preprocess_handwritten, load_and_correct
from engine.extraction import extract_text_document, _score_result
from engine.business_logic import (
    _normalize_spaced_text, normalize_farm_name, _truncate_at_field_keyword,
    _find_harvest_type_fuzzy, extract_date, validate_oven_id, validate_humidity,
    clean_ocr_number_section, normalize_caliber
)

logger = logging.getLogger("ocr-engine.pipeline")


def _has_remito_keywords(text: str) -> bool:
    """
    Devuelve True si el texto contiene al menos una palabra clave de dominio.
    Se usa como criterio de desempate en el cascade: si el ganador por score
    no tiene ninguna keyword, el otro pipeline gana por contexto.
    """
    DOMAIN_KW = re.compile(
        r'(?i)\b(finca|cosecha|fecha|horno|calibr|peso|remito|humedad|destino|producto)\b'
    )
    return bool(DOMAIN_KW.search(text))


def _extract_best_from_paper(image_path: str) -> tuple[str, float]:
    """
    Estrategia de doble pipeline para documentos con texto impreso en papel
    (remito, calibre).

    Optimización: la imagen se carga y corrige (EXIF + perspectiva) UNA sola
    vez con load_and_correct() y se pasa como array a ambas etapas, evitando
    doble I/O y doble ejecución de _correct_perspective.

    Selección en 2 pasos:
      1. Score ponderado (_score_result: 60% confianza + 40% densidad de palabras).
      2. Desempate por keywords de dominio: si el ganador por score NO contiene
         ninguna keyword del formulario (finca, cosecha, fecha...), el otro pipeline
         gana automáticamente. Esto previene el caso donde el OCR produce texto
         basura con alto score de densidad pero sin campos útiles.

    Etapa 1 (texto impreso):
        preprocess_document (CLAHE + umbral adaptativo blockSize=41)
        + Tesseract PSM 4 y PSM 6 siempre, PSM 11 si conf < 70%.
        Optimizada para texto negro impreso, rápida (~2-4s).

    Etapa 2 (texto manuscrito):
        preprocess_handwritten (CLAHE clipLimit=3 + umbral blockSize=15)
        + Tesseract PSM 4 y PSM 6 siempre, PSM 11 si conf < 70%.
        Mejor para tinta de color (violeta/azul), formularios con campos
        alineados de forma variable y texto en papel arrugado (~2-4s).

    Total esperado: ~4-10s según complejidad de la imagen.
    """
    # ── Pre-carga única: EXIF + perspectiva (evita doble trabajo en cascade) ─
    base_img = load_and_correct(image_path)

    # ── Etapa 1: pipeline impreso ──────────────────────────────────────────────
    doc_img = preprocess_document(base_img)
    doc_text, doc_conf = extract_text_document(doc_img)
    doc_score = _score_result(doc_text, doc_conf)
    doc_has_kw = _has_remito_keywords(doc_text)
    logger.info(f"[CASCADE-1] Impreso: conf={doc_conf:.1f}% | score={doc_score:.1f} | kw={doc_has_kw}")

    # ── Etapa 2: pipeline manuscrito (siempre) ─────────────────────────────────
    hw_img = preprocess_handwritten(base_img)
    hw_text, hw_conf = extract_text_document(hw_img)
    hw_score = _score_result(hw_text, hw_conf)
    hw_has_kw = _has_remito_keywords(hw_text)
    logger.info(f"[CASCADE-2] Manuscrito: conf={hw_conf:.1f}% | score={hw_score:.1f} | kw={hw_has_kw}")

    # ── Selección: score + desempate por keywords ──────────────────────────────
    # Caso 1: solo uno tiene keywords → ese gana sin importar el score
    if doc_has_kw and not hw_has_kw:
        logger.info(f"[CASCADE] Impreso ganó por keywords exclusivas")
        return doc_text, doc_conf
    if hw_has_kw and not doc_has_kw:
        logger.info(f"[CASCADE] Manuscrito ganó por keywords exclusivas")
        return hw_text, hw_conf

    # Caso 2: ambos tienen keywords (o ninguno) → elegir por score
    if hw_score > doc_score:
        logger.info(f"[CASCADE] Manuscrito ganó (score {hw_score:.1f} > {doc_score:.1f})")
        return hw_text, hw_conf

    logger.info(f"[CASCADE] Impreso ganó (score {doc_score:.1f} >= {hw_score:.1f})")
    return doc_text, doc_conf



def process_remito_image(image_path: str) -> RemitoData:
    raw_text, confidence = _extract_best_from_paper(image_path)

    logger.info(f"[REMITO] confidence={confidence:.1f}% | raw='{raw_text}'")

    raw_text_norm = _normalize_spaced_text(raw_text)
    if raw_text_norm != raw_text:
        logger.info(f"[REMITO] texto normalizado: '{raw_text_norm[:120]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD

    FIELD_BOUNDARY = r'(?=\r|\n|fecha|cosecha|horno|peso|calibre|$)'
    # Keyword FINCA tolerante a:
    #   - letras faltantes al final: 'Finc', 'Fin'
    #   - sustitución OCR c→u: 'Fiuca', 'Fiuca'
    #   - espaciado entre letras: 'F i n c a' (ya resuelto por _normalize_spaced_text)
    FINCA_KW = r'f(?:\s*[i1]\s*[nu]\s*[ck](?:\s*a)?|\s*[i1]\s*n\s*c\s*a?)'

    farm_name = None

    # ── Estrategia 1: buscar keyword 'Finca' (y variantes OCR) ───────────────
    for text_candidate in [raw_text_norm, raw_text]:
        farm_sec = re.search(
            rf'(?i){FINCA_KW}[:\s]*(.*?){FIELD_BOUNDARY}',
            text_candidate
        )
        if farm_sec:
            # Limitar a 3 palabras: el OCR puede duplicar el nombre (ej: "La Cabañi La
            # Caboña" en lugar de "La Cabaña"), generando empates falsos en el matcher.
            captured = farm_sec.group(1).strip()
            raw_farm = ' '.join(captured.split()[:3])[:60].upper()
            raw_farm = raw_farm.translate(str.maketrans('0123456789', 'OLZSASGTBG'))
            cleaned = re.sub(r'[^A-Z\sÑÁÉÍÓÚÜ]', '', raw_farm).strip()
            logger.info(f"[FINCA-KW] candidato tras keyword: '{cleaned}'")
            farm_name = normalize_farm_name(cleaned)
            if farm_name:
                break

    # ── Estrategia 2: fallback por primer ':' del texto ───────────────────────
    if not farm_name:
        logger.info("[FINCA-COLON] Buscando finca por primer ':' del texto...")
        first_colon = raw_text_norm.find(':')
        if first_colon != -1:
            after_colon = raw_text_norm[first_colon + 1:].strip()
            truncated = _truncate_at_field_keyword(after_colon)
            if truncated:
                # Limitar a 3 palabras por la misma razón que en FINCA-KW
                raw_farm = ' '.join(truncated.split()[:3])[:60].upper()
                raw_farm = raw_farm.translate(str.maketrans('0123456789', 'OLZSASGTBG'))
                cleaned = re.sub(r'[^A-Z\sÑÁÉÍÓÚÜ]', '', raw_farm).strip()
                logger.info(f"[FINCA-COLON] candidato: '{cleaned}'")
                farm_name = normalize_farm_name(cleaned)

    # ── Estrategia 3: escanear líneas buscando nombre de finca conocida ───────
    # Cubre el caso donde no hay keyword 'Finca' en el texto (ej. baja confianza
    # OCR que omite la etiqueta del campo pero lee el valor correctamente).
    if not farm_name:
        logger.info("[FINCA-LINE] Buscando finca por scan de líneas...")
        for line in raw_text_norm.split('\n'):
            line_clean = line.strip()
            if not line_clean:
                continue
            # Saltar líneas que son claramente campos-etiqueta conocidos
            if re.match(r'(?i)^(remito|fecha|cosecha|horno|peso|calibre|producto|cantidad|destino|firma)', line_clean):
                continue
            raw_farm = ' '.join(line_clean.split()[:3])[:60].upper()
            raw_farm = raw_farm.translate(str.maketrans('0123456789', 'OLZSASGTBG'))
            cleaned = re.sub(r'[^A-Z\sÑÁÉÍÓÚÜ]', '', raw_farm).strip()
            if len(cleaned) < 3:
                continue
            candidate = normalize_farm_name(cleaned)
            if candidate:
                logger.info(f"[FINCA-LINE] Finca encontrada en línea: '{candidate}'")
                farm_name = candidate
                break

    # ── Extracción de tipo de cosecha y fecha ─────────────────────────────────
    # Se intenta sobre el texto normalizado primero, y raw como fallback.
    harvest_type = _find_harvest_type_fuzzy(raw_text_norm) or _find_harvest_type_fuzzy(raw_text)
    date = extract_date(raw_text_norm) or extract_date(raw_text)

    return RemitoData(
        raw_text=raw_text,
        farm_name=farm_name,
        harvest_type=harvest_type,
        date=date,
        confidence=confidence,
        confidence_alert=confidence_alert,
    )

def process_oven_image(image_path: str) -> OvenData:
    processed = preprocess_display(image_path)
    raw_text, confidence = extract_text_document(processed)

    logger.info(f"[OVEN] confidence={confidence:.1f}% | raw='{raw_text[:80]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD
    errors: list[str] = []

    oven_id = None
    # Permite espacios o saltos de línea entre dígitos: Tesseract a veces lee "1 \n 0"
    # en lugar de "10". El lookahead negativo evita que se fusione con la humedad (ej: 5.1%)
    # limitando la captura si el siguiente número tiene decimales o signo %.
    oven_sec = re.search(r'(?i)ho?r[nh]o?[^\d]*(\d[\s\.]*\d?)(?!\s*[\.,]\s*\d|\s*%)', raw_text)
    if not oven_sec:
        oven_sec = re.search(r'(?i)h[o0]r[^\d]*(\d[\s\.]*\d?)(?!\s*[\.,]\s*\d|\s*%)', raw_text)
    if oven_sec:
        raw_oven = re.sub(r'[\s\.]', '', oven_sec.group(1))  # "1 \n 0" → "10"
        oven_id, oven_err = validate_oven_id(raw_oven)
        if oven_err:
            errors.append(oven_err)
    else:
        errors.append("No se detectó el número de horno en la imagen.")

    humidity = None
    hum_sec = re.search(r'(?i)[h]?[uv][a-záéíóú\s]*d[aá]d[^\d]*(\d+[.,]?\d*\s*%?)', raw_text)
    if not hum_sec:
        hum_sec = re.search(r'(?i)hu[a-z\s]*?(\d+[.,]\d+\s*%?)', raw_text)

    if hum_sec:
        dirty_h = hum_sec.group(1)
        clean_h = clean_ocr_number_section(dirty_h, "edad")
        h_match = re.search(r'(\d+[.,]?\d*)', clean_h)
        if h_match:
            hum_str = h_match.group(1).replace(',', '.')
            try:
                humidity_raw = float(hum_str)
                if humidity_raw > HUMIDITY_MAX * 10:
                    humidity_raw = humidity_raw / 10

                hum_val, hum_err = validate_humidity(str(humidity_raw))
                if hum_err:
                    errors.append(hum_err)
                else:
                    humidity = f"{hum_val:.1f}%"
            except ValueError:
                errors.append(f"No se pudo convertir la humedad a número: '{hum_str}'")
    else:
        errors.append("No se detectó el valor de humedad en la imagen.")

    return OvenData(
        raw_text=raw_text,
        oven_id=oven_id,
        humidity=humidity,
        confidence=confidence,
        confidence_alert=confidence_alert,
        errors=errors,
    )

def process_caliber_image(image_path: str) -> CaliberData:
    raw_text, confidence = _extract_best_from_paper(image_path)

    logger.info(f"[CALIBER] confidence={confidence:.1f}% | raw='{raw_text[:120]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD

    caliber = None
    cal_sec = re.search(
        r'(?i)c\s*a\s*l[a-z\s]*:?\s*[\r\n\s]*(\d+(?:\s*[\-\.]\s*\d+)?)',
        raw_text, re.DOTALL
    )
    if cal_sec:
        raw_cal = cal_sec.group(1).replace(' ', '').replace('.', '-')
        caliber = normalize_caliber(raw_cal)
        logger.info(f"[CALIBER] Extraído: '{raw_cal}' -> normalizado: '{caliber}'")
    else:
        logger.warning("[CALIBER] No se encontró el calibre en el texto.")

    weight = None
    peso_sec = re.search(
        r'(?i)peso\s*:?\s*[\r\n\s]*(\d+[.,]?\d*)',
        raw_text, re.DOTALL
    )
    if peso_sec:
        w_str = peso_sec.group(1).replace(',', '.')
        try:
            weight = f"{float(w_str):.1f}kg"
            logger.info(f"[CALIBER] Peso extraído: '{weight}'")
        except ValueError:
            logger.warning(f"[CALIBER] No se pudo parsear el peso: '{w_str}'")
    else:
        logger.warning("[CALIBER] No se detectó el peso en el texto.")

    return CaliberData(
        raw_text=raw_text,
        caliber=caliber,
        weight=weight,
        confidence=confidence,
        confidence_alert=confidence_alert,
    )
