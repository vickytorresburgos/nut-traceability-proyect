"""
routers/ocr_proxy.py

Proxy OCR para el móvil en el flujo offline-first.

El móvil llama a estos endpoints (/ocr/remito, /ocr/oven, /ocr/caliber)
para obtener los datos OCR SIN crear un batch en la base de datos.
Esto permite el flujo offline-first donde el móvil almacena los resultados
localmente y los sincroniza cuando hay conexión.

Arquitectura:
  Móvil  →  nut-api /ocr/*  →  ocr-service (interno)

Los errores del OCR (imagen poco clara, confianza baja) se reenvían
con su mensaje original para que el móvil pueda mostrarlos al operario.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
import httpx
from core.config import settings

router = APIRouter()

OCR_BASE = f"http://{settings.OCR_SERVICE_HOST}:{settings.OCR_SERVICE_PORT}"
OCR_TIMEOUT = 120.0  # segundos — debe ser < proxy_read_timeout de nginx (130s)
                     # El pipeline OCR puede tardar hasta ~90s (Tesseract cascada +
                     # EasyOCR safe). Con 120s hay margen antes del corte de nginx.


async def _proxy_to_ocr(image: UploadFile, ocr_endpoint: str) -> dict:
    """Reenvía la imagen al OCR service y devuelve la respuesta JSON."""
    file_bytes = await image.read()
    files = {"image": (image.filename or "upload.jpg", file_bytes, image.content_type or "image/jpeg")}
    headers = {"X-API-KEY": settings.API_KEY} if settings.API_KEY else {}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OCR_BASE}{ocr_endpoint}",
                files=files,
                headers=headers,
                timeout=OCR_TIMEOUT,
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=(
                f"El motor OCR tardó más de {OCR_TIMEOUT:.0f}s en procesar la imagen. "
                "La foto puede tener baja calidad o el servicio está bajo carga. "
                "Intentá con una foto más clara o volvé a intentarlo en unos segundos."
            ),
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar al motor OCR: {str(e)}")

    # Reenviar la respuesta tal cual (incluyendo errores 4xx con su detail)
    try:
        body = response.json()
    except Exception:
        body = {"detail": response.text}

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=body.get("detail", str(body)))

    return body


@router.post("/remito")
async def ocr_remito(image: UploadFile = File(...)):
    """Procesa imagen del remito y devuelve farm_name, harvest_type y date."""
    return await _proxy_to_ocr(image, "/ocr/remito")


@router.post("/oven")
async def ocr_oven(image: UploadFile = File(...)):
    """Procesa imagen del horno y devuelve oven_id y humidity."""
    return await _proxy_to_ocr(image, "/ocr/oven")


@router.post("/caliber")
async def ocr_caliber(image: UploadFile = File(...)):
    """Procesa imagen del calibre y devuelve caliber y weight."""
    return await _proxy_to_ocr(image, "/ocr/caliber")
