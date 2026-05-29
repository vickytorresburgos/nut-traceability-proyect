import * as SQLite from 'expo-sqlite';
import { v4 as uuidv4 } from 'uuid';
import { SyncQueueItem } from './types';

export async function enqueue(db: SQLite.SQLiteDatabase, lote_id: string, operation: SyncQueueItem['operation'], payload: object): Promise<void> {
  await db.runAsync(
    `INSERT INTO sync_queue (id, lote_id, operation, payload, created_at)
     VALUES (?,?,?,?,?)`,
    [uuidv4(), lote_id, operation, JSON.stringify(payload), new Date().toISOString()]
  );
}

export async function getPendingItems(db: SQLite.SQLiteDatabase): Promise<SyncQueueItem[]> {
  return db.getAllAsync<SyncQueueItem>(
    `SELECT * FROM sync_queue
     WHERE status IN ('PENDING','IN_PROGRESS') AND attempt_count < 5
     ORDER BY created_at ASC`
  );
}

export async function setSyncItemStatus(db: SQLite.SQLiteDatabase, id: string, status: SyncQueueItem['status'], error?: string): Promise<void> {
  await db.runAsync(
    `UPDATE sync_queue SET status=?, error_message=?, last_attempt=? WHERE id=?`,
    [status, error ?? null, new Date().toISOString(), id]
  );
}

export async function incrementSyncAttempt(db: SQLite.SQLiteDatabase, id: string, error: string): Promise<void> {
  await db.runAsync(
    `UPDATE sync_queue
     SET attempt_count = attempt_count + 1,
         status = 'PENDING',
         error_message = ?,
         last_attempt = ?
     WHERE id = ?`,
    [error, new Date().toISOString(), id]
  );
}
