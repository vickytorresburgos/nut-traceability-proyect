import cv2
import logging
import numpy as np
from PIL import Image, ExifTags

logger = logging.getLogger("ocr-engine.vision")

def _load_image_exif_safe(image_path: str) -> np.ndarray:
    try:
        pil_img = Image.open(image_path)
        exif = pil_img._getexif()
        if exif:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == 'Orientation':
                    rotations = {
                        3: Image.ROTATE_180,
                        6: Image.ROTATE_270,
                        8: Image.ROTATE_90,
                    }
                    if value in rotations:
                        pil_img = pil_img.transpose(rotations[value])
                    break
        return cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)
    except Exception as e:
        logger.warning(f"PIL no pudo cargar {image_path}: {e} — usando cv2.imread como fallback")
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"No se pudo cargar la imagen: {image_path}")
        return img

def _deskew(image: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(image < 128))
    if len(coords) < 50:
        return image

    pts = coords[:, ::-1].astype(np.float32)
    rect = cv2.minAreaRect(pts)
    angle = rect[-1]

    if angle < -45:
        angle = 90 + angle

    if abs(angle) < 1.0:
        logger.debug(f"[DESKEW] Ángulo {angle:.2f}° < 1°, sin corrección necesaria.")
        return image

    logger.info(f"[DESKEW] Corrigiendo inclinación de {angle:.2f}°")
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated

def preprocess_document(image_path: str) -> np.ndarray:
    img = _load_image_exif_safe(image_path)
    h, w = img.shape[:2]
    if w < 1500:
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
    binary = cv2.adaptiveThreshold(
        filtered, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=41,
        C=15
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    if np.sum(binary == 0) > np.sum(binary == 255):
        binary = cv2.bitwise_not(binary)
    binary = _deskew(binary)
    return binary

def preprocess_display(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen: {image_path}")

    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if np.sum(binary == 0) > np.sum(binary == 255):
        binary = cv2.bitwise_not(binary)
    return binary
