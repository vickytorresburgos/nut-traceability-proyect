// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title NutTraceability
 * @notice Notario digital para trazabilidad de nueces.
 *         Almacena hashes SHA-256 de lotes ya validados off-chain.
 *
 * @dev Arquitectura Off-Chain/On-Chain:
 *      - Los datos completos (farm, humidity, caliber...) viven en PostgreSQL/MinIO.
 *      - Este contrato solo recibe la huella criptográfica (32 bytes) del lote.
 *      - El sha256_hash se convierte a bytes32 antes de llamar a anchorHash().
 *
 *      Flujo:
 *        finalize_batch() → sha256_hash (Python) → anchorHash() → evento HashAnchored
 *        El tx hash resultante se guarda en DB como blockchain_tx_hash.
 */
contract NutTraceability {

    // ── Estado ────────────────────────────────────────────────────────────────
    address public owner;

    struct BatchAnchor {
        bytes32 sha256Hash;  // huella SHA-256 del contenido del lote
        uint256 timestamp;   // timestamp UNIX del bloque de confirmación
        bool exists;         // flag de existencia para idempotencia
    }

    // traceNumber (ej: "LT-001") → datos del anclaje
    mapping(string => BatchAnchor) private anchors;

    // ── Eventos ───────────────────────────────────────────────────────────────
    /**
     * @notice Emitido al anclar un hash exitosamente.
     *         Los exploradores blockchain indexan estos eventos para auditoria.
     */
    event HashAnchored(
        string indexed traceNumber,
        bytes32 sha256Hash,
        uint256 timestamp
    );

    // ── Modificadores ─────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "Solo el propietario puede anclar hashes");
        _;
    }

    modifier notAlreadyAnchored(string calldata traceNumber) {
        require(!anchors[traceNumber].exists, "Hash ya anclado para esta traza");
        _;
    }

    // ── Constructor ───────────────────────────────────────────────────────────
    constructor() {
        owner = msg.sender;
    }

    // ── Funciones de escritura ────────────────────────────────────────────────

    /**
     * @notice Ancla el hash SHA-256 de un lote identificado por traceNumber.
     * @param traceNumber  Identificador único del lote (ej: "LT-001")
     * @param sha256Hash   Hash SHA-256 del lote en formato bytes32
     *
     * @dev El caller debe ser el owner (cuenta de deploy de nut-api).
     *      Una vez anclado, el hash es inmutable — no se puede sobreescribir.
     */
    function anchorHash(
        string calldata traceNumber,
        bytes32 sha256Hash
    ) external onlyOwner notAlreadyAnchored(traceNumber) {
        anchors[traceNumber] = BatchAnchor({
            sha256Hash: sha256Hash,
            timestamp: block.timestamp,
            exists: true
        });
        emit HashAnchored(traceNumber, sha256Hash, block.timestamp);
    }

    // ── Funciones de lectura (view — sin costo de gas) ────────────────────────

    /**
     * @notice Verifica si el hash de un lote está anclado y coincide.
     * @param traceNumber  Número de traza a verificar
     * @param sha256Hash   Hash a comparar contra el almacenado
     * @return isValid      true si el hash coincide exactamente con el anclado
     * @return anchorTime   timestamp UNIX del bloque de anclaje (0 si no existe)
     */
    function verifyHash(
        string calldata traceNumber,
        bytes32 sha256Hash
    ) external view returns (bool isValid, uint256 anchorTime) {
        BatchAnchor memory anchor = anchors[traceNumber];
        isValid = anchor.exists && anchor.sha256Hash == sha256Hash;
        anchorTime = anchor.timestamp;
    }

    /**
     * @notice Devuelve el hash almacenado y metadatos para un número de traza.
     * @return sha256Hash  Hash anclado (bytes32 cero si no existe)
     * @return timestamp   Timestamp del anclaje
     * @return exists      true si el traceNumber fue anclado
     */
    function getAnchor(
        string calldata traceNumber
    ) external view returns (bytes32 sha256Hash, uint256 timestamp, bool exists) {
        BatchAnchor memory anchor = anchors[traceNumber];
        return (anchor.sha256Hash, anchor.timestamp, anchor.exists);
    }
}
