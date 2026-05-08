import cv2
import logging
import numpy as np
from PIL import Image, ExifTags

logger = logging.getLogger("ocr-engine.vision")


# ---------------------------------------------------------------------------
# Carga segura con corrección de orientación EXIF
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Corrección de perspectiva (distorsión trapezoidal)
# ---------------------------------------------------------------------------

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 puntos: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left: suma mínima
    rect[2] = pts[np.argmax(s)]   # bottom-right: suma máxima
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right: diferencia mínima
    rect[3] = pts[np.argmax(diff)]  # bottom-left: diferencia máxima
    return rect


def _four_point_transform(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Aplica transformación de perspectiva a partir de 4 puntos."""
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect

    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = max(int(heightA), int(heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (maxWidth, maxHeight))


def _correct_perspective(image: np.ndarray) -> np.ndarray:
    """
    Detecta el borde del papel en la imagen y corrige la distorsión de
    perspectiva trapezoidal causada por ángulo de captura.
    Devuelve la imagen original si no se detecta un contorno válido.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 50, 200)

    # Dilatar para conectar bordes fragmentados
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edged = cv2.dilate(edged, kernel, iterations=1)

    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    h, w = image.shape[:2]
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            area = cv2.contourArea(approx)
            if area < (h * w * 0.60):
                # El contorno cubre menos del 60% de la imagen.
                # Probablemente es un bloque de texto, no el borde del papel.
                continue

            # Validar que el contorno es aproximadamente rectangular
            # (evita aplicar la transformación a formas muy irregulares)
            pts = approx.reshape(4, 2)
            rect = _order_points(pts)
            (tl, tr, br, bl) = rect
            w_top = np.linalg.norm(tr - tl)
            w_bot = np.linalg.norm(br - bl)
            h_left = np.linalg.norm(bl - tl)
            h_right = np.linalg.norm(br - tr)
            avg_w = (w_top + w_bot) / 2
            avg_h = (h_left + h_right) / 2
            if avg_w < 1 or avg_h < 1:
                continue
            aspect = avg_w / avg_h
            if not (0.3 < aspect < 3.3):  # descartar formas muy alargadas o muy anchas
                continue

            logger.info(f"[PERSPECTIVE] Corrigiendo perspectiva (área={area:.0f} px², aspect={aspect:.2f})")
            return _four_point_transform(image, approx.reshape(4, 2))

    logger.debug("[PERSPECTIVE] No se detectó borde de papel, sin corrección de perspectiva.")
    return image



# ---------------------------------------------------------------------------
# Corrección de inclinación (deskew)
# ---------------------------------------------------------------------------

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
    return cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )


# ---------------------------------------------------------------------------
# Pipelines de preprocesado
# ---------------------------------------------------------------------------

def preprocess_document(image_path: str) -> np.ndarray:
    """
    Pipeline optimizado para documentos IMPRESOS en papel.
    Aplica bilateral filter y adaptive threshold con bloque grande.
    """
    img = _load_image_exif_safe(image_path)
    h, w = img.shape[:2]
    if w < 1500:
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    img = _correct_perspective(img)

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
    return _deskew(binary)


def preprocess_handwritten(image_path: str) -> np.ndarray:
    """
    Pipeline específico para texto MANUSCRITO en papel.

    Diferencias clave respecto a preprocess_document:
    - Escalado más agresivo (3x) para capturar trazos finos.
    - CLAHE para mejorar contraste local con presión de trazo variable.
    - Gaussian blur suave (3x3) en lugar de bilateral para no borrar trazos.
    - blockSize=15 (vs 41) para adaptarse a la variabilidad del trazo.
    - Kernel morfológico mínimo para no fusionar letras escritas a mano.
    """
    img = _load_image_exif_safe(image_path)
    h, w = img.shape[:2]

    # Escalar más agresivamente para capturar detalles del trazo manuscrito
    scale = 3 if w < 1000 else 2
    if w < 2000:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    img = _correct_perspective(img)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE: mejora contraste local, fundamental cuando la presión del trazo varía
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Blur suave para no borrar trazos finos
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

    # Threshold adaptativo con bloque pequeño (adaptado a trazo variable)
    binary = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=8
    )

    # Morfología mínima para no fusionar letras manuscritas
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (1, 1))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    if np.sum(binary == 0) > np.sum(binary == 255):
        binary = cv2.bitwise_not(binary)

    return _deskew(binary)


def preprocess_display(image_path: str) -> np.ndarray:
    """
    Pipeline para imágenes de displays digitales (LCD/LED).
    Usa Otsu threshold que es óptimo para texto blanco sobre fondo oscuro.
    FIX: ahora usa _load_image_exif_safe para corregir orientación EXIF.
    """
    img = _load_image_exif_safe(image_path)  # antes: cv2.imread (sin corrección EXIF)
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if np.sum(binary == 0) > np.sum(binary == 255):
        binary = cv2.bitwise_not(binary)
    return binary
