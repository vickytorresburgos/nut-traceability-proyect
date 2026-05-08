// La URL base se lee del archivo .env (EXPO_PUBLIC_API_URL).
// Si no está definida, cae en la IP local donde corre el nut-api.
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://192.168.100.10:8080';

export interface CompleteBatchPayload {
  remitoImageUri: string;
  ovenImageUri: string;
  caliberImageUri: string;
  farmName: string;
  harvestType: string;
  remitoDate: string;
  ovenId: string;
  humidity: string;
  caliber: string;
  weight: string;
}

export async function createCompleteBatch(payload: CompleteBatchPayload) {
  const formData = new FormData();
  
  // Añadir imágenes
  const appendImage = (uri: string, name: string) => {
    const filename = uri.split('/').pop() || `${name}.jpg`;
    const type = 'image/jpeg';
    formData.append(name, {
      uri,
      name: filename,
      type,
    } as any);
  };

  appendImage(payload.remitoImageUri, 'remito_image');
  appendImage(payload.ovenImageUri, 'oven_image');
  appendImage(payload.caliberImageUri, 'caliber_image');

  // Añadir datos de formulario
  formData.append('farm_name', payload.farmName);
  formData.append('harvest_type', payload.harvestType);
  formData.append('remito_date', payload.remitoDate);
  formData.append('oven_id', payload.ovenId);
  formData.append('humidity', payload.humidity);
  formData.append('caliber', payload.caliber);
  formData.append('weight', payload.weight);

  console.log(`[BatchAPI] POST /api/v1/batches/complete`);
  
  const response = await fetch(`${API_URL}/api/v1/batches/complete`, {
    method: 'POST',
    body: formData,
    headers: {
      'Accept': 'application/json',
      // Requerido para que localtunnel no bloquee requests que no son de un navegador
      'bypass-tunnel-reminder': '1',
      // Content-Type se auto genera con el boundary de FormData
    },
  });

  if (!response.ok) {
    let errorMsg = response.statusText;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMsg = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
      }
    } catch (e) {
      const errorText = await response.text();
      if (errorText) errorMsg = errorText;
    }
    throw new Error(`Error en el servidor: ${response.status} - ${errorMsg}`);
  }

  return response.json();
}
