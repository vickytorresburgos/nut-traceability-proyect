/**
 * database.ts — Persistencia local SQLite (expo-sqlite)
 *
 * La tabla local `nut_batches` espeja EXACTAMENTE la tabla PostgreSQL del backend,
 * más dos tablas propias del cliente:
 *   - `capturas`   → imágenes originales en disco + hash SHA-256
 *   - `sync_queue` → operaciones pendientes de subir al servidor
 *
 * Separación de responsabilidades:
 *   UI Layer   → hooks/stores de React (NO acceden a SQLite directamente)
 *   Data Layer → este módulo (db.*) es el único punto de acceso a SQLite
 */

import * as SQLite from 'expo-sqlite';
import * as Crypto from 'expo-crypto';
import * as FileSystem from 'expo-file-system/legacy';
import 'react-native-get-random-values';
import { v4 as uuidv4 } from 'uuid';

// ---------------------------------------------------------------------------
// Tipos — espejo de NutBatch (database.py) + campos móviles
// ---------------------------------------------------------------------------

export interface NutBatch {
  /** UUID local (string). Al sincronizar, server_id es el INTEGER del backend. */
  id: string;
  trace_number: string | null;       // "LF-01" provisional o definitivo
  server_id: number | null;          // id INTEGER asignado por nut-api tras sync
  status: 'PENDING' | 'SYNCED' | 'ERROR';  // local tracking

  // Fase 1 — Remito
  farm_name: string | null;
  harvest_type: string | null;       // 'manual' | 'mecanica'
  remito_date: string | null;
  remito_image_url: string | null;   // URL MinIO tras sync (null si offline)

  // Fase 2 — Secadero
  oven_id: string | null;
  humidity: string | null;
  oven_image_url: string | null;

  // Fase 3 — Calibrado
  caliber: string | null;
  weight: string | null;
  caliber_image_url: string | null;

  // Sellado
  sha256_hash: string | null;
  created_at: string;
  synced_at: string | null;
}

export interface Captura {
  id: string;
  lote_id: string;                   // referencia a nut_batches.id (local UUID)
  type: 'remito' | 'oven' | 'caliber';
  local_path: string;                // path en DocumentDirectory (bytes sin re-comprimir)
  sha256_hash: string;               // calculado al guardar, verificado al subir
  ocr_raw_text: string | null;
  ocr_confidence: number | null;
  captured_at: string;
}

export interface SyncQueueItem {
  id: string;
  lote_id: string;
  operation: 'CREATE_BATCH' | 'ADD_OVEN' | 'ADD_CALIBER';
  payload: string;                   // JSON serializado
  status: 'PENDING' | 'IN_PROGRESS' | 'DONE' | 'FAILED';
  attempt_count: number;
  last_attempt: string | null;
  error_message: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Database class
// ---------------------------------------------------------------------------

class Database {
  private _db: SQLite.SQLiteDatabase | null = null;

  private get conn(): SQLite.SQLiteDatabase {
    if (!this._db) throw new Error('Database not initialized. Call db.open() first.');
    return this._db;
  }

  async open(): Promise<void> {
    this._db = await SQLite.openDatabaseAsync('nut_traceability.db');
    await this._migrate();
  }

  /** Migraciones idempotentes — safe to run on every app start */
  private async _migrate(): Promise<void> {
    await this.conn.execAsync(`
      PRAGMA journal_mode = WAL;
      PRAGMA foreign_keys = ON;

      -- Espejo de la tabla PostgreSQL nut_batches + columnas móviles
      CREATE TABLE IF NOT EXISTS nut_batches (
        id                TEXT PRIMARY KEY,
        trace_number      TEXT UNIQUE,
        server_id         INTEGER,
        status            TEXT NOT NULL DEFAULT 'PENDING',

        farm_name         TEXT,
        harvest_type      TEXT,
        remito_date       TEXT,
        remito_image_url  TEXT,

        oven_id           TEXT,
        humidity          TEXT,
        oven_image_url    TEXT,

        caliber           TEXT,
        weight            TEXT,
        caliber_image_url TEXT,

        sha256_hash       TEXT,
        created_at        TEXT NOT NULL,
        synced_at         TEXT
      );

      -- Imágenes capturadas localmente (no existe en el backend)
      CREATE TABLE IF NOT EXISTS capturas (
        id              TEXT PRIMARY KEY,
        lote_id         TEXT NOT NULL REFERENCES nut_batches(id) ON DELETE CASCADE,
        type            TEXT NOT NULL,
        local_path      TEXT NOT NULL,
        sha256_hash     TEXT NOT NULL,
        ocr_raw_text    TEXT,
        ocr_confidence  REAL,
        captured_at     TEXT NOT NULL
      );

      -- Cola de sincronización (no existe en el backend)
      CREATE TABLE IF NOT EXISTS sync_queue (
        id            TEXT PRIMARY KEY,
        lote_id       TEXT NOT NULL REFERENCES nut_batches(id) ON DELETE CASCADE,
        operation     TEXT NOT NULL,
        payload       TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'PENDING',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_attempt  TEXT,
        error_message TEXT,
        created_at    TEXT NOT NULL
      );

      CREATE INDEX IF NOT EXISTS idx_batches_status ON nut_batches(status);
      CREATE INDEX IF NOT EXISTS idx_batches_created ON nut_batches(created_at);
      CREATE INDEX IF NOT EXISTS idx_capturas_lote ON capturas(lote_id, type);
      CREATE INDEX IF NOT EXISTS idx_queue_status ON sync_queue(status, attempt_count);
    `);

    // Limpieza de datos sucios de versiones anteriores:
    // trace_number = '' o 'TMP-*' se revierten a NULL para evitar colisiones UNIQUE.
    // SQLite permite múltiples NULL en columnas UNIQUE.
    await this.conn.runAsync(
      `UPDATE nut_batches
       SET trace_number = NULL
       WHERE trace_number = '' OR trace_number LIKE 'TMP-%'`
    );
  }

  // ── nut_batches ─────────────────────────────────────────────────────────

  async createBatch(data: Pick<NutBatch, 'trace_number' | 'farm_name' | 'harvest_type' | 'remito_date'>): Promise<NutBatch> {
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
          caliber, weight, caliber_image_url, sha256_hash, created_at, synced_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [batch.id, batch.trace_number, batch.server_id, batch.status,
       batch.farm_name, batch.harvest_type, batch.remito_date, batch.remito_image_url,
       batch.oven_id, batch.humidity, batch.oven_image_url,
       batch.caliber, batch.weight, batch.caliber_image_url,
       batch.sha256_hash, batch.created_at, batch.synced_at]
    );
    return batch;
  }

  async getBatchById(id: string): Promise<NutBatch | null> {
    return this.conn.getFirstAsync<NutBatch>(
      'SELECT * FROM nut_batches WHERE id = ?', [id]
    );
  }

  /** Todos los lotes (para verificar unicidad de trace_number) */
  async getAllBatches(): Promise<NutBatch[]> {
    return this.conn.getAllAsync<NutBatch>(
      'SELECT * FROM nut_batches ORDER BY created_at DESC'
    );
  }

  /** Lotes creados hoy, orden descendente */
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

  /** Llamado tras CREATE_BATCH exitoso: guarda el server_id y trace_number definitivo */
  async updateBatchAfterSync(localId: string, serverId: number, traceNumber: string): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET server_id = ?, trace_number = ?, status = ?, synced_at = ? WHERE id = ?',
      [serverId, traceNumber, 'SYNCED', new Date().toISOString(), localId]
    );
  }

  /**
   * Actualiza solo los datos OCR del remito (farm_name, harvest_type, remito_date).
   * NO toca trace_number para evitar colisiones UNIQUE durante el procesamiento OCR.
   * Llamar inmediatamente después de recibir el resultado OCR (antes de confirmar).
   */
  async updateBatchOcrData(id: string, farm_name: string, harvest_type: string, remito_date: string): Promise<void> {
    await this.conn.runAsync(
      'UPDATE nut_batches SET farm_name = ?, harvest_type = ?, remito_date = ? WHERE id = ?',
      [farm_name, harvest_type, remito_date, id]
    );
  }

  /**
   * Actualiza todos los datos del remito incluyendo el trace_number definitivo.
   * Llamar solo en el momento en que el operario confirma los datos (save()).
   */
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

  // ── capturas ─────────────────────────────────────────────────────────────

  /**
   * Guarda la imagen en DocumentDirectory SIN re-comprimir (preserva calidad)
   * y almacena ruta + SHA-256 en SQLite para verificación pre-upload.
   */
  async saveCaptura(
    lote_id: string,
    type: Captura['type'],
    imageUri: string,
    ocr_raw_text?: string,
    ocr_confidence?: number
  ): Promise<Captura> {
    // 1. Copiar bytes originales al directorio persistente
    // @ts-ignore - documentDirectory missing from expo-file-system types
    const destDir = `${FileSystem.documentDirectory}capturas/${lote_id}/`;
    // @ts-ignore - 'intermediates' is valid at runtime but missing from expo-file-system's MakeDirectoryOptions
    await FileSystem.makeDirectoryAsync(destDir, { intermediates: true });
    const destPath = `${destDir}${type}_${Date.now()}.jpg`;
    await FileSystem.copyAsync({ from: imageUri, to: destPath });

    // 2. Calcular SHA-256 sobre base64 (integridad en reposo)
    const b64 = await FileSystem.readAsStringAsync(destPath, {
      // @ts-ignore - EncodingType missing from expo-file-system types
      encoding: FileSystem.EncodingType.Base64,
    });
    const sha256_hash = await Crypto.digestStringAsync(
      Crypto.CryptoDigestAlgorithm.SHA256,
      b64
    );

    const captura: Captura = {
      id: uuidv4(),
      lote_id,
      type,
      local_path: destPath,
      sha256_hash,
      ocr_raw_text: ocr_raw_text ?? null,
      ocr_confidence: ocr_confidence ?? null,
      captured_at: new Date().toISOString(),
    };

    await this.conn.runAsync(
      `INSERT INTO capturas VALUES (?,?,?,?,?,?,?,?)`,
      [captura.id, captura.lote_id, captura.type, captura.local_path,
       captura.sha256_hash, captura.ocr_raw_text, captura.ocr_confidence, captura.captured_at]
    );
    return captura;
  }

  async getCapturaByType(lote_id: string, type: string): Promise<Captura | null> {
    return this.conn.getFirstAsync<Captura>(
      'SELECT * FROM capturas WHERE lote_id = ? AND type = ?', [lote_id, type]
    );
  }

  // ── sync_queue ───────────────────────────────────────────────────────────

  async enqueue(lote_id: string, operation: SyncQueueItem['operation'], payload: object): Promise<void> {
    await this.conn.runAsync(
      `INSERT INTO sync_queue (id, lote_id, operation, payload, created_at)
       VALUES (?,?,?,?,?)`,
      [uuidv4(), lote_id, operation, JSON.stringify(payload), new Date().toISOString()]
    );
  }

  async getPendingItems(): Promise<SyncQueueItem[]> {
    return this.conn.getAllAsync<SyncQueueItem>(
      `SELECT * FROM sync_queue
       WHERE status IN ('PENDING','IN_PROGRESS') AND attempt_count < 5
       ORDER BY created_at ASC`
    );
  }

  async setSyncItemStatus(id: string, status: SyncQueueItem['status'], error?: string): Promise<void> {
    await this.conn.runAsync(
      `UPDATE sync_queue SET status=?, error_message=?, last_attempt=? WHERE id=?`,
      [status, error ?? null, new Date().toISOString(), id]
    );
  }

  async incrementSyncAttempt(id: string, error: string): Promise<void> {
    await this.conn.runAsync(
      `UPDATE sync_queue
       SET attempt_count = attempt_count + 1,
           status = 'PENDING',
           error_message = ?,
           last_attempt = ?
       WHERE id = ?`,
      [error, new Date().toISOString(), id]
    );
  }
}

export const db = new Database();
