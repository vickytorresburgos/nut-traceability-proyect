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
        scorer=fuzz.token_sort_ratio,
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

    logger.info(f"[HUMIDITY-VALIDATION] {value:.1f}% dentro del rango [{HUMIDITY_MIN}–{HUMIDITY_MAX}%]")
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

    logger.info(f"[OVEN-VALIDATION] Horno Nº{val} válido")
    return str(val), None

def normalize_caliber(raw_cal: str) -> str | None:
    raw_cal = raw_cal.replace(' ', '').replace('.', '-')

    if re.match(r'^\d+$', raw_cal):
        val = int(raw_cal)
        if val <= 28:    return '28'
        elif val <= 30:  return '28-30'
        elif val <= 32:  return '30-32'
        elif val <= 34:  return '32-34'
        elif val < 36:   return '34-36'   # FIX: val==36 exacto → '36+', no '34-36'
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

def _collapse_spaced_line(line: str) -> str:
    """
    Pre-colapsa líneas donde Tesseract PSM-4 espació cada letra individualmente.

    Cuando el OCR genera 'F i n c a: L a C a b a ñ a', esta función detecta
    que la mayoría de tokens son chars individuales y los une en palabras.
    No modifica líneas con palabras normales de >1 char para no introducir
    errores en texto ya correcto.

    Preserva separadores ':' y '/' adjuntos a las letras.
    """
    stripped = line.strip()
    if not stripped:
        return line
    tokens = stripped.split()
    if len(tokens) < 3:
        return line

    # Contar tokens de 1 caracter alfanumérico (letras y dígitos, incl. acentuados)
    single_char_count = sum(
        1 for t in tokens
        if len(re.sub(r'[^A-Za-z0-9áéíóúüñÁÉÍÓÚÜÑ]', '', t)) == 1
    )
    if single_char_count / len(tokens) < 0.6:
        return line  # línea normal, no modificar

    result = []
    current_word: list[str] = []
    for token in tokens:
        m = re.match(r'^([A-Za-z0-9áéíóúüñÁÉÍÓÚÜÑ]*)([^A-Za-z0-9áéíóúüñÁÉÍÓÚÜÑ]*)', token)
        alpha = m.group(1) if m else token
        suffix = m.group(2) if m else ''

        if len(alpha) == 1:
            current_word.append(alpha)
            if suffix:  # separador ':' cierra la palabra actual
                result.append(''.join(current_word) + suffix)
                current_word = []
        else:
            if current_word:
                result.append(''.join(current_word))
                current_word = []
            result.append(token)
    if current_word:
        result.append(''.join(current_word))

    return ' '.join(result)


def _normalize_spaced_text(text: str) -> str:
    """
    Normaliza artefactos de espaciado del OCR en dos pasadas:

    1. _collapse_spaced_line: detecta líneas donde PSM-4 espació cada letra
       ('F i n c a:') y las colapsa a palabras normales ('Finca:').

    2. Regex de colapso de runs: elimina el espacio entre chars individuales
       consecutivos que quedaron tras la primera pasada (ej: 'L aC a b a ñ a'
       → 'LaCabaña'). El fuzzy matcher de finca tolera el pegado.
    """
    result_lines = []
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue

        # Pasada 1: colapsar líneas completamente espaciadas (PSM-4)
        line_processed = _collapse_spaced_line(stripped)
        tokens = line_processed.split()

        # Pasada 2: colapsar runs residuales de chars individuales
        single_char = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        if len(tokens) > 2 and single_char / len(tokens) >= 0.5:
            collapsed = re.sub(
                r'(?<![\w:])([A-ZÑÁÉÍÓÚÜa-záéíóú]) (?=[A-ZÑÁÉÍÓÚÜa-záéíóú](?: |$))',
                r'\1',
                line_processed
            )
            result_lines.append(collapsed)
        else:
            result_lines.append(line_processed)
    return '\n'.join(result_lines)

def clean_ocr_number_section(sec_text: str, remove_word: str) -> str:
    sec_text = re.sub(f'(?i){remove_word}', '', sec_text)
    sec_text = re.sub(r'[^0-9OIlZSABGT.,\- %]', '', sec_text)
    sec_text = sec_text.upper().translate(str.maketrans('OILZSABGT', '011254867'))
    return sec_text.strip()

# Tabla de sustituciones comunes de Tesseract en dígitos del año
_OCR_DIGIT_FIX = str.maketrans('ZzIiOoSsBbGgTt', '22110055887766')


def _fix_ocr_year(year_str: str) -> str:
    """Corrige sustituciones OCR comunes en el año: Z→2, I→1, O→0, etc."""
    return year_str.translate(_OCR_DIGIT_FIX)


def extract_date(raw_text: str) -> str | None:
    # Paso 0: colapsar espacios entre dígitos que PSM-4 introduce en fechas.
    # '2 0/0 1/2 0 2 4' necesita múltiples pasadas para → '20/01/2024'.
    pre_cleaned = raw_text
    for _ in range(6):  # máx 6 iteraciones para cubrir números de 4 dígitos
        new = re.sub(r'(\d)\s+(\d)', r'\1\2', pre_cleaned)
        if new == pre_cleaned:
            break
        pre_cleaned = new

    # Normalizar sustituciones OCR en letras que parecen dígitos (Z→2, I→1, O→0)
    # Solo en el contexto de posibles años (4 chars alfanuméricos tras separador)
    cleaned = re.sub(
        r'(?<=[/\-\.\s])([A-Za-z0-9]{2,4})(?=[/\-\.\s]|$)',
        lambda m: m.group(0).translate(_OCR_DIGIT_FIX),
        pre_cleaned
    )
    # También al final de línea para años tipo 'Z024'
    cleaned = re.sub(
        r'(20[0-9ZzIiOoSs]{2})(?!\d)',
        lambda m: m.group(0).translate(_OCR_DIGIT_FIX),
        cleaned
    )

    # 1. Patrón con separadores explícitos (soporta años de 2 y 4 dígitos)
    regex1 = r'(?<!\d)(0?[1-9]|[12][0-9]|3[01])[/\-\.\s7lI]+(0?[1-9]|1[0-2])[/\-\.\s7lI]+(20\d{2}|\d{2})(?!\d)'
    # 2. Patrón con separadores opcionales, exige año de 4 dígitos para evitar falsos positivos
    regex2 = r'(?<!\d)(0?[1-9]|[12][0-9]|3[01])[/\-\.\s7lI]*(0?[1-9]|1[0-2])[/\-\.\s7lI]*(20\d{2})(?!\d)'
    # 3. Fallback para años de 2 dígitos sin separadores
    regex3 = r'(?<!\d)(0?[1-9]|[12][0-9]|3[01])[/\-\.\s7lI]*(0?[1-9]|1[0-2])[/\-\.\s7lI]*(\d{2})(?!\d)'

    for text_candidate in [cleaned, raw_text]:
        m = re.search(regex1, text_candidate) or re.search(regex2, text_candidate) or re.search(regex3, text_candidate)
        if m:
            day, month, year = m.group(1), m.group(2), m.group(3)
            year = _fix_ocr_year(year)  # corregir Z024 → 2024
            if len(year) == 2:
                year = f"20{year}"
            if 1 <= int(day) <= 31 and 1 <= int(month) <= 12:
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # Patrón texto: "20 de enero de 2024" / "20 enero 2024"
    for text_candidate in [cleaned, raw_text]:
        m = re.search(
            r'(\d{1,2})\s+(?:de\s+)?(' + '|'.join(MESES_ES.keys()) + r')\s+(?:de\s+)?(\d{2,4})',
            text_candidate, re.IGNORECASE
        )
        if m:
            day = m.group(1).zfill(2)
            month = MESES_ES.get(m.group(2).lower(), '??')
            year = _fix_ocr_year(m.group(3))
            if len(year) == 2:
                year = f"20{year}"
            return f"{year}-{month}-{day}"

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
    if re.search(r'(?i)mecanic|mecan[ií]', raw_text):
        return 'mecanica'
    if re.search(r'(?i)\bmanual\b|\bmanua\b', raw_text):
        return 'manual'

    HARVEST_MAP = {
        'MECANICA': 'mecanica',
        'MANUAL':   'manual',
    }
    tokens = re.findall(r'[A-Za-zÁÉÍÓÚáéíóúÑñ0-9]{2,}', raw_text)
    candidates = list(tokens) + [''.join(tokens[i:i+2]) for i in range(len(tokens) - 1)]

    best_match = None
    best_score = -1

    for candidate in candidates:
        c_alpha = re.sub(r'[0-9]', '', candidate).upper()
        # Eliminar tildes para no perjudicar el score
        c_alpha = c_alpha.translate(str.maketrans('ÁÉÍÓÚ', 'AEIOU'))
        
        if len(c_alpha) < 4:
            continue
            
        result = fuzz_process.extractOne(
            c_alpha, list(HARVEST_MAP.keys()),
            scorer=fuzz.partial_ratio,
            score_cutoff=72
        )
        if result:
            match_str, score, _ = result
            if score > best_score:
                best_score = score
                best_match = HARVEST_MAP[match_str]
                
    if best_match:
        logger.info(f"[HARVEST-FUZZY] Ganador con score {best_score} -> {best_match}")
        return best_match
        
    return None
