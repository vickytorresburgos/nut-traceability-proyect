import os
import hashlib
import httpx
from minio import Minio
from typing import Dict, Any
from core.config import settings

minio_client = Minio(
    f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False
)

def ensure_bucket_exists():
    try:
        found = minio_client.bucket_exists(settings.MINIO_BUCKET)
        if not found:
            minio_client.make_bucket(settings.MINIO_BUCKET)
    except Exception as e:
        print(f"Warning: Failed to ensure MinIO bucket exists: {e}")

def upload_image_to_storage(object_name: str, file_data: bytes, content_type: str = "image/jpeg") -> str:
    import io
    ensure_bucket_exists()
    minio_client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        data=io.BytesIO(file_data),
        length=len(file_data),
        content_type=content_type
    )
    return f"http://{settings.MINIO_HOST}:{settings.MINIO_PORT}/{settings.MINIO_BUCKET}/{object_name}"

async def extract_data_with_ocr(file_data: bytes, filename: str, content_type: str, doc_endpoint: str) -> Dict[str, Any]:
    url = f"http://{settings.OCR_SERVICE_HOST}:{settings.OCR_SERVICE_PORT}{doc_endpoint}"
    files = {'image': (filename, file_data, content_type)}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, files=files, timeout=180.0)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise ValueError(f"OCR respondió {response.status_code}: {detail}")
        return response.json()

def calculate_sha256(data: str) -> str:
    return hashlib.sha256(data.encode('utf-8')).hexdigest()
