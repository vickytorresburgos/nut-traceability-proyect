import { Platform } from 'react-native';

/**
 * IP del servidor donde corre Nginx (puerto 80).
 * En Android Emulator, 10.0.2.2 apunta al host.
 * En dispositivo físico, debe ser la IP local de la PC (ej: 192.168.1.50).
 */
const DEFAULT_HOST = Platform.OS === 'android' ? '192.168.100.10' : 'localhost';

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? `http://${DEFAULT_HOST}`;

/**
 * URL base para el dashboard público.
 * El QR apuntará a: ${DASHBOARD_URL}/?trace_id=XXXX
 */
export const DASHBOARD_URL = `${API_URL}/dashboard`;
