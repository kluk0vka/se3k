import logging
import socket
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import fault, psp
from app.config import settings
from app.db import Session, init_db
from staybook_common.app import instrument
from staybook_common.events import Event
from staybook_common.kafka import EventConsumer, EventProducer
from staybook_common.logging import setup_logging

setup_logging(settings.service_name)
log = logging.getLogger(__name__)

producer = EventProducer(settings.kafka_bootstrap_servers, settings.service_name)


async def on_booking_cancelled(event: Event) -> None:
    refund_minor = int(event.data.get("refund_minor") or 0)
    booking_id = uuid.UUID(event.data["booking_id"])
    async with Session() as session, session.begin():
        first = await session.execute(
            text("INSERT INTO processed_events (event_id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": uuid.UUID(event.event_id)},
        )
        if first.rowcount == 0 or refund_minor <= 0:
            return
        payment = (
            await session.execute(
                text("SELECT id, psp_reference FROM payments WHERE booking_id = :b AND status = 'SUCCEEDED' FOR UPDATE"),
                {"b": booking_id},
            )
        ).first()
        if payment is None:
            return
        await psp.refund(payment.psp_reference, refund_minor)
        await session.execute(
            text("UPDATE payments SET status = 'REFUNDED', updated_at = now() WHERE id = :id"), {"id": payment.id}
        )
    await producer.publish(
        "payment.refunded", "payment.refunded", str(booking_id),
        {"booking_id": str(booking_id), "guest_id": event.data.get("guest_id"), "amount_minor": refund_minor},
    )


consumer = EventConsumer(settings.kafka_bootstrap_servers, "payment-service", {"booking.cancelled": on_booking_cancelled})


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await producer.start()
    await consumer.start()
    yield
    await consumer.stop()
    await producer.stop()


app = FastAPI(title=settings.service_name, lifespan=lifespan)
app.middleware("http")(fault.fault_middleware)
instrument(app)


class PaymentRequest(BaseModel):
    booking_id: uuid.UUID
    amount_minor: int = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)


class PaymentView(BaseModel):
    payment_id: str
    booking_id: str
    status: str
    psp_reference: str | None = None
    failure_reason: str | None = None


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


@app.post("/payments", response_model=PaymentView)
async def pay(
    req: PaymentRequest,
    response: Response,
    x_user_id: str = Header(default="anonymous"),
    idempotency_key: str | None = Header(default=None),
) -> PaymentView:
    if idempotency_key:
        async with Session() as session:
            row = (
                await session.execute(
                    text("SELECT id, booking_id, status, psp_reference, failure_reason FROM payments WHERE idempotency_key = :k"),
                    {"k": idempotency_key},
                )
            ).first()
        if row:
            return PaymentView(payment_id=str(row.id), booking_id=str(row.booking_id), status=row.status,
                               psp_reference=row.psp_reference, failure_reason=row.failure_reason)
    payment_id = uuid.uuid4()
    try:
        reference, status, reason = await psp.charge(req.amount_minor), "SUCCEEDED", None
    except psp.PspDeclined as exc:
        reference, status, reason = None, "FAILED", str(exc)
    try:
        async with Session() as session, session.begin():
            await session.execute(
                text("INSERT INTO payments (id, booking_id, amount_minor, currency, status, psp_reference, "
                     "failure_reason, idempotency_key) VALUES (:id, :b, :a, :c, :s, :r, :f, :k)"),
                {"id": payment_id, "b": req.booking_id, "a": req.amount_minor, "c": req.currency, "s": status,
                 "r": reference, "f": reason, "k": idempotency_key},
            )
    except IntegrityError:
        raise HTTPException(409, "booking already paid")
    topic = "payment.succeeded" if status == "SUCCEEDED" else "payment.failed"
    await producer.publish(
        topic, topic, str(req.booking_id),
        {"booking_id": str(req.booking_id), "guest_id": x_user_id, "payment_id": str(payment_id),
         "amount_minor": req.amount_minor, "reason": reason},
    )
    if status == "FAILED":
        response.status_code = 402
    return PaymentView(payment_id=str(payment_id), booking_id=str(req.booking_id), status=status,
                       psp_reference=reference, failure_reason=reason)


@app.get("/admin/fault", response_model=fault.FaultConfig)
async def get_fault() -> fault.FaultConfig:
    return fault.state


@app.put("/admin/fault", response_model=fault.FaultConfig)
async def set_fault(cfg: fault.FaultConfig) -> fault.FaultConfig:
    fault.state.error_rate = cfg.error_rate
    fault.state.delay_ms = cfg.delay_ms
    log.warning(f"fault injection on {socket.gethostname()}: {cfg.model_dump()}")
    return fault.state
