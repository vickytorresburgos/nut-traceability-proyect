"""
Script de deploy del contrato NutTraceability.

Uso (Ganache local):
    # 1. Iniciar Ganache con hardfork london (compatible con web3.py):
    ganache --deterministic --port 8545 --chain.hardfork london

    # 2. En otra terminal, ejecutar este script:
    BLOCKCHAIN_RPC_URL=http://localhost:8545 \
    BLOCKCHAIN_DEPLOYER_PRIVATE_KEY=0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d \
    python blockchain/scripts/deploy.py

IMPORTANTE: El contrato solo existe mientras Ganache esté corriendo.
            Para producción usar Polygon Amoy o Mainnet.

El contrato compilado debe estar en blockchain/build/NutTraceability.json.
Generar con: python blockchain/scripts/compile.py
"""
import json
import os
import sys
from pathlib import Path

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# ── Configuración ─────────────────────────────────────────────────────────────
RPC_URL = os.environ.get("BLOCKCHAIN_RPC_URL")
PRIVATE_KEY = os.environ.get("BLOCKCHAIN_DEPLOYER_PRIVATE_KEY")

if not RPC_URL or not PRIVATE_KEY:
    print("ERROR: Definir BLOCKCHAIN_RPC_URL y BLOCKCHAIN_DEPLOYER_PRIVATE_KEY")
    sys.exit(1)

# ── Conexión ──────────────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

if not w3.is_connected():
    print(f"ERROR: No se puede conectar a {RPC_URL}")
    sys.exit(1)

account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"Desplegando desde: {account.address}")
print(f"Balance: {w3.from_wei(w3.eth.get_balance(account.address), 'ether')} ETH")

# ── Cargar artefacto compilado ────────────────────────────────────────────────
artifact_path = Path(__file__).parent.parent / "build" / "NutTraceability.json"
if not artifact_path.exists():
    print(f"ERROR: No se encontró {artifact_path}")
    print("Compilar primero con Remix IDE y guardar el ABI+bytecode en blockchain/build/")
    sys.exit(1)

with open(artifact_path) as f:
    artifact = json.load(f)

abi = artifact["abi"]
bytecode = artifact["bytecode"]

# ── Deploy ────────────────────────────────────────────────────────────────────
Contract = w3.eth.contract(abi=abi, bytecode=bytecode)

tx = Contract.constructor().build_transaction({
    "from": account.address,
    "nonce": w3.eth.get_transaction_count(account.address),
    "gas": 600_000,
    "gasPrice": w3.eth.gas_price,
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"Transacción enviada: {tx_hash.hex()}")
print("Esperando confirmación...")

receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

print(f"\n✅ Contrato desplegado exitosamente!")
print(f"   Dirección: {receipt.contractAddress}")
print(f"   Gas usado: {receipt.gasUsed}")
print(f"\nAgregar a .env y nut-api/.env:")
print(f"   BLOCKCHAIN_CONTRACT_ADDRESS={receipt.contractAddress}")
