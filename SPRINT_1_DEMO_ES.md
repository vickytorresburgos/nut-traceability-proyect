# Demo Sprint 1: Plataforma de Trazabilidad de Nueces

> Sistema integral de trazabilidad desde la cosecha hasta el procesamiento, con captura móvil y extracción de datos mediante IA (OCR).

## 1. Resumen del Sprint

El objetivo principal del Sprint 1 fue establecer la infraestructura core y demostrar el flujo completo. Se implementaron los módulos troncales para capturar, procesar y verificar datos críticos, resolviendo el problema de la "primera milla" en la digitalización industrial mediante la eliminación de la carga manual de datos.

## 2. Módulos Implementados y Resoluciones Técnicas

Este sprint se centró en cinco componentes interconectados que forman la columna vertebral de la plataforma:

### Aplicación Móvil (`mobile-app`)
- **Stack:** React Native (v0.81), Expo (v54), SQLite (v16.0).
- **Cómo se resolvió:** Se diseñó una arquitectura **Offline-First**. Los datos se persisten inmediatamente en una base de datos local SQLite. Un `SyncManager` basado en eventos de red (`NetInfo`) orquesta la subida asíncrona.
- **Justificación:** Expo permite un desarrollo ágil multiplataforma, mientras que SQLite garantiza que el operario nunca pierda datos, incluso en zonas de galpones sin señal de Wi-Fi.

### API Orquestadora (`nut-api`)
- **Stack:** FastAPI (v0.110), PostgreSQL, SQLAlchemy (v2.0), MinIO.
- **Cómo se resolvió:** Se implementó una **Máquina de Estados** para los lotes. La API centraliza la lógica de negocio, coordina el guardado de metadatos en SQL y de imágenes en MinIO, y genera anclajes criptográficos.
- **Justificación:** FastAPI fue elegido por su alto rendimiento y soporte nativo para `async/await`, lo que permite manejar múltiples peticiones de OCR y storage de forma eficiente.

### OCR Proxy
- **Stack:** FastAPI (httpx v0.27).
- **Cómo se resolvió:** Se integró un cliente HTTP global con **Connection Pooling**. El proxy abstrae la comunicación interna entre microservicios, protegiendo al motor OCR de la exposición directa.
- **Justificación:** El uso de `httpx` con pooling reduce drásticamente la latencia al reutilizar conexiones TCP existentes hacia el servicio OCR.

### Motor OCR (`ocr-service`)
- **Stack:** Python, OpenCV (v4.9), Tesseract (v0.3.10), EasyOCR (v1.7), RapidFuzz.
- **Cómo se resolvió:** Se implementó una **Estrategia en Cascada**. Primero se usa Tesseract (rápido) para texto impreso; si la confianza es baja, se escala a pre-procesamiento avanzado con OpenCV y, como último recurso, EasyOCR.
- **Justificación:** OpenCV y Tesseract son el estándar de la industria para procesamiento de documentos. EasyOCR se reservó como fallback para texto manuscrito debido a su mayor consumo de CPU.

### Dashboard Web
- **Stack:** HTML/JS plano.
- **Cómo se resolvió:** Interfaz ligera de solo-lectura que consume los endpoints de la API orquestadora para mostrar la trazabilidad inmutable.
- **Justificación:** Simplicidad absoluta para garantizar una carga instantánea y compatibilidad con cualquier navegador moderno al escanear el QR.

## 3. Flujo del Sistema

El sistema opera bajo un flujo de orquestación asíncrona que garantiza la integridad de los datos:

1.  **Captura Móvil:** El operario captura imágenes de remitos, displays de hornos y etiquetas de calibre.
2.  **Persistencia Local:** Los datos se guardan inmediatamente en SQLite y se calcula el hash SHA-256 de la imagen original.
3.  **Sincronización Inteligente (`SyncManager`):** Cuando detecta conexión, sube las imágenes a la API orquestadora, verificando previamente que el archivo no haya sido corrompido en el dispositivo.
4.  **Orquestación de Backend (`nut-api`):** Recibe la imagen, la almacena de forma segura en MinIO y solicita la extracción de datos al microservicio OCR.
5.  **Extracción IA (`ocr-service`):** Procesa la imagen mediante un pipeline especializado (OpenCV + Tesseract) y devuelve datos estructurados listos para validación.
6.  **Validación y Consolidación:** La API combina los datos extraídos con los metadatos manuales, los persiste en PostgreSQL y genera un número de trazabilidad inmutable.
7.  **Visualización:** Los datos finales y sus evidencias (fotos originales) son consultables desde el Dashboard Web mediante el escaneo de un código QR.

## 4. Pipeline del Motor OCR

El motor OCR utiliza un enfoque híbrido para maximizar la precisión y minimizar los tiempos de respuesta:

### A. Pre-procesamiento Adaptativo
- **Documentos (Remitos/Calibre):** Corrección de perspectiva, eliminación de ruido de fondo y binarización dinámica con OpenCV.
- **Displays Digitales (Hornos):** Aislamiento de segmentos LED/LCD mediante inversión de canales y realce de contraste específico para dígitos segmentados.

### B. Estrategia de Cascada (Paper Cascade)
- **Etapa 1 (Rápida):** Pipeline optimizado para texto impreso estándar. Si la confianza del motor es superior al 55%, la operación finaliza exitosamente.
- **Etapa 2 (Resiliencia):** Si la confianza es baja, se aplica un pre-procesado agresivo diseñado para capturar texto manuscrito y se realiza una segunda pasada de extracción.

### C. Inteligencia de Negocio y Post-procesamiento
- **Normalización Difusa (RapidFuzz):** Corrección automática de nombres de fincas y variedades contra bases de datos maestras para mitigar errores de lectura.
- **Extracción de Entidades (Regex):** Motores de expresiones regulares avanzados para identificar fechas, pesos e identificadores de hornos dentro del texto crudo extraído.

## 5. Tecnologías y Versiones

| Componente | Tecnología | Versión | Razón de Elección |
|------------|------------|---------|-------------------|
| **Móvil** | React Native | 0.81.5 | Ecosistema robusto y performance nativa. |
| **Framework Web** | Expo | 54.0.0 | Facilidad de despliegue y acceso a APIs nativas. |
| **Backend** | FastAPI | 0.110.0 | Velocidad de ejecución y auto-documentación (OpenAPI). |
| **DB Relacional** | PostgreSQL | 16+ | Estándar de integridad de datos y escalabilidad. |
| **ORM** | SQLAlchemy | 2.0.0 | Tipado fuerte y soporte para patrones modernos. |
| **Visión** | OpenCV | 4.9.0 | Potencia inigualable para pre-procesado de imágenes. |
| **OCR** | Tesseract | 5.0 | Motor veloz para texto impreso estructurado. |
| **Almacén** | MinIO | 7.2 | S3-compatible, ideal para evidencias locales. |

## 6. Diferenciadores Técnicos para el MVP

- **Resiliencia:** El sistema no se detiene si se pierde la conexión en los galpones de secado gracias a la sincronización diferida.
- **No-Repudio:** El cálculo de hashes SHA-256 sobre la imagen cruda asegura que el exportador pueda probar la veracidad de los datos ante auditorías internacionales.
- **Integridad de Imagen:** Antes de cada subida, el móvil verifica el hash del archivo en disco para detectar corrupciones de almacenamiento.
- **Escalabilidad:** El desacoplamiento del OCR permite que este corra en hardware dedicado con GPU si la carga lo requiere en el futuro.
