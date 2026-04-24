import re
import logging
from core.schemas import RemitoData, OvenData, CaliberData
from core.constants import CONFIDENCE_WARN_THRESHOLD, HUMIDITY_MAX
from engine.vision import preprocess_document, preprocess_display
from engine.extraction import extract_text_document
from engine.business_logic import (
    _normalize_spaced_text, normalize_farm_name, _truncate_at_field_keyword,
    _find_harvest_type_fuzzy, extract_date, validate_oven_id, validate_humidity,
    clean_ocr_number_section, normalize_caliber
)

logger = logging.getLogger("ocr-engine.pipeline")

def process_remito_image(image_path: str) -> RemitoData:
    processed = preprocess_document(image_path)
    raw_text, confidence = extract_text_document(processed)

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
    raw_text, confidence = extract_text_document(processed)

    logger.info(f"[OVEN] confidence={confidence:.1f}% | raw='{raw_text[:80]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD
    errors: list[str] = []

    oven_id = None
    oven_sec = re.search(r'(?i)ho?r[nh]o?[^0-9\n]*(\d+)', raw_text)
    if not oven_sec:
        oven_sec = re.search(r'(?i)h[o0]r.*?(\d+)', raw_text)
    if oven_sec:
        raw_oven = oven_sec.group(1)
        oven_id, oven_err = validate_oven_id(raw_oven)
        if oven_err:
            errors.append(oven_err)
    else:
        errors.append("No se detectó el número de horno en la imagen.")

    humidity = None
    hum_sec = re.search(r'(?i)h[uv][\w\s]*d[aá]d[:\s]*(.*?)(?=\r|\n|$)', raw_text)
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
    processed = preprocess_document(image_path)
    raw_text, confidence = extract_text_document(processed)

    logger.info(f"[CALIBER] confidence={confidence:.1f}% | raw='{raw_text[:80]}'")

    confidence_alert = confidence < CONFIDENCE_WARN_THRESHOLD

    caliber = None
    cal_sec = re.search(r'(?i)c\s*a\s*l[a-z\s]*(.*?)(?=\r|\n|peso|$)', raw_text)
    if cal_sec:
        dirty_c = cal_sec.group(1)
        clean_c = clean_ocr_number_section(dirty_c, "ibre")
        c_match = re.search(r'(\d+(?:\s*[\.\-]\s*\d+)?)', clean_c)
        if c_match:
            raw_cal = c_match.group(1).replace('.', '-')
            caliber = normalize_caliber(raw_cal)

    weight = None
    peso_sec = re.search(r'(?i)peso[a-z:=;\s\-,\.]*([\d]+[.,]?[\d]*)', raw_text)
    if peso_sec:
        w_str = peso_sec.group(1).replace(',', '.')
        try:
            weight = f"{float(w_str):.1f}kg"
        except ValueError:
            pass

    return CaliberData(
        raw_text=raw_text,
        caliber=caliber,
        weight=weight,
        confidence=confidence,
        confidence_alert=confidence_alert,
    )
