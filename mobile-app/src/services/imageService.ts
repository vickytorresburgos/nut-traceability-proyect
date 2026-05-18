import * as ImageManipulator from 'expo-image-manipulator';

export async function optimizeImage(uri: string): Promise<string> {
  console.log(`[ImageService] Optimizando imagen: ${uri}`);
  try {
    const result = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: 2000 } }], 
      { compress: 0.9, format: ImageManipulator.SaveFormat.JPEG } 
    );
    console.log(`[ImageService] Imagen optimizada: ${result.uri} (${result.width}x${result.height})`);
    return result.uri;
  } catch (error) {
    console.error(`[ImageService] Error al optimizar imagen:`, error);
    return uri; 
  }
}
