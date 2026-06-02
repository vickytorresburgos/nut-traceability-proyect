# Demo Sprint 1: Plataforma de Trazabilidad de Nueces

> Sistema integral de trazabilidad desde la finca hasta la exportación, con captura móvil y extracción de datos mediante OCR.

## 1. Resumen y Justificación del Alcance del Sprint 1

El objetivo primordial del Sprint 1 fue establecer la infraestructura core y demostrar el flujo crítico de datos. La decisión de implementar estos módulos específicos en la primera etapa se fundamenta en:

- **Validación de la "Primera Milla":** El mayor riesgo técnico radica en la captura de datos en la planta. Implementar el motor OCR y la base de datos local primero permite validar la viabilidad de digitalizar documentos físicos reales.
- **Arquitectura de Integración:** Establecer la comunicación entre el dispositivo móvil, la API y el microservicio de OCR asegura que los contratos de datos sean sólidos antes de escalar a funcionalidades secundarias.
- **Demostración de Valor:** Al finalizar este sprint, el sistema ya es capaz de generar evidencias inmutables (hashes) y extraer datos automáticamente, resolviendo el problema central de la carga manual de datos.

## 2. Módulos Implementados y Resoluciones Técnicas

Este sprint se centró en cinco componentes interconectados que forman la columna vertebral de la plataforma:

### 2.1. Aplicación Móvil (`mobile-app`)
- **Stack:** React Native (v0.81), Expo (v54), SQLite (v16.0).
- **Resolución:** Arquitectura **Offline-First**. Los datos se persisten en SQLite local y un `SyncManager` orquesta la subida asíncrona.
- **Justificación Técnica (Tesis):**
    - **Desarrollo Multiplataforma:** Se seleccionó React Native con Expo para compilar para iOS y Android desde una única base de código, eliminando el riesgo de exclusión de plataforma en el entorno de finca, donde los operarios poseen dispositivos heterogéneos.
    - **Acceso Robusto a Hardware:** Expo provee librerías nativas probadas como `expo-camera` (control de flash y enfoque), `expo-file-system` (persistencia física de imágenes) y `expo-sqlite` (gestión de base de datos relacional local con soporte para transacciones).
    - **Navegación Moderna:** El uso de `Expo Router` permite un enrutamiento basado en archivos (tipo Next.js), lo que mejora la mantenibilidad y garantiza una usabilidad fluida para el operario al manejar automáticamente el botón de "atrás" en Android.

### 2.2. API y Almacenamiento (`nut-api` / PostgreSQL / MinIO)
- **Stack:** Python, FastAPI (v0.110), PostgreSQL, SQLAlchemy (v2.0), MinIO.
- **Resolución:** Se implementó una **Máquina de Estados** para los lotes y una arquitectura de almacenamiento híbrida.
- **Justificación Técnica (Tesis):**
    - **FastAPI:** Elegido por su soporte nativo para `async/await`, permitiendo atender múltiples peticiones de OCR y almacenamiento de forma eficiente.
    - **Estrategia de Almacenamiento:** Se separaron los metadatos (PostgreSQL) de las evidencias físicas (MinIO). Las bases relacionales no están diseñadas para archivos BLOB pesados; MinIO, al ser compatible con Amazon S3, ofrece una entrega multimedia rápida y portabilidad absoluta a la nube.

### 2.3. OCR Proxy
- **Stack:** FastAPI (httpx v0.27).
- **Cómo se resolvió:** Se integró un cliente HTTP global con **Connection Pooling**. El proxy abstrae la comunicación interna entre microservicios, protegiendo al motor OCR de la exposición directa.
- **Justificación:** El uso de `httpx` con pooling reduce la latencia al reutilizar conexiones TCP hacia el servicio OCR.

### 2.4. Motor OCR (`ocr-service`)
- **Stack:** Python, OpenCV (v4.9), Tesseract (v5.0), RapidFuzz.
- **Cómo se resolvió:** Se implementó un **Pipeline de Pre-procesamiento Adaptativo**. Se utiliza OpenCV para limpiar, normalizar y corregir la perspectiva de la imagen antes de pasarla al motor Tesseract. Si la confianza inicial es baja, el sistema aplica transformaciones morfológicas adicionales para intentar una segunda lectura.
- **Justificación:** Se optó por Tesseract debido a su alta velocidad y bajo consumo de recursos en comparación con modelos basados en Deep Learning. Esto permite procesar múltiples imágenes en paralelo sin saturar el servidor, manteniendo la precisión necesaria para texto impreso y displays digitales.

### 2.5. Dashboard Web
- **Stack:** HTML/JS plano.
- **Cómo se resolvió:** Interfaz ligera de solo-lectura que consume los endpoints de la API orquestadora para mostrar la trazabilidad inmutable.
- **Justificación:** Simplicidad para garantizar una carga instantánea y compatibilidad universal al escanear el QR de trazabilidad.

## 3. Flujo del Sistema

El sistema opera bajo un flujo de orquestación asíncrona que garantiza la integridad de los datos:

1.  **Captura Móvil:** El operario captura imágenes de remitos, displays de hornos y etiquetas de calibre.
2.  **Persistencia Local:** Los datos se guardan inmediatamente en SQLite y se calcula el hash SHA-256 de la imagen original.
3.  **Sincronización Inteligente (`SyncManager`):** Al detectar conexión, sube las imágenes a la API, verificando previamente la integridad del archivo.
4.  **Orquestación de Backend (`nut-api`):** Almacena la imagen en MinIO y solicita la extracción de datos al microservicio OCR.
5.  **Extracción IA (`ocr-service`):** Procesa la imagen mediante un pipeline especializado (OpenCV + Tesseract) y devuelve datos estructurados listos para validación.
6.  **Validación y Consolidación:** La API combina los datos extraídos con los metadatos manuales, los persiste en PostgreSQL y genera un número de trazabilidad inmutable.
7.  **Visualización:** Los datos finales y sus evidencias (fotos originales) son consultables desde el Dashboard Web mediante el escaneo de un código QR.

## 4. Pipeline del Motor OCR

El motor OCR utiliza un enfoque híbrido para maximizar la precisión:

### A. Pre-procesamiento Adaptativo
- **Documentos (Remitos/Calibre):** Corrección de perspectiva, eliminación de ruido de fondo y binarización dinámica con OpenCV.
- **Displays Digitales (Hornos):** Aislamiento de segmentos LED/LCD mediante inversión de canales y realce de contraste específico para dígitos segmentados.

### B. Estrategia de Cascada de Lectura
- **Etapa 1 (Estándar):** Pipeline optimizado para texto impreso. Si la confianza es alta, la operación finaliza.
- **Etapa 2 (Resiliencia):** Si la confianza es baja, se aplica un pre-procesado agresivo (filtrado de ruido y erosión/dilatación) para intentar capturar caracteres difíciles.

### C. Inteligencia de Negocio y Post-procesamiento
- **Normalización Difusa (RapidFuzz):** Corrección automática de nombres de fincas y variedades contra bases de datos maestras para mitigar errores de lectura.
- **Extracción de Entidades (Regex):** Motores de expresiones regulares avanzados para identificar fechas, pesos e identificadores de hornos dentro del texto crudo extraído.

## 5. Tecnologías y Versiones Principales

| Componente | Tecnología | Versión | Razón de Elección |
|------------|------------|---------|-------------------|
| **Móvil** | React Native | 0.81.5 | Ecosistema robusto y performance nativa. |
| **Framework Web** | Expo | 54.0.0 | Facilidad de despliegue y acceso a APIs nativas. |
| **Backend** | FastAPI | 0.110.0 | Velocidad de ejecución y auto-documentación (OpenAPI). |
| **DB Relacional** | PostgreSQL | 16+ | Estándar de integridad de datos y escalabilidad. |
| **Visión** | OpenCV | 4.9.0 | Potencia inigualable para pre-procesado de imágenes. |
| **OCR** | Tesseract | 5.0 | Motor veloz para texto impreso estructurado. |
| **Almacén** | MinIO | 7.2 | S3-compatible, ideal para evidencias locales. |

## 6. Diferenciadores Técnicos para el MVP

- **Resiliencia Offline:** El sistema no se detiene si se pierde la conexión en los galpones de secado.
- **No-Repudio:** El cálculo de hashes SHA-256 sobre la imagen cruda asegura la veracidad de los datos ante auditorías.
- **Integridad de Imagen:** Verificación del hash antes de la subida para detectar corrupciones de almacenamiento.
- **Escalabilidad:** El desacoplamiento del OCR permite que este corra en hardware dedicado si la carga lo requiere en el futuro.
