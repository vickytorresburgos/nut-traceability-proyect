import Constants from 'expo-constants';

/**
 * Detecta dinámicamente la IP del host de desarrollo.
 *
 * Lógica de prioridad:
 * 1. EXPO_PUBLIC_API_URL en .env  → producción o configuración manual explícita
 * 2. hostUri de Expo              → desarrollo con Expo Go / dev build (misma PC que el Metro bundler)
 * 3. localhost                    → simulador iOS (que sí puede resolver localhost del host)
 */
function getApiUrl(): string {
  // 1. Variable de entorno explícita (producción o override manual)
  if (process.env.EXPO_PUBLIC_API_URL) {
    return process.env.EXPO_PUBLIC_API_URL;
  }

  // 2. En desarrollo, Expo expone la IP del host mediante hostUri (ej: "192.168.x.x:8081")
  //    La API corre en la misma máquina que el bundler, solo cambiamos el puerto.
  const hostUri = Constants.expoConfig?.hostUri;
  if (hostUri) {
    const hostIp = hostUri.split(':')[0]; // extraer solo la IP, sin el puerto de Metro
    return `http://${hostIp}:8080`;
  }

  // 3. Fallback: simulador iOS puede usar localhost directamente
  return 'http://localhost:8080';
}

export const API_URL = getApiUrl();

export const API_KEY = process.env.EXPO_PUBLIC_API_KEY;

export const DASHBOARD_URL = `${API_URL}/dashboard`;
