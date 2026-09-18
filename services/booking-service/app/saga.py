import logging
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import Booking, BookingStatus, ProcessedEvent, Session
from app.outbox import stage_event
from staybook_common.events import Event

log = logging.getLogger(__name__)

TERMINAL = {BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.EXPIRED}


class Saga:
    def __init__(self, relay):
        self.relay = relay

    async def _load(self, session, event: Event) -> Booking | None:
        inserted = await session.execute(
            insert(ProcessedEvent).values(event_id=uuid.UUID(event.event_id)).on_conflict_do_nothing()
        )
        if inserted.rowcount == 0:
            return None
        booking = await session.scalar(
            select(Booking).where(Booking.id == uuid.UUID(event.data["booking_id"])).with_for_update()
        )
        if booking is None:
            log.warning("event for unknown booking", extra={"event_id": event.event_id})
        return booking

    def _transition(self, booking: Booking, status: BookingStatus) -> None:
        log.info(
            f"booking {booking.status.value} -> {status.value}",
            extra={"booking_id": str(booking.id)},
        )
        booking.status = status
        booking.version += 1

    async def on_inventory_held(self, event: Event) -> None:
        async with Session() as session, session.begin():
            booking = await self._load(session, event)
            if booking is None or booking.status != BookingStatus.PENDING:
                return
            if booking.payment_received:
                self._transition(booking, BookingStatus.CONFIRMED)
                stage_event(session, "booking.confirmed", "booking.confirmed", booking)
            else:
                self._transition(booking, BookingStatus.AWAITING_PAYMENT)
        self.relay.notify()

    async def on_inventory_rejected(self, event: Event) -> None:
        async with Session() as session, session.begin():
            booking = await self._load(session, event)
            if booking is None or booking.status in TERMINAL:
                return
            self._transition(booking, BookingStatus.REJECTED)
            booking.reject_reason = event.data.get("reason", "room unavailable")
            if booking.payment_received:
                stage_event(
                    session, "booking.cancelled", "booking.cancelled", booking,
                    {"refund_minor": booking.amount_minor, "reason": "rejected_after_payment"},
                )
        self.relay.notify()

    async def on_inventory_released(self, event: Event) -> None:
        async with Session() as session, session.begin():
            booking = await self._load(session, event)
            if booking is None or event.data.get("reason") != "expired":
                return
            if booking.status in (BookingStatus.PENDING, BookingStatus.AWAITING_PAYMENT):
                self._transition(booking, BookingStatus.EXPIRED)

    async def on_payment_succeeded(self, event: Event) -> None:
        async with Session() as session, session.begin():
            booking = await self._load(session, event)
            if booking is None:
                return
            booking.payment_received = True
            if booking.status == BookingStatus.AWAITING_PAYMENT:
                self._transition(booking, BookingStatus.CONFIRMED)
                stage_event(session, "booking.confirmed", "booking.confirmed", booking)
            elif booking.status in TERMINAL:
                stage_event(
                    session, "booking.cancelled", "booking.cancelled", booking,
                    {"refund_minor": booking.amount_minor, "reason": "payment_after_termination"},
                )
        self.relay.notify()

    async def on_payment_failed(self, event: Event) -> None:
        async with Session() as session, session.begin():
            booking = await self._load(session, event)
            if booking is None or booking.status in TERMINAL or booking.status == BookingStatus.CONFIRMED:
                return
            self._transition(booking, BookingStatus.CANCELLED)
            stage_event(
                session, "booking.cancelled", "booking.cancelled", booking,
                {"refund_minor": 0, "reason": "payment_failed"},
            )
        self.relay.notify()

    async def on_payment_refunded(self, event: Event) -> None:
        async with Session() as session, session.begin():
            booking = await self._load(session, event)
            if booking is None:
                return
            if booking.status == BookingStatus.CANCELLING:
                self._transition(booking, BookingStatus.CANCELLED)
