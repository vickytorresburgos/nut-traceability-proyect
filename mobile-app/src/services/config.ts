import { Platform } from 'react-native';


const DEFAULT_HOST = Platform.OS === 'android' ? '192.168.100.10' : 'localhost';

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? `http://${DEFAULT_HOST}`;

export const API_KEY = process.env.EXPO_PUBLIC_API_KEY;

export const DASHBOARD_URL = `${API_URL}/dashboard`;
