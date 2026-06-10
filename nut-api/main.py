from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import init_db, get_db
from services import init_http_client, close_http_client, minio_client
from core.config import settings
from core.logging_config import configure_logging
from core.security import get_current_user
from routers import batches
from routers import ocr_proxy
from routers import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    configure_logging()        # silencia /health del access log
    init_db()
    await init_http_client()   # C3: inicializa el pool de conexiones HTTP
    yield
    # Shutdown
    await close_http_client()  # C3: cierra el cliente limpiamente


app = FastAPI(
    title="Nut Traceability API",
    version="1.1.0",
    lifespan=lifespan
)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Health check enriquecido que verifica DB y MinIO.
    Usado por Docker Compose (condition: service_healthy) y Nginx.
    """
    status: dict = {"api": "ok", "db": "unknown", "minio": "unknown"}

    # Verificar conexión a PostgreSQL
    try:
        db.execute(text("SELECT 1"))
        status["db"] = "ok"
    except Exception as e:
        status["db"] = f"error: {e}"

    # Verificar conexión a MinIO
    try:
        minio_client.bucket_exists(settings.MINIO_BUCKET)
        status["minio"] = "ok"
    except Exception as e:
        status["minio"] = f"error: {e}"

    overall = "healthy" if all(v == "ok" for v in status.values()) else "degraded"
    status["status"] = overall
    return status


app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(batches.router, prefix="/api/v1/batches", tags=["batches"])
app.include_router(ocr_proxy.router, prefix="/ocr", tags=["ocr-proxy"], dependencies=[Depends(get_current_user)])

app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")
