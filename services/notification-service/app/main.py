import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from app.config import settings
from staybook_common.app import instrument
from staybook_common.events import Event
from staybook_common.kafka import EventConsumer
from staybook_common.logging import setup_logging

setup_logging(settings.service_name)
log = logging.getLogger(__name__)

mongo = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
db = mongo[settings.mongo_db]

TEMPLATES = {
    "booking.confirmed": "Booking {booking_id} is confirmed: room {room_id}, {check_in} - {check_out}",
    "booking.cancelled": "Booking {booking_id} is cancelled",
    "payment.failed": "Payment for booking {booking_id} failed: {reason}",
    "payment.refunded": "Refund for booking {booking_id} is on its way",
}


async def notify(event: Event) -> None:
    data = event.data
    text = TEMPLATES[event.event_type].format_map({k: data.get(k, "") for k in
                                                 ("booking_id", "room_id", "check_in", "check_out", "reason")})
    doc = {
        "_id": event.event_id,
        "guest_id": data.get("guest_id"),
        "booking_id": data.get("booking_id"),
        "event_type": event.event_type,
        "channel": "email",
        "text": text,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.notifications.insert_one(doc)
    except DuplicateKeyError:
        return
    log.info(f"notification sent: {text}", extra={"booking_id": data.get("booking_id")})


consumer = EventConsumer(
    settings.kafka_bootstrap_servers,
    "notification-service",
    {topic: notify for topic in TEMPLATES},
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.notifications.create_index("created_at", expireAfterSeconds=settings.retention_days * 86400)
    await db.notifications.create_index([("guest_id", 1), ("created_at", -1)])
    await consumer.start()
    yield
    await consumer.stop()
    mongo.close()


app = FastAPI(title=settings.service_name, lifespan=lifespan)
instrument(app)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(response: Response) -> dict:
    try:
        await db.command("ping")
    except Exception:
        response.status_code = 503
        return {"status": "db unavailable"}
    if not consumer.running:
        response.status_code = 503
        return {"status": "kafka unavailable"}
    return {"status": "ready"}


@app.get("/notifications")
async def list_notifications(x_user_id: str = Header(default="anonymous"), limit: int = 20) -> list[dict]:
    cursor = db.notifications.find({"guest_id": x_user_id}).sort("created_at", -1).limit(min(limit, 100))
    return [{**d, "notification_id": d.pop("_id")} async for d in cursor]
