import * as SQLite from 'expo-sqlite';
import 'react-native-get-random-values';
import { v4 as uuidv4 } from 'uuid';
import { NutBatch, Captura, SyncQueueItem } from './types';
import { migrate } from './schema';
import * as syncQueue from './syncQueue';
import * as capturas from './capturas';

class Database {
  private _db: SQLite.SQLiteDatabase | null = null;

  private get conn(): SQLite.SQLiteDatabase {
    if (!this._db) throw new Error('Database not initialized. Call db.open() first.');
    return this._db;
  }

  async open(): Promise<void> {
    this._db = await SQLite.openDatabaseAsync('nut_traceability.db');
    await migrate(this.conn);
  }

  // ── nut_batches Operations ──────────────────────────────────────────────

  async createBatch(data: Pick<NutBatch, 'trace_number' | 'farm_name' | 'harvest_type' | 'remito_date' | 'operator_id'>): Promise<NutBatch> {
    const batch: NutBatch = {
      id: uuidv4(),
      ...data,
      server_id: null,
      status: 'PENDING',
      remito_image_url: null,
      oven_id: null, humidity: null, oven_image_url: null,
      caliber: null, weight: null, caliber_image_url: null,
      sha256_hash: null,
      created_at: new Date().toISOString(),
      synced_at: null,
    };
    await this.conn.runAsync(
      `INSERT INTO nut_batches
         (id, trace_number, server_id, status, farm_name, harvest_type,
          remito_date, remito_image_url, oven_id, humidity, oven_image_url,
          caliber, weight, caliber_image_url, sha256_hash, operator_id, created_at, synced_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [batch.id, batch.trace_number, batch.server_id, batch.status,
       batch.farm_name, batch.harvest_type, batch.remito_date, batch.remito_image_url,
       batch.oven_id, batch.humidity, batch.oven_image_url,
       batch.caliber, batch.weight, batch.caliber_image_url,
       batch.sha256_hash, batch.operator_id, batch.created_at, batch.synced_at]
    );
    return batch;
  }

  async getBatchById(id: string): Promise<NutBatch | null> {
    return this.conn.getFirstAsync<NutBatch>(
      'SELECT * FROM nut_batches WHERE id = ?', [id]
    );
  }

  async getAllBatches(): Promise<NutBatch[]> {
    return this.conn.getAllAsync<NutBatch>(
      'SELECT * FROM nut_batches ORDER BY created_at DESC'
    );
  }

  async getBatchesForUser(username: string): Promise<NutBatch[]> {
    if (username === 'admin') {
      return this.getAllBatches();
    }
    return this.conn.getAllAsync<NutBatch>(
      'SELECT * FROM nut_batches WHERE operator_id = ? ORDER BY created_at DESC',
      [username]
    );
  }

  async getBatchesForToday(): Promise<NutBatch[]> {
    const today = new Date().toISOString().slice(0, 10);
    return this.conn.getAllAsync<NutBatch>(
      `SELECT * FROM nut_batches WHERE created_at LIKE ? ORDER BY created_at DESC`,
      [`${today}%`]
    );
  }

  async updateBatchStatus(id: string, status: NutBatch['status'], synced_at?: string): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET status = ?, synced_at = ? WHERE id = ?',
      [status, synced_at ?? null, id]
    );
  }

  async updateBatchAfterSync(localId: string, serverId: number | null, traceNumber: string | null): Promise<void> {
    if (traceNumber) {
      await this.conn.runAsync(
        'UPDATE nut_batches SET trace_number = NULL WHERE trace_number = ? AND id != ?',
        [traceNumber, localId]
      );
    }

    await this.conn.runAsync(
      'UPDATE nut_batches SET server_id = ?, trace_number = ?, status = ?, synced_at = ? WHERE id = ?',
      [serverId, traceNumber, 'SYNCED', new Date().toISOString(), localId]
    );
  }

  async updateBatchOcrData(id: string, farm_name: string, harvest_type: string, remito_date: string): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET farm_name = ?, harvest_type = ?, remito_date = ? WHERE id = ?',
      [farm_name, harvest_type, remito_date, id]
    );
  }

  async updateBatchDetails(id: string, farm_name: string, harvest_type: string, remito_date: string, trace_number: string | null): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET farm_name = ?, harvest_type = ?, remito_date = ?, trace_number = ? WHERE id = ?',
      [farm_name, harvest_type, remito_date, trace_number, id]
    );
  }

  async updateBatchOven(id: string, oven_id: string, humidity: string): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET oven_id = ?, humidity = ? WHERE id = ?',
      [oven_id, humidity, id]
    );
  }

  async updateBatchCaliber(id: string, caliber: string, weight: string, sha256_hash?: string): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET caliber = ?, weight = ?, sha256_hash = ? WHERE id = ?',
      [caliber, weight, sha256_hash ?? null, id]
    );
  }

  // ── Proxy methods to sub-modules ────────────────────────────────────────

  async saveCaptura(lote_id: string, type: Captura['type'], imageUri: string, ocr_raw_text?: string, ocr_confidence?: number): Promise<Captura> {
    return capturas.saveCaptura(this.conn, lote_id, type, imageUri, ocr_raw_text, ocr_confidence);
  }

  async getCapturaByType(lote_id: string, type: string): Promise<Captura | null> {
    return capturas.getCapturaByType(this.conn, lote_id, type);
  }

  async enqueue(lote_id: string, operation: SyncQueueItem['operation'], payload: object): Promise<void> {
    return syncQueue.enqueue(this.conn, lote_id, operation, payload);
  }

  async getPendingItems(): Promise<SyncQueueItem[]> {
    return syncQueue.getPendingItems(this.conn);
  }

  async setSyncItemStatus(id: string, status: SyncQueueItem['status'], error?: string): Promise<void> {
    return syncQueue.setSyncItemStatus(this.conn, id, status, error);
  }

  async incrementSyncAttempt(id: string, error: string): Promise<void> {
    return syncQueue.incrementSyncAttempt(this.conn, id, error);
  }
}

export const db = new Database();
export * from './types';
