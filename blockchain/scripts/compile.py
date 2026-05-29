"""
Script de compilación del contrato NutTraceability.

Uso:
    pip install py-solc-x
    python blockchain/scripts/compile.py

Genera blockchain/build/NutTraceability.json con el ABI y bytecode
compilado con EVM target 'london' (compatible con Ganache y redes modernas).
"""
import json
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────
SOLC_VERSION = "0.8.20"
EVM_VERSION   = "london"   # No usa PUSH0, compatible con Ganache v7+
CONTRACT_FILE = Path(__file__).parent.parent / "contracts" / "NutTraceability.sol"
OUTPUT_FILE   = Path(__file__).parent.parent / "build" / "NutTraceability.json"

def main():
    try:
        from solcx import compile_files, install_solc
    except ImportError:
        print("ERROR: py-solc-x no instalado. Ejecutar: pip install py-solc-x")
        raise SystemExit(1)

    print(f"Instalando solc {SOLC_VERSION}...")
    install_solc(SOLC_VERSION, show_progress=False)

    print(f"Compilando {CONTRACT_FILE.name} con EVM={EVM_VERSION}...")
    result = compile_files(
        [str(CONTRACT_FILE)],
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        evm_version=EVM_VERSION,
    )

    key = next(k for k in result if "NutTraceability" in k)
    abi      = result[key]["abi"]
    bytecode = "0x" + result[key]["bin"]

    # Verificar ausencia de opcodes incompatibles
    bc_hex = bytecode[2:]
    push0_count = sum(1 for i in range(0, len(bc_hex) - 1, 2) if bc_hex[i:i+2] == "5f")
    if push0_count > 2:
        print(f"ADVERTENCIA: {push0_count} PUSH0 en bytecode — puede causar problemas en Ganache")

    # Guardar
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"abi": abi, "bytecode": bytecode}, f, indent=2)

    print(f"\n✅ Compilado exitosamente")
    print(f"   Solc: {SOLC_VERSION}  |  EVM: {EVM_VERSION}")
    print(f"   ABI: {len(abi)} entradas  |  Bytecode: {len(bytecode)} chars")
    print(f"   Guardado en: {OUTPUT_FILE}")
    print(f"\nPróximo paso:")
    print(f"   ganache --deterministic --port 8545 --chain.hardfork london")
    print(f"   python blockchain/scripts/deploy.py")

if __name__ == "__main__":
    main()
