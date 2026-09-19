import asyncio
import logging
import random
import socket

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

EXEMPT_PREFIXES = ("/healthz", "/readyz", "/metrics", "/admin")


class FaultConfig(BaseModel):
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    status_code: int = Field(default=503, ge=500, le=599)
    delay_ms: int = Field(default=0, ge=0, le=30000)


state = FaultConfig()
router = APIRouter(prefix="/admin", include_in_schema=False)


@router.get("/fault", response_model=FaultConfig)
async def get_fault() -> FaultConfig:
    return state


@router.put("/fault", response_model=FaultConfig)
async def set_fault(cfg: FaultConfig) -> FaultConfig:
    state.error_rate, state.status_code, state.delay_ms = cfg.error_rate, cfg.status_code, cfg.delay_ms
    log.warning(f"fault injection on {socket.gethostname()}: {cfg.model_dump()}")
    return state


def install(app: FastAPI) -> None:
    app.include_router(router)

    @app.middleware("http")
    async def inject(request: Request, call_next):
        if not request.url.path.startswith(EXEMPT_PREFIXES):
            if state.delay_ms:
                await asyncio.sleep(state.delay_ms / 1000)
            if state.error_rate and random.random() < state.error_rate:
                return JSONResponse({"detail": "injected fault"}, status_code=state.status_code)
        return await call_next(request)
