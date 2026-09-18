from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def instrument(app: FastAPI) -> None:
    Instrumentator(
        excluded_handlers=["/healthz", "/readyz", "/metrics"],
        should_group_status_codes=False,
    ).instrument(app).expose(app, include_in_schema=False)
