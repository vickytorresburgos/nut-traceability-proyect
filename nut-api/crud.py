from sqlalchemy.orm import Session
from database import NutBatch
from typing import Optional


def get_batch(db: Session, batch_id: int) -> Optional[NutBatch]:
    return db.query(NutBatch).filter(NutBatch.id == batch_id).first()


def get_batch_by_trace_number(db: Session, trace_number: str) -> Optional[NutBatch]:
    return db.query(NutBatch).filter(NutBatch.trace_number == trace_number).first()


def get_batch_by_idempotency_key(db: Session, key: str) -> Optional[NutBatch]:
    """I4: busca un lote existente por su clave de idempotencia."""
    return db.query(NutBatch).filter(NutBatch.idempotency_key == key).first()


def create_batch(
    db: Session,
    farm_name: str,
    harvest_type: str,
    remito_date: str,
    remito_image_url: str,
    status: str,
    operator_id: int | None = None,
) -> NutBatch:
    new_batch = NutBatch(
        farm_name=farm_name,
        harvest_type=harvest_type,
        remito_date=remito_date,
        remito_image_url=remito_image_url,
        status=status,
        operator_id=operator_id,
    )
    db.add(new_batch)
    db.commit()
    db.refresh(new_batch)
    return new_batch


def update_batch_oven(
    db: Session, batch: NutBatch, oven_id: str, humidity: str, oven_image_url: str
):
    batch.oven_id = oven_id
    batch.humidity = humidity
    batch.oven_image_url = oven_image_url
    db.commit()
    return batch


def update_batch_caliber(
    db: Session, batch: NutBatch, caliber: str, weight: str, caliber_image_url: str
):
    """Fase 3: guarda los datos del calibre. NO finaliza ni genera hash."""
    batch.caliber = caliber
    batch.weight = weight
    batch.caliber_image_url = caliber_image_url
    db.commit()
    return batch


def finalize_batch(db: Session, batch: NutBatch) -> NutBatch:
    """
    Paso final: genera el trace_number y el SHA-256 del lote completo,
    y lo marca como COMPLETED.
    El trace_number es por finca: LT-001, LT-002, LF-001, etc.
    Requiere que remito, horno y calibre ya estén cargados en el objeto batch.
    """
    import json
    from services import calculate_sha256

    # ── Generar iniciales de la finca (máx 2 letras) ────────────────────────
    words = batch.farm_name.split() if batch.farm_name else []
    initials = "".join([w[0].upper() for w in words if w])[:2] if words else "XX"
    prefix = f"{initials}-"

    # ── Calcular el siguiente número de secuencia para esta finca ────────────
    # Busca todos los trace_numbers existentes con el mismo prefijo de iniciales,
    # extrae la parte numérica y toma el máximo.
    # Usando MAX en lugar de COUNT para ser robusto frente a:
    #   - lotes eliminados (gaps en la secuencia)
    #   - datos de pruebas anteriores
    existing_traces = (
        db.query(NutBatch.trace_number)
        .filter(
            NutBatch.trace_number.like(f"{prefix}%"),
            NutBatch.id != batch.id,
        )
        .all()
    )
    max_seq = 0
    for (trace,) in existing_traces:
        if trace:
            try:
                num = int(trace.split("-")[-1])
                if num > max_seq:
                    max_seq = num
            except (ValueError, IndexError):
                pass
    sequence = max_seq + 1
    trace_number = f"{prefix}{sequence:03d}"

    # ── Generar hash SHA-256 ──────────────────────────────────────────
    raw_data = json.dumps(
        {
            "trace_number": trace_number,
            "farm_name": batch.farm_name,
            "humidity": batch.humidity,
            "caliber": batch.caliber,
            "weight": batch.weight,
            "harvest_type": batch.harvest_type,
            "remito_img": batch.remito_image_url,
            "oven_img": batch.oven_image_url,
            "caliber_img": batch.caliber_image_url,
        },
        sort_keys=True,
    )
    digital_hash = calculate_sha256(raw_data)

    batch.trace_number = trace_number
    batch.sha256_hash = digital_hash
    batch.status = "COMPLETED"
    db.commit()
    db.refresh(batch)
    return batch


def update_batch_caliber_and_complete(
    db: Session,
    batch: NutBatch,
    caliber: str,
    weight: str,
    caliber_image_url: str,
    trace_number: str,
    sha256_hash: str,
    status: str,
):
    """Mantener compatibilidad con el endpoint /complete (all-at-once)."""
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
    farm_name: str,
    harvest_type: str,
    remito_date: str,
    remito_image_url: str,
    oven_id: str,
    humidity: str,
    oven_image_url: str,
    caliber: str,
    weight: str,
    caliber_image_url: str,
    status: str,
    idempotency_key: Optional[str] = None,  # I4
    operator_id: int | None = None,
) -> NutBatch:
    import json
    from services import calculate_sha256

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
        status=status,
        idempotency_key=idempotency_key,  # I4
        operator_id=operator_id,
    )
    db.add(new_batch)
    db.flush()  # obtiene el ID sin hacer commit

    # Genera trace_number con 3 dígitos de padding
    words = farm_name.split() if farm_name else []
    initials = "".join([w[0].upper() for w in words if w])[:2] if words else "XX"
    trace_number = f"{initials}-{new_batch.id:03d}"

    raw_data = json.dumps(
        {
            "trace_number": trace_number,
            "farm_name": farm_name,
            "humidity": humidity,
            "caliber": caliber,
            "weight": weight,
            "harvest_type": harvest_type,
            "remito_img": remito_image_url,
            "oven_img": oven_image_url,
            "caliber_img": caliber_image_url,
        },
        sort_keys=True,
    )
    digital_hash = calculate_sha256(raw_data)

    new_batch.trace_number = trace_number
    new_batch.sha256_hash = digital_hash

    db.commit()
    db.refresh(new_batch)
    return new_batch
