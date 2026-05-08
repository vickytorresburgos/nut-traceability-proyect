from sqlalchemy.orm import Session
from database import NutBatch
from typing import Optional

def get_batch(db: Session, batch_id: int) -> Optional[NutBatch]:
    return db.query(NutBatch).filter(NutBatch.id == batch_id).first()

def get_batch_by_trace_number(db: Session, trace_number: str) -> Optional[NutBatch]:
    return db.query(NutBatch).filter(NutBatch.trace_number == trace_number).first()

def create_batch(db: Session, farm_name: str, harvest_type: str, remito_date: str, remito_image_url: str, status: str) -> NutBatch:
    new_batch = NutBatch(
        farm_name=farm_name,
        harvest_type=harvest_type,
        remito_date=remito_date,
        remito_image_url=remito_image_url,
        status=status
    )
    db.add(new_batch)
    db.commit()
    db.refresh(new_batch)
    return new_batch

def update_batch_oven(db: Session, batch: NutBatch, oven_id: str, humidity: str, oven_image_url: str):
    batch.oven_id = oven_id
    batch.humidity = humidity
    batch.oven_image_url = oven_image_url
    db.commit()
    return batch

def update_batch_caliber_and_complete(db: Session, batch: NutBatch, caliber: str, weight: str, caliber_image_url: str, trace_number: str, sha256_hash: str, status: str):
    batch.caliber = caliber
    batch.weight = weight
    batch.caliber_image_url = caliber_image_url
    batch.trace_number = trace_number
    batch.sha256_hash = sha256_hash
    batch.status = status
    db.commit()
    db.refresh(batch)
    return batch

def create_complete_batch(
    db: Session, 
    farm_name: str, harvest_type: str, remito_date: str, remito_image_url: str,
    oven_id: str, humidity: str, oven_image_url: str,
    caliber: str, weight: str, caliber_image_url: str,
    status: str
) -> NutBatch:
    new_batch = NutBatch(
        farm_name=farm_name,
        harvest_type=harvest_type,
        remito_date=remito_date,
        remito_image_url=remito_image_url,
        oven_id=oven_id,
        humidity=humidity,
        oven_image_url=oven_image_url,
        caliber=caliber,
        weight=weight,
        caliber_image_url=caliber_image_url,
        status=status
    )
    db.add(new_batch)
    db.flush() # Get the ID without committing
    
    # Generate trace_number with 3 digit padding
    import json
    from services import calculate_sha256
    words = farm_name.split() if farm_name else []
    initials = "".join([w[0].upper() for w in words if w])[:2] if words else "XX"
    trace_number = f"{initials}-{new_batch.id:03d}"
    
    raw_data = json.dumps({
        "trace_number": trace_number,
        "farm_name": farm_name,
        "humidity": humidity,
        "caliber": caliber,
        "weight": weight,
        "harvest_type": harvest_type,
        "remito_img": remito_image_url,
        "oven_img": oven_image_url,
        "caliber_img": caliber_image_url
    }, sort_keys=True)
    digital_hash = calculate_sha256(raw_data)
    
    new_batch.trace_number = trace_number
    new_batch.sha256_hash = digital_hash
    
    db.commit()
    db.refresh(new_batch)
    return new_batch
