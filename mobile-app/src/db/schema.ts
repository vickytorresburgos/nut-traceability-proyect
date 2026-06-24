import * as SQLite from 'expo-sqlite';

export async function migrate(db: SQLite.SQLiteDatabase): Promise<void> {
  // Consolidamos toda la creación en un solo bloque para evitar múltiples llamadas al puente nativo
  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;

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
      operator_id       TEXT,
      created_at        TEXT NOT NULL,
      synced_at         TEXT
    );

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

  // Ejecutamos la migración de la columna operator_id de forma aislada
  // Solo si la tabla ya existía sin esa columna (fallback)
  try {
    const tableInfo = await db.getAllAsync<{name: string}>("PRAGMA table_info(nut_batches)");
    const columnExists = tableInfo.some(col => col.name === 'operator_id');
    
    if (!columnExists) {
      await db.execAsync("ALTER TABLE nut_batches ADD COLUMN operator_id TEXT;");
    }
  } catch (err) {
    // Si falla porque la tabla es nueva (ya tiene la columna), simplemente ignoramos
  }

  // Mantenimiento de datos
  try {
    await db.execAsync("UPDATE nut_batches SET trace_number = NULL WHERE trace_number = '' OR trace_number LIKE 'TMP-%';");
  } catch (e) {
    // No crítico
  }
}
