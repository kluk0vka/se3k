import socket

from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from staybook_common import fault

HOSTNAME = socket.gethostname()


def instrument(app: FastAPI) -> None:
    fault.install(app)

    @app.middleware("http")
    async def served_by(request: Request, call_next):
        response = await call_next(request)
        response.headers["x-served-by"] = HOSTNAME
        return response

    Instrumentator(
        excluded_handlers=["/healthz", "/readyz", "/metrics"],
        should_group_status_codes=False,
    ).instrument(app).expose(app, include_in_schema=False)
