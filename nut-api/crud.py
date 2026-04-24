from sqlalchemy.orm import Session
from database import NutBatch
from typing import Optional

def get_batch(db: Session, batch_id: int) -> Optional[NutBatch]:
    return db.query(NutBatch).filter(NutBatch.id == batch_id).first()

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
