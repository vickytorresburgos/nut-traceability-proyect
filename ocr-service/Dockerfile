FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-spa \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descarga los modelos de EasyOCR durante el build para que no haya
# delay en la primera request de producción. Los modelos se cachean en ~/.EasyOCR/
RUN python3 -c "import easyocr; easyocr.Reader(['es', 'en'], gpu=False, verbose=False)" \
    || echo "Advertencia: descarga de modelos EasyOCR falló, se intentará en runtime."


COPY . .

EXPOSE 8081

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
