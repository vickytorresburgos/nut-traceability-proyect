# Módulo Blockchain — NutTraceability

## Estructura

```
blockchain/
├── contracts/
│   └── NutTraceability.sol   # Smart contract (Solidity 0.8.20)
├── build/
│   └── NutTraceability.json  # ABI + bytecode (generado por compilación)
├── scripts/
│   └── deploy.py             # Script de deploy con web3.py
└── README.md                 # Este archivo
```

---

## Paso 1 — Compilar el contrato

### Opción A: Remix IDE (recomendado para MVP/TIF)

1. Ir a [https://remix.ethereum.org](https://remix.ethereum.org)
2. Crear archivo `NutTraceability.sol` y pegar el contenido de `contracts/NutTraceability.sol`
3. En el panel **Solidity Compiler**:
   - Versión: `0.8.20`
   - EVM Version: `paris` (compatible con Ganache y Polygon)
   - Hacer clic en **Compile**
4. En el panel **Compilation Details** → copiar **ABI** y **Bytecode → object**
5. Crear `blockchain/build/NutTraceability.json` con este formato:

```json
{
  "abi": [ ... ],
  "bytecode": "0x608060..."
}
```

### Opción B: solc-js via py-solc-x

```bash
pip install py-solc-x
python -c "
from solcx import compile_files, install_solc
install_solc('0.8.20')
result = compile_files(
    ['blockchain/contracts/NutTraceability.sol'],
    output_values=['abi', 'bin'],
    solc_version='0.8.20'
)
key = list(result.keys())[0]
import json
with open('blockchain/build/NutTraceability.json', 'w') as f:
    json.dump({'abi': result[key]['abi'], 'bytecode': '0x' + result[key]['bin']}, f, indent=2)
print('Compilado OK')
"
```

---

## Paso 2 — Configurar la red

### Opción A: Ganache local (recomendado para desarrollo/TIF)

```bash
npm install -g ganache
ganache --deterministic --accounts 5
```

Variables de entorno:
```env
BLOCKCHAIN_RPC_URL=http://localhost:8545
BLOCKCHAIN_CHAIN_ID=1337
BLOCKCHAIN_DEPLOYER_PRIVATE_KEY=<primer_clave_privada_que_muestra_ganache>
```

### Opción B: Polygon Amoy Testnet (demo con blockchain pública)

1. Crear cuenta en [Alchemy](https://alchemy.com) → crear app en Polygon Amoy
2. Copiar el HTTPS URL
3. Obtener tokens del faucet: [https://faucet.polygon.technology](https://faucet.polygon.technology)

```env
BLOCKCHAIN_RPC_URL=https://polygon-amoy.g.alchemy.com/v2/TU_API_KEY
BLOCKCHAIN_CHAIN_ID=80002
BLOCKCHAIN_DEPLOYER_PRIVATE_KEY=<tu_clave_privada>
```

---

## Paso 3 — Deploy

```bash
cd /path/to/nut-traceability-project

BLOCKCHAIN_RPC_URL=http://localhost:8545 \
BLOCKCHAIN_DEPLOYER_PRIVATE_KEY=0xTU_CLAVE \
python blockchain/scripts/deploy.py
```

Copiar la dirección del contrato al `.env` y al `nut-api/.env`:
```env
BLOCKCHAIN_CONTRACT_ADDRESS=0x...
BLOCKCHAIN_ENABLED=true
```

---

## Variables de entorno requeridas en `nut-api/.env`

```env
# Blockchain — dejar BLOCKCHAIN_ENABLED=false hasta completar el deploy
BLOCKCHAIN_ENABLED=false
BLOCKCHAIN_RPC_URL=http://localhost:8545
BLOCKCHAIN_CHAIN_ID=1337
BLOCKCHAIN_CONTRACT_ADDRESS=
BLOCKCHAIN_DEPLOYER_PRIVATE_KEY=
```

> **Seguridad:** `BLOCKCHAIN_DEPLOYER_PRIVATE_KEY` nunca debe commitarse.
> Verificar que `.gitignore` incluya `.env`.
