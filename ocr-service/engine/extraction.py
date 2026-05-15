import os
import logging
import pytesseract
import numpy as np

# I1 — Apuntar a tessdata_fast para modelos ligeros (~3-5x más rápidos en CPU)
# En el Dockerfile se instala /usr/share/tesseract-ocr/5/tessdata
# tessdata_fast está en ese mismo directorio con los modelos .traineddata fast
TESSDATA_FAST_PATH = os.getenv(
    "TESSDATA_FAST_PATH",
    "/usr/share/tesseract-ocr/5/tessdata"
)

logger = logging.getLogger("ocr-engine.extraction")

# ---------------------------------------------------------------------------
# EasyOCR — dependencia opcional (fallback para manuscrito)
# ---------------------------------------------------------------------------

try:
    import easyocr as _easyocr_lib
    _EASYOCR_AVAILABLE = True
    logger.info("EasyOCR disponible como fallback para texto manuscrito.")
except ImportError:
    _EASYOCR_AVAILABLE = False
    logger.warning(
        "EasyOCR no está instalado. El fallback para manuscrito no estará disponible. "
        "Instalá con: pip install easyocr"
    )

_easyocr_reader = None


def _get_easyocr_reader():
    """Inicialización lazy del lector EasyOCR (carga el modelo la primera vez)."""
    global _easyocr_reader
    if not _EASYOCR_AVAILABLE:
        return None
    if _easyocr_reader is None:
        logger.info("[EASYOCR] Inicializando lector...")
        _easyocr_reader = _easyocr_lib.Reader(['es', 'en'], gpu=False, verbose=False)
        logger.info("[EASYOCR] Lector listo.")
    return _easyocr_reader


def warmup_easyocr() -> None:
    """
    Pre-carga los modelos de EasyOCR durante el startup del servidor.
    Evita que la primera request real experimente el delay de descarga/carga
    de modelos (que puede causar timeout en el cliente).
    Llamar desde el evento @app.on_event('startup') de FastAPI.
    """
    if not _EASYOCR_AVAILABLE:
        logger.info("[EASYOCR-WARMUP] EasyOCR no disponible, se omite warmup.")
        return
    logger.info("[EASYOCR-WARMUP] Pre-cargando modelos en startup...")
    _get_easyocr_reader()
    logger.info("[EASYOCR-WARMUP] Modelos listos. El servicio está listo para recibir requests.")


# ---------------------------------------------------------------------------
# Selector de resultado mejorado
# ---------------------------------------------------------------------------

def _score_result(text: str, conf: float) -> float:
    """
    Puntaje ponderado para elegir el mejor resultado entre múltiples PSMs.
    60% confianza + 40% cantidad de palabras significativas (cap en 20).
    Evita elegir resultados con muchas palabras cortas de baja calidad.
    """
    wc = len([w for w in text.split() if len(w) > 1])
    return (conf * 0.6) + (min(wc, 20) * 2.0)


# ---------------------------------------------------------------------------
# Extracción con Tesseract
# ---------------------------------------------------------------------------

def _run_ocr(image: np.ndarray, psm: int) -> tuple[str, float]:
    # I1: --tessdata-dir apunta a tessdata_fast para inferencia más rápida en CPU
    config = f"--oem 1 --psm {psm} --tessdata-dir {TESSDATA_FAST_PATH}"
    try:
        data = pytesseract.image_to_data(
            image, lang="spa", config=config,
            output_type=pytesseract.Output.DICT
        )
        tokens = []
        valid_confs = []
        last_block = -1
        for i in range(len(data['text'])):
            token = data['text'][i].strip()
            if not token:
                continue
            conf_str = str(data['conf'][i]).lstrip('-')
            conf = int(data['conf'][i]) if conf_str.isdigit() else -1
            if conf < 0:
                continue
            
            valid_confs.append(conf)
            if last_block != -1 and data['block_num'][i] != last_block:
                tokens.append('\n')
            tokens.append(token)
            last_block = data['block_num'][i]
            
        text = ' '.join(tokens).strip()

        avg_conf = round(sum(valid_confs) / len(valid_confs), 2) if valid_confs and text else 0.0

        return text, avg_conf
    except Exception as e:
        logger.warning(f"Tesseract PSM {psm} falló: {e}")
        return "", 0.0


def extract_text_document(image: np.ndarray) -> tuple[str, float]:
    """
    Extrae texto con múltiples PSMs y elige el mejor usando puntaje ponderado.
    PSMs usados: [4, 6, 11].
      - PSM 4:  columna de texto variable (bueno para remitos con campos)
      - PSM 6:  bloque uniforme de texto (el más rápido para texto corrido)
      - PSM 11: texto disperso (bueno para formularios con campos separados)
    """
    best_text, best_conf, best_score = "", 0.0, -1.0
    for psm in [4, 6, 11]:
        text, conf = _run_ocr(image, psm)
        score = _score_result(text, conf)
        logger.debug(f"[PSM {psm}] conf={conf:.1f}% | words={len(text.split())} | score={score:.1f}")
        if score > best_score:
            best_text, best_conf, best_score = text, conf, score

    logger.debug(f"[TESSERACT] Mejor resultado: conf={best_conf:.1f}% | score={best_score:.1f}")
    return best_text, best_conf


# ---------------------------------------------------------------------------
# Fallback con EasyOCR
# ---------------------------------------------------------------------------

def _run_easyocr(image: np.ndarray, timeout_s: float = 60.0) -> tuple[str, float]:
    """Ejecuta EasyOCR con timeout para evitar bloqueos indefinidos.

    Si EasyOCR no responde en `timeout_s` segundos, devuelve vacío
    y el pipeline usa el resultado de Tesseract en su lugar.
    """
    reader = _get_easyocr_reader()
    if reader is None:
        return "", 0.0
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(reader.readtext, image, detail=1, paragraph=False)
            try:
                results = future.result(timeout=timeout_s)
            except FuturesTimeout:
                logger.warning(f"[EASYOCR] Timeout ({timeout_s:.0f}s) — usando resultado de Tesseract.")
                return "", 0.0

        if not results:
            return "", 0.0
        texts = [r[1] for r in results]
        confs = [r[2] * 100 for r in results]  # EasyOCR devuelve 0.0–1.0
        avg_conf = round(sum(confs) / len(confs), 2)
        full_text = ' '.join(texts)
        logger.info(f"[EASYOCR] conf={avg_conf:.1f}% | texto='{full_text[:80]}'")
        return full_text, avg_conf
    except Exception as e:
        logger.warning(f"[EASYOCR] Falló: {e}")
        return "", 0.0



def _run_easyocr_safe(image: np.ndarray) -> tuple[str, float]:
    """
    Versión segura de _run_easyocr para usar en la cascada del pipeline.
    Solo ejecuta EasyOCR si el modelo YA está cargado en memoria (warmup completo).
    Si el lector aún no está listo, devuelve vacío sin bloquear la request.
    Esto evita que la primera request sufra el delay de carga del modelo.
    """
    if not _EASYOCR_AVAILABLE:
        return "", 0.0
    if _easyocr_reader is None:
        logger.info("[EASYOCR-SAFE] Modelo aún no cargado (warmup en progreso), saltando EasyOCR.")
        return "", 0.0
    return _run_easyocr(image)



def extract_text_with_fallback(
    image: np.ndarray,
    confidence_threshold: float = 50.0
) -> tuple[str, float]:
    """
    Extrae texto usando Tesseract. Si la confianza queda por debajo de
    `confidence_threshold`, activa EasyOCR como segunda opinión (solo si el
    modelo ya está cargado en memoria) y devuelve el resultado con mayor
    confianza.

    Usa _run_easyocr_safe para no bloquear la request si EasyOCR aún no
    terminó de cargar o está bajo alta carga — en ese caso responde con
    el resultado de Tesseract sin esperar el timeout de 60s de EasyOCR.

    Args:
        image: Imagen ya preprocesada (numpy array).
        confidence_threshold: Umbral (%) a partir del cual no se activa EasyOCR.

    Returns:
        Tupla (texto, confianza).
    """
    tess_text, tess_conf = extract_text_document(image)

    if tess_conf >= confidence_threshold:
        logger.info(f"[EXTRACT] Tesseract OK (conf={tess_conf:.1f}%), fallback no necesario.")
        return tess_text, tess_conf

    logger.info(
        f"[EXTRACT] Tesseract bajo (conf={tess_conf:.1f}% < {confidence_threshold}%), "
        "activando EasyOCR (safe)..."
    )
    # _run_easyocr_safe no bloquea si el modelo aún no está listo,
    # evitando que la request supere el timeout del proxy (OCR_TIMEOUT).
    easy_text, easy_conf = _run_easyocr_safe(image)

    if easy_conf > tess_conf:
        logger.info(f"[EXTRACT] EasyOCR ganó: {easy_conf:.1f}% > Tesseract {tess_conf:.1f}%")
        return easy_text, easy_conf

    logger.info(f"[EXTRACT] Tesseract ganó: {tess_conf:.1f}% >= EasyOCR {easy_conf:.1f}%")
    return tess_text, tess_conf


# ---------------------------------------------------------------------------
# Extracción numérica (sin cambios)
# ---------------------------------------------------------------------------

def extract_text_numeric(image: np.ndarray, whitelist: str) -> str:
    config = f"--oem 1 --psm 7 --tessdata-dir {TESSDATA_FAST_PATH} -c tessedit_char_whitelist={whitelist}"
    text = pytesseract.image_to_string(image, lang="spa", config=config)
    return text.strip()
