# Red Blockchain Permisionada (Hyperledger Besu)

Esta carpeta contiene la configuración para una red blockchain permisionada de 2 nodos validadores utilizando el algoritmo de consenso **Clique** (Proof of Authority).

## Estructura
- `genesis.json`: Configuración inicial de la red, validadores y cuentas pre-fundadas.
- `docker-compose-besu.yml`: Orquestación de los 2 nodos validadores.
- `node1/`, `node2/`: Claves criptográficas de cada nodo.

## Cómo levantar la red
1. Asegúrate de tener Docker instalado.
2. Ejecuta:
   ```bash
   docker-compose -f docker-compose-besu.yml up -d
   ```
3. La red estará disponible en `http://localhost:8545`.

## Cuentas Pre-fundadas
- **Deployer API:**
  - Address: `0xC82500B1538CeF3aaEb82edFa064076221cE97B6`
  - Private Key: `0x3f7bc4bcfaee70773760fb1a37581c6a8bcd03c3e80ccf212cc501a349113f8f` (Configurada en `.env`)

## Verificación de Consenso
Puedes ver que los nodos están llegando a un acuerdo revisando los logs:
```bash
docker logs -f besu-node-1
```
Deberías ver mensajes de "Imported #block" confirmando que ambos nodos están validando.
