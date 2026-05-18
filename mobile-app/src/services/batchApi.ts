import { API_URL, API_KEY } from './config';
import { optimizeImage } from './imageService';

const DEFAULT_HEADERS: Record<string, string> = {
  'Accept': 'application/json',
  'bypass-tunnel-reminder': '1',
};

if (API_KEY) {
  DEFAULT_HEADERS['X-API-KEY'] = API_KEY;
}

async function handleResponse(response: Response) {
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
  const res = await fetch(`${API_URL}/api/v1/batches`, {
    method: 'POST', body: form, headers: DEFAULT_HEADERS,
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
  const res = await fetch(`${API_URL}/api/v1/batches/${serverBatchId}/oven`, {
    method: 'POST', body: form, headers: DEFAULT_HEADERS,
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
  const res = await fetch(`${API_URL}/api/v1/batches/${serverBatchId}/caliber`, {
    method: 'POST', body: form, headers: DEFAULT_HEADERS,
  });
  return handleResponse(res);
}

export async function completeBatch(serverBatchId: number) {
  const res = await fetch(`${API_URL}/api/v1/batches/${serverBatchId}/complete`, {
    method: 'POST', headers: DEFAULT_HEADERS,
  });
  return handleResponse(res);
}
