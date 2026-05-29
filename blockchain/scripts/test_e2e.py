#!/usr/bin/env python3
"""
Test E2E del módulo blockchain de trazabilidad.

Flujo real de la API (step-by-step):
  POST /api/v1/batches          → Fase 1: crea lote + sube remito
  POST /api/v1/batches/{id}/oven    → Fase 2: sube imagen de horno
  POST /api/v1/batches/{id}/caliber → Fase 3: sube imagen de calibre
  POST /api/v1/batches/{id}/complete → Finaliza + dispara anclaje blockchain
  GET  /api/v1/batches/by-trace/{trace}/verify → Verifica on-chain

Uso:
    python blockchain/scripts/test_e2e.py
"""
import io, struct, zlib, time, json
import requests

# ── Configuración ─────────────────────────────────────────────────────────────
BASE_URL = "http://localhost"
API_KEY  = "866d12031a902ee1899bde8e3bcf687827eb821d75f1d530ab3773dbb28959d5"
HEADERS  = {"X-API-Key": API_KEY}
SEP = "─" * 60

def step(n, title):
    print(f"\n{SEP}\n  PASO {n}: {title}\n{SEP}")

def ok(resp, expected=200):
    if resp.status_code != expected:
        print(f"  ❌ HTTP {resp.status_code}: {resp.text[:400]}")
        raise SystemExit(1)
    data = resp.json()
    print(f"  ✅ HTTP {resp.status_code}")
    return data

def make_png():
    """Crea una imagen PNG válida de 1×1 pixel (blanco)."""
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xFF\xFF\xFF'))
            + chunk(b'IEND', b''))

PNG = make_png()

# ════════════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*60}")
print("  TEST E2E — BLOCKCHAIN TRACEABILITY MODULE")
print(f"{'═'*60}")

# PASO 1 ── Health check ────────────────────────────────────────────────────────
step(1, "Health check")
data = ok(requests.get(f"{BASE_URL}/health", timeout=5))
print(f"  {data}")

# PASO 2 ── Crear lote + Fase 1 Remito ─────────────────────────────────────────
step(2, "Fase 1 — Remito (POST /api/v1/batches)")
r = requests.post(
    f"{BASE_URL}/api/v1/batches",
    headers=HEADERS,
    data={
        "farm_name":    "La Torre",
        "harvest_type": "manual",
        "remito_date":  "2024-11-15",
    },
    files={"remito_image": ("remito.png", PNG, "image/png")},
    timeout=30,
)
data = ok(r, 200)
batch_id = data["batch_id"]
print(f"  batch_id:   {batch_id}")
print(f"  farm_name:  {data['extracted_data']['farm_name']}")

# PASO 3 ── Fase 2 Horno ────────────────────────────────────────────────────────
step(3, "Fase 2 — Horno (POST /api/v1/batches/{id}/oven)")
r = requests.post(
    f"{BASE_URL}/api/v1/batches/{batch_id}/oven",
    headers=HEADERS,
    data={"oven_id": "H-07", "humidity": "12.5"},
    files={"oven_image": ("horno.png", PNG, "image/png")},
    timeout=30,
)
data = ok(r)
print(f"  oven_id:  {data['extracted_data'].get('oven_id', 'H-07')}")
print(f"  humidity: {data['extracted_data'].get('humidity', '12.5')}")

# PASO 4 ── Fase 3 Calibre ──────────────────────────────────────────────────────
step(4, "Fase 3 — Calibre (POST /api/v1/batches/{id}/caliber)")
r = requests.post(
    f"{BASE_URL}/api/v1/batches/{batch_id}/caliber",
    headers=HEADERS,
    data={"caliber": "28", "weight": "1250"},
    files={"caliber_image": ("calibre.png", PNG, "image/png")},
    timeout=30,
)
data = ok(r)
print(f"  caliber: {data['extracted_data'].get('caliber', '28')}")
print(f"  weight:  {data['extracted_data'].get('weight', '1250')}")

# PASO 5 ── Finalizar → dispara anclaje blockchain en background ─────────────────
step(5, "Finalizar lote → blockchain en background (POST /complete)")
r = requests.post(
    f"{BASE_URL}/api/v1/batches/{batch_id}/complete",
    headers=HEADERS,
    timeout=15,
)
data = ok(r)
trace_number = data["trace_number"]
sha256_hash  = data["hash"]
print(f"  trace_number:      {trace_number}")
print(f"  sha256_hash:       {sha256_hash}")
print(f"  blockchain_status: {data.get('blockchain_status', 'N/A')}  ← anclaje en background")

# PASO 6 ── Esperar anclaje blockchain ─────────────────────────────────────────
step(6, "Esperar anclaje on-chain (background task, máx 30s)")
tx_hash = None
for i in range(10):
    time.sleep(3)
    r = requests.get(f"{BASE_URL}/api/v1/batches/by-trace/{trace_number}/verify", timeout=10)
    vdata = r.json() if r.status_code == 200 else {}
    tx_hash = vdata.get("blockchain_tx_hash")
    if tx_hash:
        print(f"  ✅ Anclado en intento {i+1}/10 ({(i+1)*3}s)")
        break
    print(f"  ⏳ Intento {i+1}/10 — aún pendiente...")

# PASO 7 ── Verificación final ──────────────────────────────────────────────────
step(7, "Verificación on-chain (GET /by-trace/{trace}/verify)")
r = requests.get(f"{BASE_URL}/api/v1/batches/by-trace/{trace_number}/verify", timeout=10)
result = ok(r)

print(f"\n  ┌─ RESULTADO ────────────────────────────────────")
print(f"  │  trace_number:      {result['trace_number']}")
print(f"  │  sha256_hash:       {result['sha256_hash']}")
print(f"  │  blockchain_tx_hash:{result['blockchain_tx_hash']}")
print(f"  │  anchored:          {result['blockchain_anchored']}")
print(f"  │  anchored_at:       {result['blockchain_anchored_at']}")

verif = result.get("blockchain_verification") or {}
if verif:
    print(f"  │")
    print(f"  │  [on-chain]  anchored: {verif.get('anchored')}  valid: {verif.get('valid')}")
    print(f"  │  [on-chain]  timestamp: {verif.get('anchor_timestamp')}")
print(f"  └────────────────────────────────────────────────")

# ── Conclusión ─────────────────────────────────────────────────────────────────
print(f"\n{'═'*60}")
anchored = result['blockchain_anchored']
valid    = verif.get('valid') if verif else None

if anchored and valid:
    print("  ✅ ÉXITO TOTAL — Módulo blockchain funcional")
    print(f"\n  sha256_hash        = huella de los DATOS del lote")
    print(f"  blockchain_tx_hash = ID de la TX en la red blockchain")
    print(f"  ¿Son iguales? → {result['sha256_hash'] == result['blockchain_tx_hash']} (siempre False)")
elif anchored and valid is None:
    print("  ⚠️  Lote anclado pero sin verificación on-chain (Ganache desconectado?)")
else:
    print("  ⚠️  Sin anclaje blockchain. Verificar:")
    print("      1. Ganache corriendo: ganache --port 8545 --host 0.0.0.0 --chain.hardfork london")
    print("      2. BLOCKCHAIN_ENABLED=true en .env")
    print("      3. BLOCKCHAIN_CONTRACT_ADDRESS configurado")
print(f"{'═'*60}\n")
