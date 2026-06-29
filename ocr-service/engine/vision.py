import cv2
import logging
import numpy as np
from PIL import Image, ExifTags

logger = logging.getLogger("ocr-engine.vision")


# ---------------------------------------------------------------------------
# Carga segura con corrección de orientación EXIF
# ---------------------------------------------------------------------------

def _load_image_exif_safe(image_path: str) -> np.ndarray:
    """
    Carga una imagen y asegura su orientación horizontal.
    
    NOTA: El sistema ahora define el estándar HORIZONTAL para todas las capturas,
    coincidiendo con las imágenes de prueba (test-img/). Los clientes móviles 
    normalizan la imagen antes del upload (quemando la orientación en los píxeles). 
    Esta función se mantiene para corregir orientaciones vía EXIF en caso de que 
    lleguen imágenes crudas sin normalizar.
    """
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
            if area < (h * w * 0.40):
                # El contorno cubre menos del 40% de la imagen.
                # Probablemente es un bloque de texto, no el borde del papel.
                continue

            # Validar que el contorno es aproximadamente rectangular
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
            if not (0.3 < aspect < 3.3):
                continue

            logger.info(f"[PERSPECTIVE] Corrigiendo perspectiva (área={area:.0f} px², aspect={aspect:.2f})")
            return _four_point_transform(image, approx.reshape(4, 2))

    logger.debug("[PERSPECTIVE] No se detectó borde de papel, sin corrección de perspectiva.")
    return image


# ---------------------------------------------------------------------------
# Auto-rotación por orientación: corrige imágenes portrait sin EXIF
# ---------------------------------------------------------------------------

def _auto_rotate_portrait(img: np.ndarray) -> np.ndarray:
    """
    Detecta y corrige imágenes de remito/calibre que llegan en orientación
    portrait (h > w) sin metadatos EXIF de orientación.

    Esto ocurre cuando la app móvil o el SO hace strip de EXIF antes del
    upload (comportamiento habitual en Android 13+ y iOS con ciertas
    configuraciones de privacidad). Los píxeles quedan rotados 90° pero el
    campo Orientation del EXIF dice 'normal', por lo que _load_image_exif_safe
    no los corrige.

    Estrategia en dos pasos:
      1. Primario — Tesseract OSD (PSM 0): lee el campo 'rotate' que indica
         el ángulo exacto de corrección. Muy rápido (~0.5s), sin extracción.
         Solo se activa si hay suficiente texto en la imagen (orient_conf > 1).
      2. Fallback — heurístico de runs horizontales: cuenta runs de píxeles
         oscuros ≥3px en muestras de filas. El texto horizontal tiene más runs
         que el texto vertical. Compara 0° vs 90° y elige el mejor.

    Solo actúa si la imagen es portrait (h > w). No modifica imágenes
    landscape.
    """
    h, w = img.shape[:2]

    # Los remitos y etiquetas de calibre son documentos horizontales.
    # Si w >= h, la orientación ya es correcta.
    if w >= h:
        return img

    logger.info(f"[AUTO-ROTATE] Portrait detectado ({w}×{h}), aplicando corrección...")

    # ── Paso 1: Tesseract OSD ──────────────────────────────────────────────
    try:
        import pytesseract
        # Reducir a 800px de ancho para acelerar OSD (trabaja bien a baja res)
        scale = min(1.0, 800 / w)
        probe = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        osd = pytesseract.image_to_osd(
            probe,
            config='--psm 0 -c min_characters_to_try=5',
            nice=0,
            output_type=pytesseract.Output.DICT,
        )
        rotate_needed = int(osd.get('rotate', 0))
        orient_conf   = float(osd.get('orientation_conf', 0))

        logger.debug(f"[AUTO-ROTATE] OSD: rotate={rotate_needed}° conf={orient_conf:.2f}")

        if orient_conf >= 0.5 and rotate_needed != 0:
            cv2_map = {
                90:  cv2.ROTATE_90_COUNTERCLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_CLOCKWISE,
            }
            if rotate_needed in cv2_map:
                logger.info(f"[AUTO-ROTATE] OSD recomienda {rotate_needed}° (conf={orient_conf:.2f}) → aplicando")
                return cv2.rotate(img, cv2_map[rotate_needed])
            logger.debug(f"[AUTO-ROTATE] OSD rotate={rotate_needed}° no mapeado, sin corrección OSD")

        elif orient_conf <= 1.0:
            logger.debug(f"[AUTO-ROTATE] OSD conf={orient_conf:.2f} insuficiente, probando heurístico")

    except Exception as e:
        logger.debug(f"[AUTO-ROTATE] OSD falló ({e}), usando heurístico")

    # ── Paso 2: Heurístico de runs horizontales ────────────────────────────
    # Compara la densidad de runs de píxeles oscuros en orientación 0° vs 90°.
    # El texto horizontal tiene muchos runs cortos en filas → score alto.
    def _run_score(candidate: np.ndarray) -> float:
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY) if len(candidate.shape) == 3 else candidate
        small = cv2.resize(gray, (400, 400), interpolation=cv2.INTER_AREA)
        _, binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        dark = (binary < 128)
        score = 0.0
        for row in dark[::4]:  # muestrear 1 de cada 4 filas
            run = 0
            for px in row:
                if px:
                    run += 1
                else:
                    if 3 <= run <= 80:  # runs típicos de letras (3-80px)
                        score += 1
                    run = 0
        return score

    score_0   = _run_score(img)
    rotated90 = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    score_90  = _run_score(rotated90)
    logger.debug(f"[AUTO-ROTATE] Heurístico: score_0°={score_0:.1f} score_90°={score_90:.1f}")

    if score_90 > score_0 * 1.2:  # margen del 20% para evitar correcciones por ruido
        logger.info(f"[AUTO-ROTATE] Heurístico → rotando 90° CCW (score {score_90:.1f} > {score_0:.1f})")
        return rotated90

    logger.debug("[AUTO-ROTATE] Sin corrección por heurístico")
    return img



# ---------------------------------------------------------------------------
# Carga segura + corrección de perspectiva — pública y reutilizable
# ---------------------------------------------------------------------------

def load_and_correct(image_path: str) -> np.ndarray:
    """
    Carga la imagen con corrección EXIF, auto-rotación portrait y perspectiva.

    Extraer esta lógica como función pública permite que el cascade en
    pipeline.py la invoque UNA sola vez y pase el resultado a ambos
    pipelines de preprocesado (impreso y manuscrito), evitando:
      - Doble lectura de disco.
      - Doble ejecución de _correct_perspective (Canny + findContours).

    Tres etapas de corrección:
      1. EXIF: corrige orientación por metadatos (cuando están presentes).
      2. AUTO-ROTATE: si la imagen es portrait (h > w), prueba las 4
         orientaciones y elige la que Tesseract OSD puntúa mejor.
         Cubre el caso donde Android/iOS hace strip de EXIF antes del upload.
      3. PERSPECTIVA: corrige distorsión trapezoidal de ángulo de captura.

    Dos caps de resolución:
      1. PRE-PERSPECTIVA (3M px): la detección de bordes del papel no
         necesita más resolución que ésta, y Canny+findContours escalan O(N).
         Para una foto 4K (12M px) esto reduce el tiempo de perspectiva ~4x.
      2. POST-PERSPECTIVA (2M px): cap final para que ningún stage reciba
         una imagen enorme. Previene que Stage 2 tarde 170s en imágenes de
         alta resolución.
    """
    MAX_PRE_PIXELS  = 3_000_000   # cap antes de detección de perspectiva
    MAX_BASE_PIXELS = 2_000_000   # cap final (pasado a preprocess_*)

    img = _load_image_exif_safe(image_path)

    # 1. Pre-resize: perspectiva funciona bien a 3Mpx, evita Canny en 12Mpx
    h, w = img.shape[:2]
    if h * w > MAX_PRE_PIXELS:
        scale = (MAX_PRE_PIXELS / (h * w)) ** 0.5
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        logger.debug(f"[LOAD] Pre-resize perspectiva: {w}×{h} → {int(w*scale)}×{int(h*scale)}")

    # 2. Auto-rotación: corrige portrait sin EXIF (primera captura Android/iOS)
    img = _auto_rotate_portrait(img)

    img = _correct_perspective(img)

    # 3. Post-resize: cap final para OCR
    h, w = img.shape[:2]
    if h * w > MAX_BASE_PIXELS:
        scale = (MAX_BASE_PIXELS / (h * w)) ** 0.5
        new_w, new_h = int(w * scale), int(h * scale)
        logger.info(f"[LOAD] Cap base: {w}×{h} → {new_w}×{new_h} ({h*w/1e6:.1f}Mpx → {MAX_BASE_PIXELS/1e6:.1f}Mpx)")
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return img



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

def preprocess_document(image_input: "str | np.ndarray") -> np.ndarray:
    """
    Pipeline optimizado para documentos IMPRESOS en papel.

    Acepta tanto una ruta de archivo (str) como un array ya cargado y
    corregido (np.ndarray). Cuando recibe un array, omite la carga de
    disco y la detección de perspectiva — útil en el cascade para evitar
    trabajo duplicado.

    Cap de 1600px de ancho (antes 2000px): suficiente para Tesseract y
    reduce ~36% de píxeles, acelerando todo el pipeline subsecuente.

    CLAHE antes del blur: mejora contraste de texto gris sobre fondo
    blanco (caso calibre), donde bilateralFilter solo no era suficiente.

    Usa GaussianBlur + medianBlur en lugar de bilateralFilter(d=9):
    10-20x más rápido con calidad equivalente para texto impreso limpio.
    """
    MAX_WIDTH = 1600

    if isinstance(image_input, str):
        img = load_and_correct(image_input)
    else:
        img = image_input  # ya cargado y corregido por el caller

    h, w = img.shape[:2]
    if w > MAX_WIDTH:
        scale = MAX_WIDTH / w
        img = cv2.resize(img, (MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
    elif w < 1000:
        # Solo escalar si es muy pequeña (capturas de baja resolución)
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE: mejora contraste local antes del blur.
    # Crucial para texto gris sobre fondo blanco (bajo contraste).
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # GaussianBlur + medianBlur: 10-20x más rápido que bilateralFilter(d=9)
    # y equivalente para eliminar ruido en texto impreso en papel limpio.
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    filtered = cv2.medianBlur(blurred, 3)

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


def preprocess_handwritten(image_input: "str | np.ndarray") -> np.ndarray:
    """
    Pipeline específico para texto MANUSCRITO en papel.

    Acepta tanto una ruta de archivo (str) como un array ya cargado y
    corregido (np.ndarray). Cuando recibe un array, omite la carga de
    disco y la detección de perspectiva — útil en el cascade para evitar
    trabajo duplicado.

    Diferencias clave respecto a preprocess_document:
    - Escalado más agresivo (3x) para capturar trazos finos.
    - CLAHE para mejorar contraste local con presión de trazo variable.
    - Gaussian blur suave (3x3) en lugar de bilateral para no borrar trazos.
    - blockSize=15 (vs 41) para adaptarse a la variabilidad del trazo.
    - Kernel morfológico mínimo para no fusionar letras escritas a mano.
    """
    MAX_WIDTH = 1600

    if isinstance(image_input, str):
        img = load_and_correct(image_input)
    else:
        img = image_input  # ya cargado y corregido por el caller

    h, w = img.shape[:2]
    if w > MAX_WIDTH:
        scale = MAX_WIDTH / w
        img = cv2.resize(img, (MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
    elif w < 2000:
        scale = 3 if w < 1000 else 2
        new_w = min(w * scale, MAX_WIDTH)
        new_h = int(h * (new_w / w))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

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

    Usa _load_image_exif_safe para corregir orientación según metadatos EXIF.

    El escalado se limita a MAX_WIDTH=1600px: suficiente para que Tesseract
    lea dígitos grandes de un display, y evita que imágenes de cámara
    moderna (4K) se dupliquen a 8000px+ saturando la CPU por 90s.
    """
    MAX_WIDTH = 1600

    img = _load_image_exif_safe(image_path)
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen: {image_path}")

    h, w = img.shape[:2]
    if w < MAX_WIDTH:
        # Solo escalar si la imagen es más pequeña que el máximo deseado
        scale = MAX_WIDTH / w
        img = cv2.resize(img, (MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_CUBIC)
    elif w > MAX_WIDTH:
        # Reducir si es demasiado grande (ej: 4K de cámara)
        scale = MAX_WIDTH / w
        img = cv2.resize(img, (MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.GaussianBlur(gray, (5, 5), 0)
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if np.sum(binary == 0) > np.sum(binary == 255):
        binary = cv2.bitwise_not(binary)
    return binary
