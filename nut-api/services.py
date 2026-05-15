import os
import io
import hashlib
import httpx
from typing import Dict, Any
from core.config import settings

# ── C3: Cliente httpx global con connection pooling ───────────────────────────
# Un único AsyncClient reutiliza conexiones TCP (keep-alive) hacia el OCR service,
# evitando el overhead de handshake en cada request.
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Devuelve el cliente HTTP global (debe estar inicializado en lifespan)."""
    if _http_client is None:
        raise RuntimeError("HTTP client no inicializado. Verificar lifespan de FastAPI.")
    return _http_client


async def init_http_client() -> None:
    """Inicializa el cliente global. Llamar en el startup de FastAPI."""
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(180.0),
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=30.0,
        ),
    )


async def close_http_client() -> None:
    """Cierra el cliente global. Llamar en el shutdown de FastAPI."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# ── MinIO client ──────────────────────────────────────────────────────────────
from minio import Minio

minio_client = Minio(
    f"{settings.MINIO_HOST}:{settings.MINIO_PORT}",
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False,
)


def ensure_bucket_exists():
    try:
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
    except Exception as e:
        print(f"Warning: Failed to ensure MinIO bucket exists: {e}")


def upload_image_to_storage(
    object_name: str, file_data: bytes, content_type: str = "image/jpeg"
) -> str:
    ensure_bucket_exists()
    minio_client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        data=io.BytesIO(file_data),
        length=len(file_data),
        content_type=content_type,
    )
    return f"http://{settings.MINIO_HOST}:{settings.MINIO_PORT}/{settings.MINIO_BUCKET}/{object_name}"


async def extract_data_with_ocr(
    file_data: bytes, filename: str, content_type: str, doc_endpoint: str
) -> Dict[str, Any]:
    url = f"http://{settings.OCR_SERVICE_HOST}:{settings.OCR_SERVICE_PORT}{doc_endpoint}"
    files = {"image": (filename, file_data, content_type)}

    # C3: reutiliza el cliente global con connection pool
    client = get_http_client()
    response = await client.post(url, files=files)

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise ValueError(f"OCR respondió {response.status_code}: {detail}")
    return response.json()


def calculate_sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
