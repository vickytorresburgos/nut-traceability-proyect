/**
 * syncManager.ts — Cola de sincronización Offline-First
 *
 * Responsabilidades:
 *  1. Detectar conectividad via NetInfo
 *  2. Procesar la sync_queue en orden (CREATE → ADD_OVEN → ADD_CALIBER)
 *  3. Verificar integridad SHA-256 de la imagen antes de cada upload
 *  4. Retry con exponential backoff (máx 5 intentos)
 *  5. Actualizar el estado del lote en SQLite
 */

import * as FileSystem from 'expo-file-system/legacy';
import * as Crypto from 'expo-crypto';
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';
import { db, SyncQueueItem, Captura } from '../db/database';

import { API_URL as API_BASE, API_KEY } from './config';
import { optimizeImage } from './imageService';
const MAX_ATTEMPTS = 5;
const BASE_BACKOFF_MS = 2_000; // 2s * 2^attempt

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

type Operation = 'CREATE_BATCH' | 'ADD_OVEN' | 'ADD_CALIBER' | 'COMPLETE_BATCH';

// ---------------------------------------------------------------------------
// SyncManager — Singleton
// ---------------------------------------------------------------------------

class SyncManager {
  private isSyncing = false;
  private unsubscribeNetInfo: (() => void) | null = null;
  private intervalId: ReturnType<typeof setInterval> | null = null;

  /** Iniciar listener de red + polling cada 30s */
  start(): void {
    this.unsubscribeNetInfo = NetInfo.addEventListener(
      (state: NetInfoState) => {
        if (state.isConnected && state.isInternetReachable) {
          this.sync();
        }
      }
    );
    this.intervalId = setInterval(() => this.sync(), 30_000);
    // Intentar sincronizar inmediatamente al iniciar
    this.sync();
  }

  stop(): void {
    this.unsubscribeNetInfo?.();
    if (this.intervalId) clearInterval(this.intervalId);
  }

  // -------------------------------------------------------------------------
  // Sync principal
  // -------------------------------------------------------------------------

  async sync(): Promise<void> {
    if (this.isSyncing) return;

    const netState = await NetInfo.fetch();
    // En desarrollo/USB, isInternetReachable puede ser false. 
    // Solo validamos que esté "conectado" físicamente (vía Wi-Fi o Túnel).
    if (!netState.isConnected) {
      console.log('[SyncManager] Sin conexión física detectada.');
      return;
    }

    this.isSyncing = true;
    console.log(`[SyncManager] Iniciando sync con base: ${API_BASE}`);

    try {
      const pending = await db.getPendingItems();
      console.log(`[SyncManager] ${pending.length} items pendientes`);

      for (const item of pending) {
        await this.processItem(item);
      }
    } catch (err) {
      console.error('[SyncManager] Error inesperado:', err);
    } finally {
      this.isSyncing = false;
    }
  }

  // -------------------------------------------------------------------------
  // Procesar un item de la cola
  // -------------------------------------------------------------------------

  private async processItem(item: SyncQueueItem): Promise<void> {
    if (item.attempt_count >= MAX_ATTEMPTS) {
      await db.setSyncItemStatus(item.id, 'FAILED', 'Máximo de intentos alcanzado');
      return;
    }

    // Backoff exponencial
    if (item.attempt_count > 0 && item.last_attempt) {
      const nextRetry =
        new Date(item.last_attempt).getTime() +
        BASE_BACKOFF_MS * Math.pow(2, item.attempt_count - 1);
      if (Date.now() < nextRetry) return; // Todavía no es momento
    }

    await db.setSyncItemStatus(item.id, 'IN_PROGRESS');

    try {
      const payload = JSON.parse(item.payload);
      
      switch (item.operation as Operation) {
        case 'CREATE_BATCH':
          await this.createBatch(item, payload);
          break;
        case 'ADD_OVEN':
          await this.addOven(item, payload);
          break;
        case 'ADD_CALIBER':
          await this.addCaliber(item, payload);
          break;
        case 'COMPLETE_BATCH':
          await this.completeBatch(item);
          break;
      }
      await db.setSyncItemStatus(item.id, 'DONE');
      await db.updateBatchStatus(item.lote_id, 'SYNCED', new Date().toISOString());
      console.log(`[SyncManager] [OK] ${item.operation} lote=${item.lote_id}`);
    } catch (err: any) {
      const msg = err?.message ?? String(err);
      console.warn(`[SyncManager] [WARN] ${item.operation} falló (intento ${item.attempt_count + 1}): ${msg}`);
      await db.incrementSyncAttempt(item.id, msg);
    }
  }

  // -------------------------------------------------------------------------
  // Verificación de integridad de imagen (Chain-of-Thought)
  //
  // La imagen se guardó en DocumentDirectory sin re-comprimir.
  // Su SHA-256 fue calculado en el momento de la captura.
  // Antes de subir, recalculamos el hash y comparamos.
  // Si no coincide → la imagen fue corrompida en reposo → pedimos retomar foto.
  // -------------------------------------------------------------------------

  private async verifyImageIntegrity(captura: Captura): Promise<void> {
    const b64 = await FileSystem.readAsStringAsync(captura.local_path, {
      // @ts-ignore - EncodingType missing from expo-file-system types
      encoding: FileSystem.EncodingType.Base64,
    });
    const currentHash = await Crypto.digestStringAsync(
      Crypto.CryptoDigestAlgorithm.SHA256,
      b64
    );
    if (currentHash !== captura.sha256_hash) {
      throw new Error(
        `Integridad comprometida en ${captura.type} (lote ${captura.lote_id}). ` +
        `Esperado: ${captura.sha256_hash.slice(0, 8)}... ` +
        `Actual: ${currentHash.slice(0, 8)}...`
      );
    }
  }

  // -------------------------------------------------------------------------
  // Operaciones de API
  // -------------------------------------------------------------------------

  private async createBatch(item: SyncQueueItem, payload: any): Promise<void> {
    const captura = await db.getCapturaByType(item.lote_id, 'remito');
    if (!captura) throw new Error('Captura de remito no encontrada');

    await this.verifyImageIntegrity(captura);
    const optimizedUri = await optimizeImage(captura.local_path);

    const form = new FormData();
    form.append('remito_image', {
      uri: optimizedUri,
      name: 'remito.jpg',
      type: 'image/jpeg',
    } as any);
    
    if (payload.farm_name) form.append('farm_name', payload.farm_name);
    if (payload.harvest_type) form.append('harvest_type', payload.harvest_type);
    if (payload.remito_date) form.append('remito_date', payload.remito_date);

    const headers: Record<string, string> = {};
    if (API_KEY) headers['X-API-KEY'] = API_KEY;

    const res = await fetch(`${API_BASE}/api/v1/batches`, {
      method: 'POST',
      body: form,
      headers: headers,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

    const { batch_id, trace_number } = await res.json();
    await db.updateBatchAfterSync(item.lote_id, batch_id, trace_number ?? null);
  }

  private async addOven(item: SyncQueueItem, payload: any): Promise<void> {
    const lote = await db.getBatchById(item.lote_id);
    if (!lote?.server_id) throw new Error('server_id aún no disponible, esperar CREATE_BATCH');

    const captura = await db.getCapturaByType(item.lote_id, 'oven');
    if (!captura) throw new Error('Captura de horno no encontrada');

    await this.verifyImageIntegrity(captura);
    const optimizedUri = await optimizeImage(captura.local_path);

    const form = new FormData();
    form.append('oven_image', {
      uri: optimizedUri,
      name: 'oven.jpg',
      type: 'image/jpeg',
    } as any);
    
    if (payload.oven_id) form.append('oven_id', payload.oven_id);
    if (payload.humidity) form.append('humidity', payload.humidity);

    const headers: Record<string, string> = {};
    if (API_KEY) headers['X-API-KEY'] = API_KEY;

    const res = await fetch(`${API_BASE}/api/v1/batches/${lote.server_id}/oven`, {
      method: 'POST',
      body: form,
      headers: headers,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }

  private async addCaliber(item: SyncQueueItem, payload: any): Promise<void> {
    const lote = await db.getBatchById(item.lote_id);
    if (!lote?.server_id) throw new Error('server_id aún no disponible');

    const captura = await db.getCapturaByType(item.lote_id, 'caliber');
    if (!captura) throw new Error('Captura de calibre no encontrada');

    await this.verifyImageIntegrity(captura);
    const optimizedUri = await optimizeImage(captura.local_path);

    const form = new FormData();
    form.append('caliber_image', {
      uri: optimizedUri,
      name: 'caliber.jpg',
      type: 'image/jpeg',
    } as any);
    
    if (payload.caliber) form.append('caliber', payload.caliber);
    if (payload.weight) form.append('weight', payload.weight);

    const headers: Record<string, string> = {};
    if (API_KEY) headers['X-API-KEY'] = API_KEY;

    const res = await fetch(`${API_BASE}/api/v1/batches/${lote.server_id}/caliber`, {
      method: 'POST',
      body: form,
      headers: headers,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }

  private async completeBatch(item: SyncQueueItem): Promise<void> {
    const lote = await db.getBatchById(item.lote_id);
    if (!lote?.server_id) throw new Error('server_id aún no disponible');

    const headers: Record<string, string> = {};
    if (API_KEY) headers['X-API-KEY'] = API_KEY;

    const res = await fetch(`${API_BASE}/api/v1/batches/${lote.server_id}/complete`, {
      method: 'POST',
      headers: headers,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    
    const result = await res.json();
    // Actualizar el lote local con el trace_number definitivo del servidor
    await db.updateBatchAfterSync(item.lote_id, lote.server_id, result.trace_number);
  }
}

// Exportar singleton
export const syncManager = new SyncManager();
