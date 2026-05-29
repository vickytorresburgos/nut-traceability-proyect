"""
BlockchainService: ancla hashes SHA-256 en el smart contract NutTraceability.

Distinción de hashes:
    sha256_hash        → huella SHA-256 del CONTENIDO del lote (generada por Python/hashlib)
                         Es lo que se almacena DENTRO de la transacción blockchain.
    blockchain_tx_hash → ID de la TRANSACCIÓN en la red Ethereum/Polygon
                         Lo genera la blockchain al confirmar. Permite buscar
                         la tx en Etherscan/Polygonscan.

Diseño:
    - Feature-flag: si BLOCKCHAIN_ENABLED=false, todas las llamadas son no-op.
    - Asíncrono: usa run_in_executor para no bloquear el event loop de FastAPI.
    - Tolerante a fallos: si la blockchain falla, el lote queda COMPLETED igualmente.
    - Idempotente: verifica en el contrato si el hash ya fue anclado antes de enviar.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nut-api.blockchain")

# ── ABI cacheado ──────────────────────────────────────────────────────────────
_ABI_CACHE: Optional[list] = None


def _load_abi() -> list:
    global _ABI_CACHE
    if _ABI_CACHE is not None:
        return _ABI_CACHE

    # Orden de búsqueda:
    # 1. Junto al blockchain_service.py → funciona dentro del contenedor Docker (/app/)
    # 2. En blockchain/build/ relativo a la raíz del proyecto → funciona en desarrollo local
    candidates = [
        Path(__file__).parent / "NutTraceability.json",
        Path(__file__).parent.parent / "blockchain" / "build" / "NutTraceability.json",
    ]
    artifact_path = next((p for p in candidates if p.exists()), None)
    if artifact_path is None:
        raise FileNotFoundError(
            f"ABI no encontrado. Rutas buscadas:\n"
            + "\n".join(f"  {p}" for p in candidates)
            + "\nCompilar con: python blockchain/scripts/compile.py"
        )
    with open(artifact_path) as f:
        _ABI_CACHE = json.load(f)["abi"]
    logger.info(f"ABI cargado desde: {artifact_path}")
    return _ABI_CACHE


# ── Servicio ──────────────────────────────────────────────────────────────────
class BlockchainService:
    """
    Servicio de anclaje blockchain para el módulo de trazabilidad.

    Se instancia una vez como singleton al arrancar FastAPI.
    Si BLOCKCHAIN_ENABLED=false, todos los métodos son no-op seguros.
    """

    def __init__(self):
        self.enabled = os.getenv("BLOCKCHAIN_ENABLED", "false").lower() == "true"

        if not self.enabled:
            logger.info(
                "BlockchainService deshabilitado (BLOCKCHAIN_ENABLED=false). "
                "El flujo de trazabilidad funciona con normalidad sin blockchain."
            )
            return

        # Importación lazy: web3 solo se carga si blockchain está habilitado
        try:
            from web3 import Web3
            from web3.middleware import ExtraDataToPOAMiddleware
        except ImportError:
            raise ImportError(
                "web3 no instalado. Agregar 'web3>=7.0.0' a requirements.txt "
                "o deshabilitar con BLOCKCHAIN_ENABLED=false."
            )

        rpc_url = os.environ.get("BLOCKCHAIN_RPC_URL")
        if not rpc_url:
            raise ValueError("BLOCKCHAIN_RPC_URL no definido en las variables de entorno.")

        self._Web3 = Web3
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Middleware necesario para redes PoA: Ganache y Polygon
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self.w3.is_connected():
            raise RuntimeError(
                f"No se puede conectar a la blockchain en {rpc_url}. "
                "Verificar que Ganache/nodo esté corriendo."
            )

        private_key = os.environ.get("BLOCKCHAIN_DEPLOYER_PRIVATE_KEY")
        if not private_key:
            raise ValueError("BLOCKCHAIN_DEPLOYER_PRIVATE_KEY no definido.")

        self.account = self.w3.eth.account.from_key(private_key)

        contract_address = os.environ.get("BLOCKCHAIN_CONTRACT_ADDRESS")
        if not contract_address:
            raise ValueError(
                "BLOCKCHAIN_CONTRACT_ADDRESS no definido. "
                "Ejecutar blockchain/scripts/deploy.py primero."
            )

        abi = _load_abi()
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi,
        )

        chain_id = os.getenv("BLOCKCHAIN_CHAIN_ID", "1337")
        logger.info(
            f"BlockchainService inicializado. "
            f"Red: chain_id={chain_id} | "
            f"Contrato: {contract_address} | "
            f"Cuenta: {self.account.address}"
        )

    def _sha256_hex_to_bytes32(self, hex_hash: str) -> bytes:
        """
        Convierte el sha256_hash hexadecimal (64 chars) a bytes32 para el contrato.

        El sha256_hash en DB es el hash del CONTENIDO del lote (ej: "a3f4c9d2...").
        El contrato lo recibe como bytes32 (tipo nativo de Solidity para hashes).
        """
        return bytes.fromhex(hex_hash)

    async def anchor_hash(
        self, trace_number: str, sha256_hash: str
    ) -> Optional[str]:
        """
        Ancla el sha256_hash del lote en el contrato NutTraceability.

        Args:
            trace_number: Identificador del lote (ej: "LT-001")
            sha256_hash:  Hash SHA-256 del contenido del lote (64 chars hex)

        Returns:
            blockchain_tx_hash (str): ID de la transacción confirmada, ej "0x7b3a..."
            None si blockchain está deshabilitada o si hubo un error.

        Nota: Este método se llama desde BackgroundTasks — no bloquea la respuesta
              al móvil. Si falla, el lote permanece COMPLETED; solo falta el anclaje.
        """
        if not self.enabled:
            return None

        try:
            # ── Idempotencia: no reenviar si ya fue anclado ───────────────────
            _hash_bytes32, _ts, exists = self.contract.functions.getAnchor(
                trace_number
            ).call()
            if exists:
                logger.info(
                    f"[Blockchain] {trace_number} ya anclado. Omitiendo transacción."
                )
                return None

            # ── Construir y firmar la transacción ─────────────────────────────
            hash_bytes = self._sha256_hex_to_bytes32(sha256_hash)
            nonce = self.w3.eth.get_transaction_count(self.account.address)

            tx = self.contract.functions.anchorHash(
                trace_number, hash_bytes
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 100_000,
                "gasPrice": self.w3.eth.gas_price,
            })

            signed = self.account.sign_transaction(tx)
            raw_tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)

            # ── Esperar confirmación sin bloquear el event loop ───────────────
            loop = asyncio.get_event_loop()
            receipt = await loop.run_in_executor(
                None,
                lambda: self.w3.eth.wait_for_transaction_receipt(
                    raw_tx_hash, timeout=120
                ),
            )

            # blockchain_tx_hash: ID de la transacción (distinto del sha256_hash del lote)
            blockchain_tx_hash = receipt.transactionHash.hex()
            logger.info(
                f"[Blockchain] Hash anclado exitosamente. "
                f"Traza: {trace_number} | "
                f"sha256_hash (payload): {sha256_hash[:16]}... | "
                f"blockchain_tx_hash (ID de tx): {blockchain_tx_hash[:16]}..."
            )
            return blockchain_tx_hash

        except Exception:
            logger.exception(
                f"[Blockchain] Error al anclar hash para {trace_number}. "
                "El lote permanece COMPLETED. El anclaje puede reintentarse."
            )
            return None

    async def verify_on_chain(
        self, trace_number: str, sha256_hash: str
    ) -> dict:
        """
        Verifica en el contrato si el sha256_hash del lote está anclado y es válido.

        Returns:
            dict con claves: anchored (bool), valid (bool), anchor_timestamp (int|None)
        """
        if not self.enabled:
            return {"anchored": False, "valid": False, "anchor_timestamp": None}

        try:
            hash_bytes = self._sha256_hex_to_bytes32(sha256_hash)
            is_valid, anchor_time = self.contract.functions.verifyHash(
                trace_number, hash_bytes
            ).call()
            return {
                "anchored": anchor_time > 0,
                "valid": is_valid,
                "anchor_timestamp": anchor_time if anchor_time > 0 else None,
            }
        except Exception:
            logger.exception(
                f"[Blockchain] Error al verificar hash para {trace_number}."
            )
            return {"anchored": False, "valid": False, "anchor_timestamp": None, "error": True}


# ── Singleton ─────────────────────────────────────────────────────────────────
_blockchain_service: Optional[BlockchainService] = None


def get_blockchain_service() -> BlockchainService:
    """Retorna el singleton de BlockchainService. Thread-safe para FastAPI."""
    global _blockchain_service
    if _blockchain_service is None:
        _blockchain_service = BlockchainService()
    return _blockchain_service
