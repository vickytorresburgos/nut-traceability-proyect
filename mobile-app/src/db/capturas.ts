import * as SQLite from 'expo-sqlite';
import * as Crypto from 'expo-crypto';
import * as FileSystem from 'expo-file-system/legacy';
import { v4 as uuidv4 } from 'uuid';
import { Captura } from './types';

export async function saveCaptura(
  db: SQLite.SQLiteDatabase,
  lote_id: string,
  type: Captura['type'],
  imageUri: string,
  ocr_raw_text?: string,
  ocr_confidence?: number
): Promise<Captura> {
  const oldCapturas = await db.getAllAsync<Captura>(
    `SELECT local_path FROM capturas WHERE lote_id = ? AND type = ?`, [lote_id, type]
  );
  for (const old of oldCapturas) {
    try {
      await FileSystem.deleteAsync(old.local_path, { idempotent: true });
    } catch (e) {}
  }

  await db.runAsync(`DELETE FROM capturas WHERE lote_id = ? AND type = ?`, [lote_id, type]);
  
  if (type === 'remito') {
    await db.runAsync(`UPDATE nut_batches SET farm_name = NULL, harvest_type = NULL, remito_date = NULL WHERE id = ?`, [lote_id]);
  } else if (type === 'oven') {
    await db.runAsync(`UPDATE nut_batches SET oven_id = NULL, humidity = NULL WHERE id = ?`, [lote_id]);
  } else if (type === 'caliber') {
    await db.runAsync(`UPDATE nut_batches SET caliber = NULL, weight = NULL WHERE id = ?`, [lote_id]);
  }

  // @ts-ignore
  const destDir = `${FileSystem.documentDirectory}capturas/${lote_id}/`;
  // @ts-ignore
  await FileSystem.makeDirectoryAsync(destDir, { intermediates: true });
  const destPath = `${destDir}${type}_${Date.now()}.jpg`;
  await FileSystem.copyAsync({ from: imageUri, to: destPath });

  const b64 = await FileSystem.readAsStringAsync(destPath, {
    // @ts-ignore
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

  await db.runAsync(
    `INSERT INTO capturas VALUES (?,?,?,?,?,?,?,?)`,
    [captura.id, captura.lote_id, captura.type, captura.local_path,
     captura.sha256_hash, captura.ocr_raw_text, captura.ocr_confidence, captura.captured_at]
  );
  return captura;
}

export async function getCapturaByType(db: SQLite.SQLiteDatabase, lote_id: string, type: string): Promise<Captura | null> {
  return db.getFirstAsync<Captura>(
    'SELECT * FROM capturas WHERE lote_id = ? AND type = ?', [lote_id, type]
  );
}
