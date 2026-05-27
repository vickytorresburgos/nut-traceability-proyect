import os
import logging
import pytesseract
import numpy as np

TESSDATA_FAST_PATH = os.getenv(
    "TESSDATA_FAST_PATH",
    "/usr/share/tesseract-ocr/5/tessdata"
)

logger = logging.getLogger("ocr-engine.extraction")

def _score_result(text: str, conf: float) -> float:
    """
    Puntaje ponderado para elegir el mejor resultado entre múltiples PSMs.
    60% confianza + 40% cantidad de palabras significativas (cap en 20).
    Evita elegir resultados con muchas palabras cortas de baja calidad.
    """
    wc = len([w for w in text.split() if len(w) > 1])
    return (conf * 0.6) + (min(wc, 20) * 2.0)


def _run_ocr(image: np.ndarray, psm: int) -> tuple[str, float]:
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


def extract_text_numeric(image: np.ndarray, whitelist: str) -> str:
    config = f"--oem 1 --psm 7 --tessdata-dir {TESSDATA_FAST_PATH} -c tessedit_char_whitelist={whitelist}"
    text = pytesseract.image_to_string(image, lang="spa", config=config)
    return text.strip()
