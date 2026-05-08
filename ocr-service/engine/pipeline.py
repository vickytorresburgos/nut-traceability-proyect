import re
import logging
from core.schemas import RemitoData, OvenData, CaliberData
from core.constants import CONFIDENCE_WARN_THRESHOLD, HUMIDITY_MAX
from engine.vision import preprocess_document, preprocess_display, preprocess_handwritten
from engine.extraction import extract_text_document, extract_text_with_fallback, _score_result, _run_easyocr_safe
from engine.business_logic import (
    _normalize_spaced_text, normalize_farm_name, _truncate_at_field_keyword,
    _find_harvest_type_fuzzy, extract_date, validate_oven_id, validate_humidity,
    clean_ocr_number_section, normalize_caliber
)

logger = logging.getLogger("ocr-engine.pipeline")


def _extract_best_from_paper(image_path: str) -> tuple[str, float]:
    """
    Estrategia en cascada para documentos en papel.
    Cada etapa solo se activa si la anterior no alcanzó la confianza mínima.

    Etapa 1 — RÁPIDA (~2-3s):
        preprocess_document + Tesseract [PSM 4, 6, 11]
        Si conf >= CONFIDENCE_WARN_THRESHOLD (55%): retorna inmediatamente.

    Etapa 2 — MEDIA (~+3s, solo si etapa 1 falló):
        preprocess_handwritten + Tesseract [PSM 4, 6, 11]
        Se queda con el mejor de etapa 1 y 2.

    Etapa 3 — LENTA (~+variable, solo si conf sigue < 50%):
        EasyOCR sobre la imagen que tuvo mayor confianza hasta ahora.
        Solo se activa si el modelo ya está cargado (warmup completo).
    """
    # ── Etapa 1: pipeline rápido (texto impreso) ──────────────────────────
    doc_img = preprocess_document(image_path)
    doc_text, doc_conf = extract_text_document(doc_img)
    logger.info(f"[CASCADE-1] Impreso: conf={doc_conf:.1f}%")

    if doc_conf >= CONFIDENCE_WARN_THRESHOLD:
        logger.info("[CASCADE] Etapa 1 suficiente, saltando manuscrito y EasyOCR.")
        return doc_text, doc_conf

    # ── Etapa 2: pipeline manuscrito (solo si etapa 1 fue insuficiente) ───
    logger.info("[CASCADE-2] Confianza baja, probando pipeline manuscrito...")
    hw_img = preprocess_handwritten(image_path)
    hw_text, hw_conf = extract_text_document(hw_img)
    logger.info(f"[CASCADE-2] Manuscrito: conf={hw_conf:.1f}%")

    # Tomar el mejor entre etapa 1 y 2
    if _score_result(hw_text, hw_conf) > _score_result(doc_text, doc_conf):
        best_text, best_conf, best_img = hw_text, hw_conf, hw_img
        logger.info(f"[CASCADE] Manuscrito ganó: {hw_conf:.1f}% > {doc_conf:.1f}%")
    else:
        best_text, best_conf, best_img = doc_text, doc_conf, doc_img
        logger.info(f"[CASCADE] Impreso ganó: {doc_conf:.1f}% >= {hw_conf:.1f}%")

    # ── Etapa 3: EasyOCR (último recurso, solo si conf sigue siendo baja) ─
    if best_conf < 50.0:
        logger.info(f"[CASCADE-3] Conf={best_conf:.1f}% aún baja, intentando EasyOCR...")
        easy_text, easy_conf = _run_easyocr_safe(best_img)
        if easy_conf > best_conf:
            logger.info(f"[CASCADE-3] EasyOCR ganó: {easy_conf:.1f}% > {best_conf:.1f}%")
            return easy_text, easy_conf
        logger.info(f"[CASCADE-3] EasyOCR no mejoró ({easy_conf:.1f}% <= {best_conf:.1f}%)")

    return best_text, best_conf


def process_remito_image(image_path: str) -> RemitoData:
    raw_text, confidence = _extract_best_from_paper(image_path)

    logger.info(f"[REMITO] confidence={confidence:.1f}% | raw='{raw_text}'")

    raw_text_norm = _normalize_spaced_text(raw_text)
    if raw_text_norm != raw_text:
        logger.info(f"[REMITO] texto normalizado: '{raw_text_norm[:120]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD

    FIELD_BOUNDARY = r'(?=\r|\n|fecha|cosecha|horno|peso|calibre|$)'
    FINCA_KW = r'f\s*[i1]\s*n\s*c\s*a'

    farm_name = None

    for text_candidate in [raw_text_norm, raw_text]:
        farm_sec = re.search(
            rf'(?i){FINCA_KW}[:\s]*(.*?){FIELD_BOUNDARY}',
            text_candidate
        )
        if farm_sec:
            raw_farm = farm_sec.group(1).strip()[:60].upper()
            raw_farm = raw_farm.translate(str.maketrans('0123456789', 'OLZSASGTBG'))
            cleaned = re.sub(r'[^A-Z\sÑÁÉÍÓÚÜ]', '', raw_farm).strip()
            logger.info(f"[FINCA-KW] candidato tras keyword: '{cleaned}'")
            farm_name = normalize_farm_name(cleaned)
            if farm_name:
                break

    if not farm_name:
        logger.info("[FINCA-COLON] Buscando finca por primer ':' del texto...")
        first_colon = raw_text_norm.find(':')
        if first_colon != -1:
            after_colon = raw_text_norm[first_colon + 1:].strip()
            truncated = _truncate_at_field_keyword(after_colon)
            if truncated:
                raw_farm = truncated[:60].upper()
                raw_farm = raw_farm.translate(str.maketrans('0123456789', 'OLZSASGTBG'))
                cleaned = re.sub(r'[^A-Z\sÑÁÉÍÓÚÜ]', '', raw_farm).strip()
                logger.info(f"[FINCA-COLON] candidato: '{cleaned}'")
                farm_name = normalize_farm_name(cleaned)

    harvest_type = _find_harvest_type_fuzzy(raw_text_norm)
    date = extract_date(raw_text_norm)

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
    raw_text, confidence = extract_text_with_fallback(processed)

    logger.info(f"[OVEN] confidence={confidence:.1f}% | raw='{raw_text[:80]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD
    errors: list[str] = []

    oven_id = None
    oven_sec = re.search(r'(?i)ho?r[nh]o?[^\d]*(\d+)', raw_text)
    if not oven_sec:
        oven_sec = re.search(r'(?i)h[o0]r[^\d]*(\d+)', raw_text)
    if oven_sec:
        raw_oven = oven_sec.group(1)
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
    # Busca 'calibre' (con posibles espacios internos) seguido de ':' y luego
    # el número, permitiendo saltos de línea entre la keyword y el valor.
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
    # Busca 'peso' seguido de ':' y el número, permitiendo saltos de línea.
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
