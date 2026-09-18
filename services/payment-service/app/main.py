from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings

app = FastAPI(title=settings.service_name)
Instrumentator().instrument(app).expose(app)

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/readyz")
async def readyz() -> dict:
    return {"status": "ready"}
