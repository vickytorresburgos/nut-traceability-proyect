export interface NutBatch {
  id: string;
  trace_number: string | null;
  server_id: number | null;
  status: 'PENDING' | 'SYNCED' | 'ERROR';
  farm_name: string | null;
  harvest_type: string | null;
  remito_date: string | null;
  remito_image_url: string | null;
  oven_id: string | null;
  humidity: string | null;
  oven_image_url: string | null;
  caliber: string | null;
  weight: string | null;
  caliber_image_url: string | null;
  sha256_hash: string | null;
  operator_id: string | null;
  created_at: string;
  synced_at: string | null;
}

export interface Captura {
  id: string;
  lote_id: string;
  type: 'remito' | 'oven' | 'caliber';
  local_path: string;
  sha256_hash: string;
  ocr_raw_text: string | null;
  ocr_confidence: number | null;
  captured_at: string;
}

export interface SyncQueueItem {
  id: string;
  lote_id: string;
  operation: 'CREATE_BATCH' | 'ADD_OVEN' | 'ADD_CALIBER' | 'COMPLETE_BATCH';
  payload: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'DONE' | 'FAILED';
  attempt_count: number;
  last_attempt: string | null;
  error_message: string | null;
  created_at: string;
}
