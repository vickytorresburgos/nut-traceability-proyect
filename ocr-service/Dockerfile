# ── Etapa 1: builder ─────────────────────────────────────────────────────────
# Compila wheels de Python para no llevar gcc ni librerías de build a producción.
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Genera wheels precompilados; la imagen final los instala sin compilar.
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ── Etapa 2: runtime ─────────────────────────────────────────────────────────
# Imagen final liviana: solo binarios de sistema necesarios en runtime.
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar wheels pre-compilados sin acceso a internet ni compilador
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels /wheels/*.whl \
    && rm -rf /wheels

WORKDIR /app

COPY . .

EXPOSE 8081

# 2 workers: aprovecha múltiples cores para atender requests concurrentes
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081", \
    "--workers", "2", "--timeout-keep-alive", "75"]
