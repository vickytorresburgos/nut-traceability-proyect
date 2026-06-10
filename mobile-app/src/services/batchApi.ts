import { API_URL } from './config';
import { optimizeImage } from './imageService';
import * as SecureStore from 'expo-secure-store';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    'Accept': 'application/json',
    'bypass-tunnel-reminder': '1',
  };
  const token = await SecureStore.getItemAsync('userToken');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse(response: Response) {
  if (response.status === 401) {
    await SecureStore.deleteItemAsync('userToken');
    throw new Error('Sesión expirada. Por favor inicie sesión de nuevo.');
  }

  if (!response.ok) {
    let errorMsg = response.statusText;
    try {
      const json = await response.json();
      if (json.detail) errorMsg = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
    } catch {
      const text = await response.text();
      if (text) errorMsg = text;
    }
    throw new Error(`Error ${response.status}: ${errorMsg}`);
  }
  return response.json();
}

export async function createBatchFromRemito(
  imageUri: string,
  ocrData?: { farm_name: string; harvest_type: string; remito_date?: string }
) {
  const optimizedUri = await optimizeImage(imageUri);
  const form = new FormData();
  form.append('remito_image', { uri: optimizedUri, name: 'remito.jpg', type: 'image/jpeg' } as any);
  if (ocrData) {
    form.append('farm_name', ocrData.farm_name);
    form.append('harvest_type', ocrData.harvest_type);
    if (ocrData.remito_date) form.append('remito_date', ocrData.remito_date);
  }
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/batches`, {
    method: 'POST', body: form, headers: headers,
  });
  return handleResponse(res);
}

export async function addOvenToBatch(
  serverBatchId: number,
  imageUri: string,
  ocrData?: { oven_id: string; humidity: string }
) {
  const optimizedUri = await optimizeImage(imageUri);
  const form = new FormData();
  form.append('oven_image', { uri: optimizedUri, name: 'oven.jpg', type: 'image/jpeg' } as any);
  if (ocrData) {
    form.append('oven_id', ocrData.oven_id);
    form.append('humidity', ocrData.humidity);
  }
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/batches/${serverBatchId}/oven`, {
    method: 'POST', body: form, headers: headers,
  });
  return handleResponse(res);
}

export async function addCaliberToBatch(
  serverBatchId: number,
  imageUri: string,
  ocrData?: { caliber: string; weight: string }
) {
  const optimizedUri = await optimizeImage(imageUri);
  const form = new FormData();
  form.append('caliber_image', { uri: optimizedUri, name: 'caliber.jpg', type: 'image/jpeg' } as any);
  if (ocrData) {
    form.append('caliber', ocrData.caliber);
    form.append('weight', ocrData.weight);
  }
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/batches/${serverBatchId}/caliber`, {
    method: 'POST', body: form, headers: headers,
  });
  return handleResponse(res);
}

export async function completeBatch(serverBatchId: number) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/v1/batches/${serverBatchId}/complete`, {
    method: 'POST', headers: headers,
  });
  return handleResponse(res);
}
