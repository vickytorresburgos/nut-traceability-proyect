#!/bin/bash

# Manejo de cierre (Ctrl+C)
cleanup() {
    echo -e "\nDeteniendo entorno..."
    docker compose stop 2>/dev/null
    docker compose -f blockchain/besu/docker-compose-besu.yml stop 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "Limpiando contenedores huerfanos y puertos ocupados"
docker rm -f nut-nginx nut-api nut-ocr nut-minio nut-postgres besu-node-1 besu-node-2 2>/dev/null
lsof -ti :8545 | xargs kill -9 2>/dev/null || true

# Limpieza total de redes para evitar conflictos de etiquetas
echo "Limpiando redes..."
docker network rm besu-net 2>/dev/null || true

echo ""
echo "=================================================="
echo "Iniciando Red Blockchain Permisionada (Besu)"
echo "=================================================="
# El primer compose creará la red con las etiquetas correctas
docker compose -f blockchain/besu/docker-compose-besu.yml up -d --wait --wait-timeout 120

echo "Esperando a que la Blockchain este lista..."
MAX_RETRIES=45
COUNT=0
until curl -sf -X POST -H "Content-Type: application/json" --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' http://localhost:8545 | grep -q "result"; do
    if [ $COUNT -ge $MAX_RETRIES ]; then break; fi
    echo -n "."
    sleep 3
    ((COUNT++))
done

if [ $COUNT -ge $MAX_RETRIES ]; then
    echo "ERROR: La blockchain Besu no inicio a tiempo (timeout de $((MAX_RETRIES * 3))s)."
    exit 1
fi
echo " Blockchain lista"

echo "Desplegando Contrato Inteligente..."
export BLOCKCHAIN_RPC_URL="http://localhost:8545"
export BLOCKCHAIN_DEPLOYER_PRIVATE_KEY="0x3f7bc4bcfaee70773760fb1a37581c6a8bcd03c3e80ccf212cc501a349113f8f"
python3 blockchain/scripts/deploy.py

echo ""
echo "======================================"
echo "Iniciando Backend y Servicios"
echo "======================================"
docker compose up -d --build

echo "Esperando a los servicios de la API"
for i in {1..30}; do
    if docker inspect -f '{{.State.Health.Status}}' nut-nginx 2>/dev/null | grep -q "healthy"; then
        echo "Backend listo"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "Configurando conexion USB para Android"
if command -v adb &> /dev/null; then
    adb reverse tcp:8080 tcp:8080
    adb reverse tcp:8081 tcp:8081
    echo "Redireccion de puertos ADB configurada"
    export EXPO_PUBLIC_API_URL="http://localhost:8080"
fi

echo "Iniciando Frontend Movil"
cd mobile-app
if [ ! -d "node_modules" ]; then
    npm install
fi
npx expo start --localhost
