import asyncio
import logging
from datetime import datetime, timezone

from opentelemetry import context, propagate
from sqlalchemy import select, update

from app.config import settings
from app.db import Booking, Outbox, Session
from staybook_common.events import Event
from staybook_common.kafka import EventProducer

log = logging.getLogger(__name__)


def stage_event(session, topic: str, event_type: str, booking: Booking, extra: dict | None = None) -> Event:
    data = {
        "booking_id": str(booking.id),
        "guest_id": booking.guest_id,
        "room_id": booking.room_id,
        "check_in": booking.check_in.isoformat(),
        "check_out": booking.check_out.isoformat(),
        "amount_minor": booking.amount_minor,
        "currency": booking.currency,
        "status": booking.status.value,
    }
    data.update(extra or {})
    event = Event(event_type=event_type, producer=settings.service_name, data=data)
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    session.add(
        Outbox(
            event_id=event.event_id,
            topic=topic,
            key=str(booking.id),
            payload=event.model_dump(mode="json"),
            trace_context=carrier,
        )
    )
    return event


class OutboxRelay:
    def __init__(self, producer: EventProducer):
        self.producer = producer
        self._task: asyncio.Task | None = None
        self._wakeup = asyncio.Event()

    def notify(self) -> None:
        self._wakeup.set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                published = await self._publish_batch()
            except Exception:
                log.exception("outbox relay iteration failed")
                published = 0
            if published < settings.outbox_batch_size:
                try:
                    await asyncio.wait_for(self._wakeup.wait(), timeout=settings.outbox_poll_interval_s)
                except asyncio.TimeoutError:
                    pass
                self._wakeup.clear()

    async def _publish_batch(self) -> int:
        async with Session() as session, session.begin():
            rows = (
                await session.execute(
                    select(Outbox)
                    .where(Outbox.published_at.is_(None))
                    .order_by(Outbox.id)
                    .limit(settings.outbox_batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()
            for row in rows:
                token = context.attach(propagate.extract(row.trace_context or {}))
                try:
                    await self.producer.publish_event(row.topic, row.key, Event.model_validate(row.payload))
                finally:
                    context.detach(token)
            if rows:
                await session.execute(
                    update(Outbox)
                    .where(Outbox.id.in_([r.id for r in rows]))
                    .values(published_at=datetime.now(timezone.utc))
                )
            return len(rows)
