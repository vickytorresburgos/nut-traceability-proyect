import * as ImageManipulator from 'expo-image-manipulator';

/**
 * Optimiza una imagen para su envío al servidor:
 * - Redimensiona el ancho a 2000px (suficiente para OCR).
 * - Comprime al 90% de calidad.
 * - Convierte a JPEG.
 * 
 * NOTA: Esta función asume que la imagen ya viene con la orientación
 * normalizada (pixels 'upright'), ya que ImageManipulator elimina los 
 * metadatos EXIF. La normalización se realiza en el paso de captura.
 */
export async function optimizeImage(uri: string): Promise<string> {
  console.log(`[ImageService] Optimizando imagen: ${uri}`);
  try {
    const result = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: 2000 } }], // Un poco más grande para mejor detalle
      { compress: 0.9, format: ImageManipulator.SaveFormat.JPEG } // Menos compresión (90%)
    );
    console.log(`[ImageService] Imagen optimizada: ${result.uri} (${result.width}x${result.height})`);
    return result.uri;
  } catch (error) {
    console.error(`[ImageService] Error al optimizar imagen:`, error);
    return uri; // Si falla, devolvemos la original como fallback
  }
}
