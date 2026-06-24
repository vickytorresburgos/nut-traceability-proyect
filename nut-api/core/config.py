import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "traceability")

    MINIO_HOST = os.getenv("MINIO_HOST", "minio")
    MINIO_PORT = os.getenv("MINIO_PORT", "9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "nut-images")

    OCR_SERVICE_HOST = os.getenv("OCR_SERVICE_HOST", "ocr")
    OCR_SERVICE_PORT = os.getenv("OCR_SERVICE_PORT", "8081")
    API_KEY = os.getenv("API_KEY")

    SECRET_KEY = os.getenv("SECRET_KEY", "7b095908b9816f5c8e03e5c9a7217578276f59b66249b6d91f8682662c5b058c")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days for mobile app convenience

settings = Settings()

SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
