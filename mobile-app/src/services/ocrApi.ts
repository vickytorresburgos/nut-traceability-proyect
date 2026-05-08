/**
 * src/services/ocrApi.ts
 *
 * Cliente centralizado para comunicarse con el motor OCR
 * a través del nut-api (el móvil nunca habla directo con el OCR service).
 *
 * Arquitectura:
 *   Móvil  →  nut-api (:8080)  →  ocr-service (interno :8081)
 *
 * Los endpoints del nut-api manejan internamente:
 *   - Subida de la imagen a MinIO
 *   - Llamada al OCR service con timeout adecuado
 *   - Persistencia en la base de datos
 *   - Errores de calidad de imagen (devuelven 422 con mensaje claro)
 */

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://192.168.100.10:8080';

/** Timeout en milisegundos para las llamadas OCR (el motor puede tardar con EasyOCR) */
const OCR_TIMEOUT_MS = 90_000; // 90 segundos

// ---------------------------------------------------------------------------
// Tipos de respuesta del nut-api
// ---------------------------------------------------------------------------

export interface RemitoOcrResult {
  farm_name: string | null;
  harvest_type: string | null;
  date: string | null;
  confidence: number;
  confidence_alert: boolean;
  raw_text: string;
}

export interface OvenOcrResult {
  oven_id: string | null;
  humidity: string | null;
  confidence: number;
  confidence_alert: boolean;
  raw_text: string;
  errors: string[];
}

export interface CaliberOcrResult {
  caliber: string | null;
  weight: string | null;
  confidence: number;
  confidence_alert: boolean;
  raw_text: string;
}

// ---------------------------------------------------------------------------
// Helper interno: fetch con timeout y manejo de errores descriptivo
// ---------------------------------------------------------------------------

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err: any) {
    if (err.name === 'AbortError') {
      throw new Error(
        `El motor OCR tardó demasiado en responder (>${timeoutMs / 1000}s). ` +
        'Verificá que el servidor esté corriendo y volvé a intentarlo.'
      );
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function postImageToApi(endpoint: string, imageUri: string, imageName: string): Promise<any> {
  const form = new FormData();
  form.append('image', {
    uri: imageUri,
    name: imageName,
    type: 'image/jpeg',
  } as any);

  const url = `${API_BASE}${endpoint}`;
  const response = await fetchWithTimeout(url, {
    method: 'POST',
    body: form,
    headers: {
      // Requerido para que localtunnel no bloquee requests que no son de un navegador
      'bypass-tunnel-reminder': '1',
    },
  }, OCR_TIMEOUT_MS);

  let body: any;
  try {
    body = await response.json();
  } catch {
    body = { detail: response.statusText };
  }

  if (!response.ok) {
    // El servidor devuelve { detail: "..." } en errores 4xx/5xx
    const detail = body?.detail ?? `Error HTTP ${response.status}`;
    throw new Error(detail);
  }

  return body;
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/**
 * Envía la imagen del remito al nut-api para procesamiento OCR.
 * El nut-api sube la imagen a MinIO y llama internamente al OCR service.
 *
 * NOTA: Este endpoint crea un batch en la base de datos del servidor.
 * Para el flujo offline-first, usar directamente el OCR endpoint.
 */
export async function runRemitoOcr(imageUri: string): Promise<RemitoOcrResult> {
  return postImageToApi('/ocr/remito', imageUri, 'remito.jpg');
}

/**
 * Envía la imagen del horno al OCR service via nut-api.
 */
export async function runOvenOcr(imageUri: string): Promise<OvenOcrResult> {
  return postImageToApi('/ocr/oven', imageUri, 'oven.jpg');
}

/**
 * Envía la imagen del calibre al OCR service via nut-api.
 */
export async function runCaliberOcr(imageUri: string): Promise<CaliberOcrResult> {
  return postImageToApi('/ocr/caliber', imageUri, 'caliber.jpg');
}
