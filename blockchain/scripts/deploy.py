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
from dotenv import load_dotenv

# Cargar variables desde el .env de la raíz
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# ── Configuración ─────────────────────────────────────────────────────────────
RPC_URL = os.environ.get("BLOCKCHAIN_RPC_URL")
PRIVATE_KEY = os.environ.get("BLOCKCHAIN_DEPLOYER_PRIVATE_KEY")

if not RPC_URL or not PRIVATE_KEY:
    print(f"ERROR: Variables no encontradas. RPC_URL: {RPC_URL}, KEY: {'SET' if PRIVATE_KEY else 'MISSING'}")
    sys.exit(1)

# Limpiar espacios en blanco
RPC_URL = RPC_URL.strip()
PRIVATE_KEY = PRIVATE_KEY.strip()

# Normalizar hosts para evitar problemas de resolución entre Docker y Host
if "localhost" in RPC_URL:
    RPC_URL = RPC_URL.replace("localhost", "127.0.0.1")
elif "host.docker.internal" in RPC_URL:
    RPC_URL = RPC_URL.replace("host.docker.internal", "127.0.0.1")
elif "besu-node-1" in RPC_URL:
    RPC_URL = RPC_URL.replace("besu-node-1", "127.0.0.1")

# ── Conexión ──────────────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

try:
    block_number = w3.eth.block_number
    print(f"Conectado a la red. Bloque actual: {block_number}")
except Exception as e:
    print(f"ERROR: No se puede conectar a {RPC_URL}. Detalle: {e}")
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

# Soporte para EIP-1559 (redes públicas como Polygon Amoy)
try:
    max_priority_fee = w3.eth.max_priority_fee
    base_fee = w3.eth.get_block('latest')['baseFeePerGas']
    max_fee = base_fee * 2 + max_priority_fee
    
    print(f"Gas Dinámico (EIP-1559):")
    print(f"   Max Priority Fee: {w3.from_wei(max_priority_fee, 'gwei')} Gwei")
    print(f"   Max Fee: {w3.from_wei(max_fee, 'gwei')} Gwei")
    
    tx_params = {
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 700_000,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority_fee,
        "chainId": w3.eth.chain_id
    }
except Exception as e:
    print(f"Advertencia: No se pudo obtener gas EIP-1559 ({e}). Usando fallback legacy.")
    gas_price = w3.eth.gas_price
    if gas_price == 0:
        gas_price = w3.to_wei(1, 'gwei')
    tx_params = {
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 1_500_000,
        "gasPrice": gas_price,
        "chainId": w3.eth.chain_id
    }

print(f"Enviando transacción de despliegue...")
tx = Contract.constructor().build_transaction(tx_params)

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
