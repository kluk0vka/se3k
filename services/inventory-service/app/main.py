from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Response
from sqlalchemy import text

from app.config import settings
from app.db import Session, init_db
from app.holds import Inventory
from staybook_common.app import instrument
from staybook_common.kafka import EventConsumer, EventProducer
from staybook_common.logging import setup_logging

setup_logging(settings.service_name)

producer = EventProducer(settings.kafka_bootstrap_servers, settings.service_name)
inventory = Inventory(producer)
consumer = EventConsumer(
    settings.kafka_bootstrap_servers,
    "inventory-service",
    {
        "booking.requested": inventory.on_booking_requested,
        "booking.confirmed": inventory.on_booking_confirmed,
        "booking.cancelled": inventory.on_booking_cancelled,
    },
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await producer.start()
    await consumer.start()
    inventory.start_sweeper()
    yield
    await inventory.stop_sweeper()
    await consumer.stop()
    await producer.stop()


app = FastAPI(title=settings.service_name, lifespan=lifespan)
instrument(app)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(response: Response) -> dict:
    try:
        async with Session() as session:
            await session.execute(text("select 1"))
    except Exception:
        response.status_code = 503
        return {"status": "db unavailable"}
    if not (producer.started and consumer.running):
        response.status_code = 503
        return {"status": "kafka unavailable"}
    return {"status": "ready"}


@app.get("/inventory/availability")
async def availability(
    room_ids: str = Query(..., description="comma separated room ids"),
    check_in: date = Query(...),
    check_out: date = Query(...),
) -> dict:
    if check_out <= check_in:
        raise HTTPException(422, "check_out must be after check_in")
    ids = [int(x) for x in room_ids.split(",") if x.strip()][:500]
    return {"available": await inventory.available(ids, check_in, check_out)}
