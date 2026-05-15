from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
import uuid
import json

from database import get_db
from crud import (
    create_batch,
    update_batch_oven,
    update_batch_caliber,
    finalize_batch,
    update_batch_caliber_and_complete,
    get_batch,
    get_batch_by_trace_number,
)
from services import upload_image_to_storage, extract_data_with_ocr, calculate_sha256
from core.constants import HARVEST_TYPES, STATUS_PENDING, STATUS_COMPLETED

router = APIRouter()

@router.post("")
async def create_batch_remito(
    remito_image: UploadFile = File(...),
    # Datos OCR pre-extraidos (opcionales):
    # Si el móvil ya hizo el OCR en el paso de preview, los envía aquí
    # para evitar el doble procesamiento y reducir el tiempo de respuesta.
    farm_name: str | None = Form(None),
    harvest_type: str | None = Form(None),
    remito_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    file_bytes = await remito_image.read()
    content_type = remito_image.content_type or "image/jpeg"
    filename = f"{uuid.uuid4()}_{remito_image.filename}"

    # Solo correr OCR si no se enviaron datos pre-extraidos
    if not farm_name or not harvest_type:
        try:
            ocr_result = await extract_data_with_ocr(
                file_bytes, filename, content_type, "/ocr/remito"
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OCR Service no disponible: {str(e)}")
        farm_name = ocr_result.get("farm_name")
        harvest_type = ocr_result.get("harvest_type")
        remito_date = remito_date or ocr_result.get("date")

    if not farm_name:
        raise HTTPException(status_code=400, detail="No se pudo extraer la finca del remito.")
    if harvest_type not in HARVEST_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"No se identificó el tipo de cosecha válido. Debe ser uno de {HARVEST_TYPES}.",
        )

    try:
        image_url = upload_image_to_storage(filename, file_bytes, content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage Service failed: {str(e)}")

    new_batch = create_batch(
        db=db,
        farm_name=farm_name,
        harvest_type=harvest_type,
        remito_date=remito_date,
        remito_image_url=image_url,
        status=STATUS_PENDING,
    )

    return {
        "message": "Fase 1 completada. Remito procesado.",
        "batch_id": new_batch.id,
        "status": new_batch.status,
        "extracted_data": {
            "farm_name": farm_name,
            "harvest_type": harvest_type,
            "date": remito_date,
        },
    }


@router.post("/{batch_id}/oven")
async def update_batch_oven_endpoint(
    batch_id: int,
    oven_image: UploadFile = File(...),
    # Datos OCR pre-extraidos opcionales
    oven_id: str | None = Form(None),
    humidity: str | None = Form(None),
    db: Session = Depends(get_db),
):
    batch = get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    file_bytes = await oven_image.read()
    content_type = oven_image.content_type or "image/jpeg"
    filename = f"{uuid.uuid4()}_{oven_image.filename}"

    # Solo correr OCR si no se enviaron datos pre-extraidos
    if not oven_id or not humidity:
        try:
            ocr_result = await extract_data_with_ocr(
                file_bytes, filename, content_type, "/ocr/oven"
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OCR Service no disponible: {str(e)}")
        oven_id = oven_id or ocr_result.get("oven_id")
        humidity = humidity or ocr_result.get("humidity")
        raw = ocr_result.get("raw_text", "")
        if not humidity or not oven_id:
            validation_errors = ocr_result.get("errors", [])
            detail_msg = (
                f"No se extrajeron correctamente humedad y/o horno. "
                f"Texto crudo: '{raw}'. "
                f"oven_id detectado: {oven_id}, humidity detectada: {humidity}."
            )
            if validation_errors:
                detail_msg += " Errores de validación: " + " | ".join(validation_errors)
            raise HTTPException(status_code=400, detail=detail_msg)

    image_url = upload_image_to_storage(filename, file_bytes, content_type)
    update_batch_oven(db, batch, oven_id, humidity, image_url)

    return {
        "message": "Fase 2 completada (Horno)",
        "batch_id": batch.id,
        "extracted_data": {"oven_id": oven_id, "humidity": humidity},
    }



@router.post("/{batch_id}/caliber")
async def update_batch_caliber_endpoint(
    batch_id: int,
    caliber_image: UploadFile = File(...),
    # Datos OCR pre-extraidos opcionales
    caliber: str | None = Form(None),
    weight: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """
    Fase 3: procesa la imagen del calibre con OCR y guarda los datos.
    NO finaliza el lote — para eso usar POST /{batch_id}/complete.
    """
    batch = get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    file_bytes = await caliber_image.read()
    content_type = caliber_image.content_type or "image/jpeg"
    filename = f"{uuid.uuid4()}_{caliber_image.filename}"

    # Solo correr OCR si no se enviaron datos pre-extraidos
    if not caliber or not weight:
        try:
            ocr_result = await extract_data_with_ocr(
                file_bytes, filename, content_type, "/ocr/caliber"
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OCR Service no disponible: {str(e)}")
        caliber = caliber or ocr_result.get("caliber")
        weight = weight or ocr_result.get("weight")
        if not caliber or not weight:
            raise HTTPException(status_code=400, detail="No se extrajo calibre y peso")

    image_url = upload_image_to_storage(filename, file_bytes, content_type)
    update_batch_caliber(db, batch, caliber, weight, image_url)

    return {
        "message": "Fase 3 completada (Calibre)",
        "batch_id": batch.id,
        "extracted_data": {
            "caliber": caliber,
            "weight": weight,
        },
    }



@router.post("/{batch_id}/complete")
async def complete_batch_endpoint(
    batch_id: int,
    db: Session = Depends(get_db),
):
    """
    Paso final del flujo step-by-step.
    Lee los datos de las 3 fases ya guardadas en DB, genera el hash SHA-256
    y el trace_number, y marca el lote como COMPLETED.
    Requiere que remito, horno y calibre hayan sido procesados previamente.
    """
    batch = get_batch(db, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    # Validar que las 3 fases están completas antes de finalizar
    missing = []
    if not batch.farm_name:         missing.append("remito")
    if not batch.oven_id:           missing.append("horno")
    if not batch.caliber:           missing.append("calibre")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan datos de las siguientes fases: {', '.join(missing)}. "
                   f"Completar las fases antes de finalizar el lote."
        )

    batch = finalize_batch(db, batch)

    return {
        "message": "Lote finalizado exitosamente",
        "batch_id": batch.id,
        "trace_number": batch.trace_number,
        "status": batch.status,
        "hash": batch.sha256_hash,
        "data": {
            "farm_name": batch.farm_name,
            "harvest_type": batch.harvest_type,
            "date": batch.remito_date,
            "oven_id": batch.oven_id,
            "humidity": batch.humidity,
            "caliber": batch.caliber,
            "weight": batch.weight,
        },
        "images": {
            "remito": batch.remito_image_url,
            "oven": batch.oven_image_url,
            "caliber": batch.caliber_image_url,
        },
    }



@router.get("/by-trace/{trace_number}")
async def get_batch_by_trace(
    trace_number: str,
    db: Session = Depends(get_db),
):
    batch = get_batch_by_trace_number(db, trace_number)
    if not batch:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    return {
        "trace_id": batch.trace_number,
        "farm_name": batch.farm_name,
        "harvest_type": batch.harvest_type,
        "remito_date": batch.remito_date,
        "oven_id": batch.oven_id,
        "humidity": batch.humidity,
        "caliber": batch.caliber,
        "weight": batch.weight,
        "sha256_hash": batch.sha256_hash,
        "status": batch.status,
        "images": {
            "remito": batch.remito_image_url,
            "oven": batch.oven_image_url,
            "caliber": batch.caliber_image_url,
        },
    }
