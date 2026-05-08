from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles

from database import init_db
from routers import batches
from routers import ocr_proxy

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Nut Traceability API", version="1.0.0", lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

app.include_router(batches.router, prefix="/api/v1/batches", tags=["batches"])
app.include_router(ocr_proxy.router, prefix="/ocr", tags=["ocr-proxy"])

app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")
