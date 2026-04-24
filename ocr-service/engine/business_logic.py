import re
import logging
from rapidfuzz import process as fuzz_process, fuzz
from core.constants import KNOWN_FARMS, HUMIDITY_MIN, HUMIDITY_MAX, OVEN_ID_MIN, OVEN_ID_MAX, CALIBER_SIZES, MESES_ES

logger = logging.getLogger("ocr-engine.business")

def normalize_farm_name(raw_name: str) -> str | None:
    if not raw_name:
        return None
    raw_upper = raw_name.upper().strip()

    result = fuzz_process.extractOne(
        raw_upper,
        KNOWN_FARMS,
        scorer=fuzz.WRatio,
        score_cutoff=65
    )
    if result:
        match, score, _ = result
        logger.info(f"[FUZZY-FARM] '{raw_upper}' → '{match}' (score={score:.0f})")
        return match

    logger.warning(f"[FUZZY-FARM] '{raw_upper}' no matcheó ninguna finca (score_cutoff=65)")
    return None

def validate_humidity(humidity_str: str) -> tuple[float | None, str | None]:
    clean = re.sub(r'[^\d.,]', '', humidity_str).replace(',', '.')
    if not clean:
        return None, f"No se pudo parsear el valor de humedad: '{humidity_str}'"

    try:
        value = float(clean)
    except ValueError:
        return None, f"Valor de humedad no numérico: '{humidity_str}'"

    if value < HUMIDITY_MIN or value > HUMIDITY_MAX:
        msg = (
            f"Humedad {value:.1f}% fuera del rango permitido "
            f"({HUMIDITY_MIN}%–{HUMIDITY_MAX}%). "
            "Verificar lectura del secadero y tomar nueva foto (HU-02.01)."
        )
        logger.warning(f"[HUMIDITY-VALIDATION] {msg}")
        return None, msg

    logger.info(f"[HUMIDITY-VALIDATION] {value:.1f}% dentro del rango [{HUMIDITY_MIN}–{HUMIDITY_MAX}%] ✓")
    return value, None

def validate_oven_id(oven_id_str: str) -> tuple[str | None, str | None]:
    try:
        val = int(oven_id_str.strip())
    except (ValueError, AttributeError):
        return None, f"Número de horno no es un entero válido: '{oven_id_str}'"

    if val < OVEN_ID_MIN or val > OVEN_ID_MAX:
        msg = (
            f"Horno Nº{val} fuera del rango válido "
            f"({OVEN_ID_MIN}–{OVEN_ID_MAX}). "
            "Verificar el número de horno y tomar nueva foto."
        )
        logger.warning(f"[OVEN-VALIDATION] {msg}")
        return None, msg

    logger.info(f"[OVEN-VALIDATION] Horno Nº{val} válido ✓")
    return str(val), None

def normalize_caliber(raw_cal: str) -> str | None:
    raw_cal = raw_cal.replace(' ', '').replace('.', '-')

    if re.match(r'^\d+$', raw_cal):
        val = int(raw_cal)
        if val <= 28:    return '28'
        elif val <= 30:  return '28-30'
        elif val <= 32:  return '30-32'
        elif val <= 34:  return '32-34'
        elif val <= 36:  return '34-36'
        else:            return '36+'

    result = fuzz_process.extractOne(
        raw_cal, CALIBER_SIZES,
        scorer=fuzz.QRatio,
        score_cutoff=50
    )
    if result:
        match, score, _ = result
        logger.info(f"[FUZZY-CALIBER] '{raw_cal}' → '{match}' (score={score:.0f})")
        return match

    return None

def _normalize_spaced_text(text: str) -> str:
    result_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue
        tokens = stripped.split()
        single_char = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        if len(tokens) > 2 and single_char / len(tokens) >= 0.5:
            collapsed = re.sub(
                r'(?<![\w:])([A-ZÑÁÉÍÓÚÜa-záéíóú]) (?=[A-ZÑÁÉÍÓÚÜa-záéíóú](?: |$))',
                r'\1',
                stripped
            )
            result_lines.append(collapsed)
        else:
            result_lines.append(line)
    return '\n'.join(result_lines)

def clean_ocr_number_section(sec_text: str, remove_word: str) -> str:
    sec_text = re.sub(f'(?i){remove_word}', '', sec_text)
    sec_text = re.sub(r'[^0-9OIlZSABGT.,\- %]', '', sec_text)
    sec_text = sec_text.upper().translate(str.maketrans('OILZSABGT', '011254867'))
    return sec_text.strip()

def extract_date(raw_text: str) -> str | None:
    m = re.search(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', raw_text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        if len(year) == 2:
            year = f"20{year}"
        return f"{day.zfill(2)}/{month.zfill(2)}/{year}"

    m = re.search(
        r'(\d{1,2})\s+(?:de\s+)?(' + '|'.join(MESES_ES.keys()) + r')\s+(?:de\s+)?(\d{2,4})',
        raw_text, re.IGNORECASE
    )
    if m:
        day = m.group(1).zfill(2)
        month = MESES_ES.get(m.group(2).lower(), '??')
        year = m.group(3)
        if len(year) == 2:
            year = f"20{year}"
        return f"{day}/{month}/{year}"

    return None

def _truncate_at_field_keyword(value: str) -> str:
    FIELD_KEYS = ['FINCA', 'FECHA', 'COSECHA', 'HORNO', 'PESO', 'CALIBRE']
    words = value.split()
    result = []
    for word in words:
        word_alpha = re.sub(r'[^A-Za-z]', '', word).upper()
        if len(word_alpha) >= 4:
            match = fuzz_process.extractOne(
                word_alpha, FIELD_KEYS,
                scorer=fuzz.QRatio,
                score_cutoff=65
            )
            if match:
                logger.debug(f"[TRUNCATE] Cortando en '{word}' (\u2248 {match[0]}, score={match[1]:.0f})")
                break
        result.append(word)
    return ' '.join(result).strip()

def _find_harvest_type_fuzzy(raw_text: str) -> str | None:
    if re.search(r'(?i)maquin|maquil|mecanic|mecan[ií]', raw_text):
        return 'mecanica'
    if re.search(r'(?i)\bmanual\b|\bmanua\b', raw_text):
        return 'manual'

    HARVEST_MAP = {
        'MAQUINA': 'mecanica',
        'MECANICA': 'mecanica',
        'MANUAL':   'manual',
    }
    tokens = re.findall(r'[A-Za-z0-9]{2,}', raw_text)
    candidates = list(tokens) + [''.join(tokens[i:i+2]) for i in range(len(tokens) - 1)]

    for candidate in candidates:
        c_alpha = re.sub(r'[0-9]', '', candidate).upper()
        if len(c_alpha) < 3:
            continue
        for target, harvest_val in HARVEST_MAP.items():
            score = fuzz.partial_ratio(c_alpha, target)
            if score >= 72:
                logger.info(
                    f"[HARVEST-FUZZY] '{c_alpha}' \u2248 '{target}' "
                    f"(partial_ratio={score}) -> {harvest_val}"
                )
                return harvest_val
    return None
