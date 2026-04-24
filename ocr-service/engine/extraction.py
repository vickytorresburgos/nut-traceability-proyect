import logging
import pytesseract
import numpy as np

logger = logging.getLogger("ocr-engine.extraction")

def _run_ocr(image: np.ndarray, psm: int) -> tuple[str, float]:
    config = f"--oem 1 --psm {psm}"
    try:
        data = pytesseract.image_to_data(
            image, lang="spa", config=config,
            output_type=pytesseract.Output.DICT
        )
        tokens = []
        last_block = -1
        for i in range(len(data['text'])):
            token = data['text'][i].strip()
            if not token:
                continue
            conf = int(data['conf'][i]) if str(data['conf'][i]).lstrip('-').isdigit() else -1
            if conf < 0:
                continue
            if last_block != -1 and data['block_num'][i] != last_block:
                tokens.append('\n')
            tokens.append(token)
            last_block = data['block_num'][i]
        text = ' '.join(tokens).strip()

        valid_confs = [int(c) for c in data['conf']
                       if str(c).lstrip('-').isdigit() and int(c) >= 0]
        avg_conf = round(sum(valid_confs) / len(valid_confs), 2) if valid_confs else 0.0

        return text, avg_conf
    except Exception as e:
        logger.warning(f"Tesseract PSM {psm} falló: {e}")
        return "", 0.0

def extract_text_document(image: np.ndarray) -> tuple[str, float]:
    best_text, best_conf, best_wc = "", 0.0, -1
    for psm in [6, 4, 11]:
        text, conf = _run_ocr(image, psm)
        wc = len([w for w in text.split() if len(w) > 1])
        if wc > best_wc:
            best_text, best_conf, best_wc = text, conf, wc
    return best_text, best_conf

def extract_text_numeric(image: np.ndarray, whitelist: str) -> str:
    config = f"--oem 1 --psm 7 -c tessedit_char_whitelist={whitelist}"
    text = pytesseract.image_to_string(image, lang="spa", config=config)
    return text.strip()
