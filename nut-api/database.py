from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
from core.config import SQLALCHEMY_DATABASE_URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class NutBatch(Base):
    __tablename__ = "nut_batches"

    id = Column(Integer, primary_key=True, index=True)
    trace_number = Column(String, unique=True, index=True, nullable=True) 
    status = Column(String, default="PENDING")
    
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
    migrations = [
        "ALTER TABLE nut_batches ADD COLUMN IF NOT EXISTS remito_date VARCHAR;",
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
