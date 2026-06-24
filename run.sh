#!/bin/bash

# Manejo de cierre (Ctrl+C)
cleanup() {
    echo -e "\nDeteniendo entorno..."
    docker compose stop 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "Limpiando contenedores huerfanos y puertos ocupados"
docker rm -f nut-nginx nut-api nut-ocr nut-minio nut-postgres 2>/dev/null

echo ""
echo "=================================================="
echo "Iniciando Entorno con Blockchain Pública (Amoy)"
echo "=================================================="

# Cargar variables para verificar si el contrato ya está configurado
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "$BLOCKCHAIN_CONTRACT_ADDRESS" ]; then
    echo "BLOCKCHAIN_CONTRACT_ADDRESS no detectado. Desplegando nuevo contrato..."
    python3 blockchain/scripts/deploy.py
else
    echo "Usando contrato existente en: $BLOCKCHAIN_CONTRACT_ADDRESS"
fi

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
