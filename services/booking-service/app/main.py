import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import Booking, BookingStatus, Session, init_db
from app.outbox import OutboxRelay, stage_event
from app.saga import Saga
from staybook_common.app import instrument
from staybook_common.kafka import EventConsumer, EventProducer
from staybook_common.logging import setup_logging

setup_logging(settings.service_name)
log = logging.getLogger(__name__)

producer = EventProducer(settings.kafka_bootstrap_servers, settings.service_name)
relay = OutboxRelay(producer)
saga = Saga(relay)
consumer = EventConsumer(
    settings.kafka_bootstrap_servers,
    "booking-service",
    {
        "inventory.held": saga.on_inventory_held,
        "inventory.rejected": saga.on_inventory_rejected,
        "inventory.released": saga.on_inventory_released,
        "payment.succeeded": saga.on_payment_succeeded,
        "payment.failed": saga.on_payment_failed,
        "payment.refunded": saga.on_payment_refunded,
    },
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await producer.start()
    await relay.start()
    await consumer.start()
    yield
    await consumer.stop()
    await relay.stop()
    await producer.stop()


app = FastAPI(title=settings.service_name, lifespan=lifespan)
instrument(app)


class BookingRequest(BaseModel):
    room_id: int = Field(gt=0)
    check_in: date
    check_out: date

    @model_validator(mode="after")
    def dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        return self


class BookingView(BaseModel):
    booking_id: str
    status: str
    guest_id: str
    room_id: int
    check_in: date
    check_out: date
    amount_minor: int
    currency: str
    reject_reason: str | None = None


def view(b: Booking) -> BookingView:
    return BookingView(
        booking_id=str(b.id), status=b.status.value, guest_id=b.guest_id, room_id=b.room_id,
        check_in=b.check_in, check_out=b.check_out, amount_minor=b.amount_minor,
        currency=b.currency, reject_reason=b.reject_reason,
    )


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


@app.post("/bookings", status_code=202, response_model=BookingView)
async def create_booking(
    req: BookingRequest,
    response: Response,
    x_user_id: str = Header(default="anonymous"),
    idempotency_key: str | None = Header(default=None),
) -> BookingView:
    nights = (req.check_out - req.check_in).days
    booking = Booking(
        id=uuid.uuid4(), guest_id=x_user_id, room_id=req.room_id, check_in=req.check_in,
        check_out=req.check_out, status=BookingStatus.PENDING,
        amount_minor=nights * settings.price_per_night_minor, idempotency_key=idempotency_key,
    )
    try:
        async with Session() as session, session.begin():
            session.add(booking)
            await session.flush()
            stage_event(session, "booking.requested", "booking.requested", booking)
    except IntegrityError:
        if idempotency_key is None:
            raise
        async with Session() as session:
            existing = await session.scalar(select(Booking).where(Booking.idempotency_key == idempotency_key))
        response.status_code = 200
        return view(existing)
    relay.notify()
    log.info("booking requested", extra={"booking_id": str(booking.id)})
    return view(booking)


@app.get("/bookings/{booking_id}", response_model=BookingView)
async def get_booking(booking_id: uuid.UUID) -> BookingView:
    async with Session() as session:
        booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "booking not found")
    return view(booking)


@app.get("/bookings", response_model=list[BookingView])
async def list_bookings(x_user_id: str = Header(default="anonymous"), limit: int = 20) -> list[BookingView]:
    async with Session() as session:
        rows = await session.scalars(
            select(Booking).where(Booking.guest_id == x_user_id).order_by(Booking.created_at.desc()).limit(limit)
        )
        return [view(b) for b in rows]


@app.post("/bookings/{booking_id}/cancel", status_code=202, response_model=BookingView)
async def cancel_booking(booking_id: uuid.UUID) -> BookingView:
    async with Session() as session, session.begin():
        booking = await session.get(Booking, booking_id, with_for_update=True)
        if booking is None:
            raise HTTPException(404, "booking not found")
        if booking.status not in (BookingStatus.CONFIRMED, BookingStatus.AWAITING_PAYMENT, BookingStatus.PENDING):
            raise HTTPException(409, f"booking is {booking.status.value}")
        refund = booking.amount_minor if booking.payment_received else 0
        booking.status = BookingStatus.CANCELLING if refund else BookingStatus.CANCELLED
        booking.version += 1
        stage_event(session, "booking.cancelled", "booking.cancelled", booking,
                    {"refund_minor": refund, "reason": "guest_request"})
    relay.notify()
    return view(booking)
