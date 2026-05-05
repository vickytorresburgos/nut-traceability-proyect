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

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? 'http://192.168.100.10:8080';
const MAX_ATTEMPTS = 5;
const BASE_BACKOFF_MS = 2_000; // 2s * 2^attempt

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

type Operation = 'CREATE_BATCH' | 'ADD_OVEN' | 'ADD_CALIBER';

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
    if (!netState.isConnected || !netState.isInternetReachable) return;

    this.isSyncing = true;
    console.log('[SyncManager] Iniciando sincronización...');

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
      switch (item.operation as Operation) {
        case 'CREATE_BATCH':
          await this.createBatch(item);
          break;
        case 'ADD_OVEN':
          await this.addOven(item);
          break;
        case 'ADD_CALIBER':
          await this.addCaliber(item);
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

  private async createBatch(item: SyncQueueItem): Promise<void> {
    const captura = await db.getCapturaByType(item.lote_id, 'remito');
    if (!captura) throw new Error('Captura de remito no encontrada');

    await this.verifyImageIntegrity(captura);

    const form = new FormData();
    form.append('remito_image', {
      uri: captura.local_path,
      name: 'remito.jpg',
      type: 'image/jpeg',
    } as any);

    const res = await fetch(`${API_BASE}/api/v1/batches`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);

    const { batch_id, trace_number } = await res.json();
    await db.updateBatchAfterSync(item.lote_id, batch_id, trace_number);
  }

  private async addOven(item: SyncQueueItem): Promise<void> {
    const lote = await db.getBatchById(item.lote_id);
    if (!lote?.server_id) throw new Error('server_id aún no disponible, esperar CREATE_BATCH');

    const captura = await db.getCapturaByType(item.lote_id, 'oven');
    if (!captura) throw new Error('Captura de horno no encontrada');

    await this.verifyImageIntegrity(captura);

    const form = new FormData();
    form.append('oven_image', {
      uri: captura.local_path,
      name: 'oven.jpg',
      type: 'image/jpeg',
    } as any);

    const res = await fetch(`${API_BASE}/api/v1/batches/${lote.server_id}/oven`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }

  private async addCaliber(item: SyncQueueItem): Promise<void> {
    const lote = await db.getBatchById(item.lote_id);
    if (!lote?.server_id) throw new Error('server_id aún no disponible');

    const captura = await db.getCapturaByType(item.lote_id, 'caliber');
    if (!captura) throw new Error('Captura de calibre no encontrada');

    await this.verifyImageIntegrity(captura);

    const form = new FormData();
    form.append('caliber_image', {
      uri: captura.local_path,
      name: 'caliber.jpg',
      type: 'image/jpeg',
    } as any);

    const res = await fetch(`${API_BASE}/api/v1/batches/${lote.server_id}/caliber`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
}

// Exportar singleton
export const syncManager = new SyncManager();
