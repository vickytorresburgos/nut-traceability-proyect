from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
import uuid
import json

from database import get_db
from crud import create_batch, update_batch_oven, update_batch_caliber_and_complete, get_batch
from services import upload_image_to_storage, extract_data_with_ocr, calculate_sha256
from core.constants import HARVEST_TYPES, STATUS_PENDING, STATUS_COMPLETED

router = APIRouter()

@router.post("")
async def create_batch_remito(
    remito_image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    file_bytes = await remito_image.read()
    content_type = remito_image.content_type or "image/jpeg"
    filename = f"{uuid.uuid4()}_{remito_image.filename}"
    
    try:
        ocr_result = await extract_data_with_ocr(file_bytes, filename, content_type, "/ocr/remito")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR Service failed: {str(e)}")
    
    farm_name = ocr_result.get("farm_name")
    harvest_type = ocr_result.get("harvest_type")
    remito_date = ocr_result.get("date")
    
    if not farm_name:
        raise HTTPException(status_code=400, detail="No se pudo extraer la finca del remito.")
    
    if harvest_type not in HARVEST_TYPES:
        raise HTTPException(status_code=400, detail=f"No se identificó el tipo de cosecha válido. Debe ser uno de {HARVEST_TYPES}.")  

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
        status=STATUS_PENDING
    )
    
    return {
        "message": "Fase 1 completada. Remito procesado.",
        "batch_id": new_batch.id,
        "status": new_batch.status,
        "extracted_data": {
            "farm_name": farm_name,
            "harvest_type": harvest_type,
            "date": remito_date
        }
    }

@router.post("/{batch_id}/oven")
async def update_batch_oven_endpoint(
    batch_id: int,
    oven_image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    batch = get_batch(db, batch_id)
    if not batch: raise HTTPException(status_code=404, detail="Lote no encontrado")
    
    file_bytes = await oven_image.read()
    content_type = oven_image.content_type or "image/jpeg"
    filename = f"{uuid.uuid4()}_{oven_image.filename}"
    
    try:
        ocr_result = await extract_data_with_ocr(file_bytes, filename, content_type, "/ocr/oven")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR Service failed: {str(e)}")
        
    oven_id = ocr_result.get("oven_id")
    humidity = ocr_result.get("humidity")
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
    
    return {"message": "Fase 2 completada (Horno)", "batch_id": batch.id, "extracted_data": {"oven_id": oven_id, "humidity": humidity}}

@router.post("/{batch_id}/caliber")
async def update_batch_caliber_endpoint(
    batch_id: int,
    caliber_image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    batch = get_batch(db, batch_id)
    if not batch: raise HTTPException(status_code=404, detail="Lote no encontrado")
    
    file_bytes = await caliber_image.read()
    content_type = caliber_image.content_type or "image/jpeg"
    filename = f"{uuid.uuid4()}_{caliber_image.filename}"
    
    try:
        ocr_result = await extract_data_with_ocr(file_bytes, filename, content_type, "/ocr/caliber")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR Service failed: {str(e)}")
        
    caliber = ocr_result.get("caliber")
    weight = ocr_result.get("weight")
    if not caliber or not weight:
        raise HTTPException(status_code=400, detail="No se extrajo calibre y peso")
        
    image_url = upload_image_to_storage(filename, file_bytes, content_type)
    
    # Hash y finalización
    words = batch.farm_name.split() if batch.farm_name else []
    initials = "".join([w[0].upper() for w in words if w])[:2] if words else "XX"
    trace_number = f"{initials}-{batch.id}"
    
    raw_data = json.dumps({
        "trace_number": trace_number,
        "farm_name": batch.farm_name,
        "humidity": batch.humidity,
        "caliber": caliber,
        "weight": weight,
        "harvest_type": batch.harvest_type,
        "remito_img": batch.remito_image_url,
        "oven_img": batch.oven_image_url,
        "caliber_img": image_url
    }, sort_keys=True)
    digital_hash = calculate_sha256(raw_data)
    
    update_batch_caliber_and_complete(
        db, batch, caliber, weight, image_url,
        trace_number, digital_hash, STATUS_COMPLETED
    )
    
    return {
        "message": "Lote Completado exitosamente",
        "batch_id": batch.id,
        "trace_number": batch.trace_number,
        "status": batch.status,
        "hash": batch.sha256_hash,
        "extracted_data": {
            "farm_name": batch.farm_name,
            "harvest_type": batch.harvest_type,
            "date": batch.remito_date,
            "oven_id": batch.oven_id,
            "humidity": batch.humidity,
            "caliber": batch.caliber,
            "weight": batch.weight
        },
        "images": {
            "remito": batch.remito_image_url,
            "oven": batch.oven_image_url,
            "caliber": batch.caliber_image_url
        }
    }
