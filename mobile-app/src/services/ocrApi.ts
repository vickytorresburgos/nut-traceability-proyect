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

import { optimizeImage } from './imageService';
import { API_URL as API_BASE, API_KEY } from './config';

// ── Tipos de respuesta del OCR ─────────────────────────────────────────────

export interface RemitoOcrResult {
  raw_text: string;
  farm_name: string | null;
  harvest_type: string | null;
  date: string | null;
  confidence: number;
  confidence_alert: boolean;
}

export interface OvenOcrResult {
  raw_text: string;
  oven_id: string | null;
  humidity: string | null;
  confidence: number;
  confidence_alert: boolean;
  errors: any[];
}

export interface CaliberOcrResult {
  raw_text: string;
  caliber: string | null;
  weight: string | null;
  confidence: number;
  confidence_alert: boolean;
}

/** Timeout en milisegundos para las llamadas OCR (el motor puede tardar con EasyOCR) */
const OCR_TIMEOUT_MS = 150_000; // 150 segundos

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
  // Optimizar imagen antes de subir
  const optimizedUri = await optimizeImage(imageUri);
  
  const form = new FormData();
  form.append('image', {
    uri: optimizedUri,
    name: imageName,
    type: 'image/jpeg',
  } as any);

  const url = `${API_BASE}${endpoint}`;
  
  let lastError: any;
  const maxRetries = 2; // Total 3 intentos

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      if (attempt > 0) {
        console.log(`[ocrApi] Reintentando (${attempt}/${maxRetries}) para: ${url}`);
        // Espera exponencial corta (500ms, 1000ms)
        await new Promise(resolve => setTimeout(resolve, attempt * 500));
      }

      console.log(`[ocrApi] Llamando a: ${url}`);

      const headers: Record<string, string> = {
        'bypass-tunnel-reminder': '1',
      };
      if (API_KEY) {
        headers['X-API-KEY'] = API_KEY;
      }

      const response = await fetchWithTimeout(url, {
        method: 'POST',
        body: form,
        headers: headers,
      }, OCR_TIMEOUT_MS);

      let body: any;
      try {
        body = await response.json();
      } catch {
        body = { detail: response.statusText };
      }

      if (!response.ok) {
        // El servidor devuelve { detail: "..." } en errores 4xx/5xx
        // Estos no se reintentan porque suelen ser errores de calidad de imagen o lógica
        const detail = body?.detail ?? `Error HTTP ${response.status}`;
        throw new Error(detail);
      }

      return body;
    } catch (err: any) {
      lastError = err;
      // No reintentar si es un error descriptivo de la API (calidad de imagen, etc.)
      // o si ya agotamos los intentos.
      if (err.message && (err.message.includes('calidad insuficiente') || err.message.includes('HTTP'))) {
        throw err;
      }
      
      console.warn(`[ocrApi] Intento ${attempt} falló: ${err.message}`);
      if (attempt === maxRetries) {
        throw new Error(
          `No se pudo conectar con el servidor tras ${maxRetries + 1} intentos. ` +
          'Verificá tu conexión y que el servidor esté encendido.'
        );
      }
    }
  }
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
