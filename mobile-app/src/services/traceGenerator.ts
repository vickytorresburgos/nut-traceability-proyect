/**
 * traceGenerator.ts — Generación de ID de traza local (modo offline)
 *
 * Formato: {2 iniciales de finca}-{número secuencial 2 dígitos}
 * Ejemplo: "LAS FLORES" → "LF-01"
 *
 * Cuando el lote se sincroniza, el servidor asigna el trace_number definitivo.
 * El ID local se marca como provisional con el prefijo "L-".
 * Ej: "L-LF-1746384000" (timestamp como desambiguador offline)
 */

import { db } from '../db/database';

/**
 * Extrae las iniciales de una finca.
 * "LAS FLORES"    → "LF"
 * "LA ESPERANZA"  → "LE"
 * "LOS TILOS"     → "LT"
 */
export function getFarmInitials(farmName: string): string {
  const words = farmName.trim().toUpperCase().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2);
  // Tomar primera letra de cada palabra (máx 2 palabras)
  return words
    .slice(0, 2)
    .map((w) => w[0])
    .join('');
}

/**
 * Genera un trace_number local para uso offline.
 * Cuenta los lotes existentes de la misma finca hoy para el número secuencial.
 */
export async function generateLocalTraceNumber(farmName: string): Promise<string> {
  const initials = getFarmInitials(farmName);
  const today = new Date().toISOString().slice(0, 10);

  // Contar lotes de esta finca creados hoy para el secuencial
  const lotesHoy = await db.getBatchesForToday();
  const count = lotesHoy.filter((l) => l.farm_name === farmName).length + 1;

  // El usuario solicitó el formato exacto: LF-04
  return `${initials}-${String(count).padStart(2, '0')}`;
}

/**
 * Verifica si un trace_number es provisional (generado offline)
 */
export function isProvisionalTrace(traceNumber: string): boolean {
  return traceNumber.startsWith('L-');
}
