import os
import asyncio
import tempfile
import logging
import traceback
from functools import partial
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException

from engine.pipeline import (
    process_remito_image,
    process_oven_image,
    process_caliber_image,
)
from core.constants import CONFIDENCE_REJECT_THRESHOLD
from core.logging_config import configure_logging

app = FastAPI(title="Nut Traceability — OCR Service", version="2.1.0")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr-service")


@app.on_event("startup")
async def startup_event():
    configure_logging()  # silencia /ocr/health del access log
    # EasyOCR eliminado de todos los pipelines (texto impreso en papel/display
    # digital): Tesseract en cascada es suficiente y responde en <10s.


# ---------------------------------------------------------------------------
# Response models (inline para evitar import circular)
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class RemitoResponse(BaseModel):
    raw_text: str
    farm_name: str | None
    harvest_type: str | None
    date: str | None
    confidence: float
    confidence_alert: bool


class OvenResponse(BaseModel):
    raw_text: str
    oven_id: str | None
    humidity: str | None
    confidence: float
    confidence_alert: bool
    errors: list[str] = []


class CaliberResponse(BaseModel):
    raw_text: str
    caliber: str | None
    weight: str | None
    confidence: float
    confidence_alert: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/ocr/health")
async def health():
    return {"status": "ok", "version": "2.1.0"}


async def process_generic(image: UploadFile, processor_func):
    """
    Guarda el upload en un archivo temporal, lo procesa en un thread pool
    (run_in_executor) para no bloquear el event loop de Uvicorn durante el
    OCR (que puede durar 2-30s), y elimina el temporal al terminar.

    FIX C1: usa model_dump() en lugar de .get() para serializar el resultado
             Pydantic y evitar AttributeError.
    FIX I6: run_in_executor desacopla el trabajo CPU-intensivo del event loop.
    """
    suffix = Path(image.filename or "upload.png").suffix or ".png"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await image.read()
            tmp.write(content)
            tmp_path = tmp.name

        logger.info(f"Procesando '{image.filename}' con {processor_func.__name__}")

        # ── I6: ejecutar en thread pool para liberar el event loop ─────────
        loop = asyncio.get_running_loop()
        result_obj = await loop.run_in_executor(
            None, partial(processor_func, tmp_path)
        )

        # ── C1: serializar correctamente (compatible con Pydantic y TypedDict) ─
        if hasattr(result_obj, "model_dump"):
            result = result_obj.model_dump()
        else:
            result = result_obj

        if result.get("confidence", 100) < CONFIDENCE_REJECT_THRESHOLD:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Imagen con calidad insuficiente para OCR confiable "
                    f"(confidence={result['confidence']:.1f}%, mínimo requerido: "
                    f"{CONFIDENCE_REJECT_THRESHOLD}%). "
                    f"Por favor, tomá una foto más clara e intentá nuevamente."
                ),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR falló con excepción:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/ocr/remito", response_model=RemitoResponse)
async def process_remito(image: UploadFile = File(...)):
    result = await process_generic(image, process_remito_image)
    return RemitoResponse(**result)


@app.post("/ocr/oven", response_model=OvenResponse)
async def process_oven(image: UploadFile = File(...)):
    result = await process_generic(image, process_oven_image)
    return OvenResponse(**result)


@app.post("/ocr/caliber", response_model=CaliberResponse)
async def process_caliber(image: UploadFile = File(...)):
    result = await process_generic(image, process_caliber_image)
    return CaliberResponse(**result)
