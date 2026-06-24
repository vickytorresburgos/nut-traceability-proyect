from sqlalchemy import create_engine, Column, Integer, String, DateTime, text, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import datetime
from core.config import SQLALCHEMY_DATABASE_URL

# ── C4: Pool de conexiones explícito ─────────────────────────────────────────
# pool_size=5  → conexiones permanentes en el pool
# max_overflow=10 → conexiones extra permitidas bajo carga pico
# pool_pre_ping=True → descarta conexiones muertas antes de usarlas
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)

    batches = relationship("NutBatch", back_populates="operator")


class NutBatch(Base):
    __tablename__ = "nut_batches"

    id = Column(Integer, primary_key=True, index=True)
    trace_number = Column(String, unique=True, index=True, nullable=True)
    status = Column(String, default="PENDING")

    # Auditoría
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    operator = relationship("User", back_populates="batches")

    # Remito
    farm_name = Column(String, nullable=True)
    harvest_type = Column(String, nullable=True)
    remito_date = Column(String, nullable=True)
    remito_image_url = Column(String, nullable=True)

    # Secadero
    oven_id = Column(String, nullable=True)
    humidity = Column(String, nullable=True)
    oven_image_url = Column(String, nullable=True)

    # Calibrado
    caliber = Column(String, nullable=True)
    weight = Column(String, nullable=True)
    caliber_image_url = Column(String, nullable=True)

    # Sellado
    sha256_hash = Column(String, nullable=True)

    # Blockchain — distinción importante:
    #   sha256_hash        → huella SHA-256 del CONTENIDO del lote (generada por Python)
    #   blockchain_tx_hash → ID de la TRANSACCIÓN en la red Ethereum/Polygon
    #                        (generado por la blockchain al confirmar el anclaje)
    blockchain_tx_hash = Column(String, nullable=True)
    blockchain_anchored_at = Column(DateTime, nullable=True)
    # I4: clave de idempotencia para evitar duplicados en reintentos del móvil
    idempotency_key = Column(String, unique=True, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # Si otro worker ya creó la tabla, ignoramos el error
        print(f"Nota: init_db (create_all) lanzó una excepción (posible ejecución concurrente): {e}")

    migrations = [
        "ALTER TABLE nut_batches ADD COLUMN IF NOT EXISTS remito_date VARCHAR;",
        # I4: columna para idempotencia — safe en re-ejecuciones
        "ALTER TABLE nut_batches ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR UNIQUE;",
        # Blockchain: ID de la tx on-chain (distinto del sha256_hash del lote)
        "ALTER TABLE nut_batches ADD COLUMN IF NOT EXISTS blockchain_tx_hash VARCHAR;",
        "ALTER TABLE nut_batches ADD COLUMN IF NOT EXISTS blockchain_anchored_at TIMESTAMP;",
        # Auditoría de operarios
        "ALTER TABLE nut_batches ADD COLUMN IF NOT EXISTS operator_id INTEGER REFERENCES users(id);",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            conn.execute(text(stmt))
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
