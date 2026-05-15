# Sistema de Trazabilidad de Datos Críticos de Nueces Basado en Blockchain y OCR

**Alumno:** Torres Burgos María Victoria.
**Institución:** Universidad de Mendoza - Sede Mendoza, Facultad de Ingeniería, Ingeniería en Informática.

## Resumen Ejecutivo
Este proyecto propone un sistema de trazabilidad inmutable para la cadena de suministro en la producción agroexportadora de nueces. Su objetivo principal es resolver el problema de la "primera milla" o el "último metro" en la digitalización industrial: la ruptura de la trazabilidad que ocurre cuando los operarios transcriben manualmente a planillas de papel los datos críticos (como humedad, temperatura o calibre) leídos desde los displays de las maquinarias de secado.

Al eliminar la carga manual, el sistema asegura que la información sea una representación fiel de la realidad, no alterable ni repudiable, protegiendo tanto al exportador frente a reclamos, como al importador al garantizar el cumplimiento normativo.

## Solución Propuesta (MVP)
El Producto Mínimo Viable (MVP) transforma datos operativos volátiles en activos digitales permanentes. El flujo se divide en:
1. **Captura:** Escaneo del display de la máquina utilizando la cámara de un dispositivo móvil (eliminando la transcripción manual).
2. **Extracción (OCR):** Uso de Inteligencia Artificial para extraer los datos técnicos directamente de la imagen.
3. **Persistencia Híbrida:** Almacenamiento de la imagen como evidencia en un Almacén de Objetos, el dato estructurado en una Base de Datos relacional, y el anclaje de un hash criptográfico (SHA-256) en una red Blockchain permisionada.
4. **Consulta (Dashboard):** Generación de un Código QR al concluir el proceso que redirige a un panel web para verificar el historial del lote y su inmutabilidad.

## Arquitectura del Sistema
El sistema utiliza un patrón de diseño híbrido (On-Chain/Off-Chain) compuesto por los siguientes módulos:
* **Cliente Móvil:** Interfaz de captura en planta.
* **Proxy Inverso:** Barrera de seguridad perimetral controlada por firewall.
* **API RESTful:** Cerebro orquestador que centraliza la lógica de negocio.
* **Servicio OCR:** Microservicio basado en IA / modelos de visión para la extracción de texto de imágenes.
* **Almacén de Objetos:** Para resguardo de archivos binarios (evidencias fotográficas).
* **Base de Datos (PostgreSQL):** Persistencia de los datos estructurados para consultas rápidas.
* **Blockchain Permisionada:** Notario digital que registra las huellas criptográficas (hashes SHA-256).
* **Dashboard Web:** Interfaz ligera para la visualización y auditoría de los datos en tiempo real.
