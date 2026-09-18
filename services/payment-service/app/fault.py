import asyncio
import random

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class FaultConfig(BaseModel):
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    delay_ms: int = Field(default=0, ge=0, le=30000)


state = FaultConfig()


async def fault_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/payments"):
        if state.delay_ms:
            await asyncio.sleep(state.delay_ms / 1000)
        if state.error_rate and random.random() < state.error_rate:
            return JSONResponse({"detail": "injected fault"}, status_code=503)
    return await call_next(request)
