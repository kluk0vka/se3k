import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import Session
from staybook_common.events import Event
from staybook_common.kafka import EventProducer

log = logging.getLogger(__name__)

EXCLUSION_VIOLATION = "23P01"


class Inventory:
    def __init__(self, producer: EventProducer):
        self.producer = producer
        self._sweeper: asyncio.Task | None = None

    async def _first_time(self, session, event: Event) -> bool:
        result = await session.execute(
            text("INSERT INTO processed_events (event_id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": uuid.UUID(event.event_id)},
        )
        return result.rowcount == 1

    async def _reply(self, topic: str, source: Event, extra: dict | None = None) -> None:
        data = {k: source.data[k] for k in ("booking_id", "guest_id", "room_id", "check_in", "check_out")}
        data.update(extra or {})
        await self.producer.publish(topic, topic, source.data["booking_id"], data)

    async def on_booking_requested(self, event: Event) -> None:
        d = event.data
        try:
            async with Session() as session, session.begin():
                if not await self._first_time(session, event):
                    return
                await session.execute(
                    text(
                        "INSERT INTO holds (id, booking_id, room_id, stay, status, expires_at) "
                        "VALUES (:id, :booking_id, :room_id, daterange(:check_in, :check_out, '[)'), 'HELD', "
                        "now() + make_interval(secs => :ttl))"
                    ),
                    {
                        "id": uuid.uuid4(), "booking_id": uuid.UUID(d["booking_id"]), "room_id": d["room_id"],
                        "check_in": date.fromisoformat(d["check_in"]),
                        "check_out": date.fromisoformat(d["check_out"]), "ttl": settings.hold_ttl_s,
                    },
                )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != EXCLUSION_VIOLATION:
                raise
            async with Session() as session, session.begin():
                await self._first_time(session, event)
            log.info("room unavailable", extra={"booking_id": d["booking_id"]})
            await self._reply("inventory.rejected", event, {"reason": "room unavailable for the requested dates"})
            return
        await self._reply("inventory.held", event, {"hold_ttl_s": settings.hold_ttl_s})

    async def on_booking_confirmed(self, event: Event) -> None:
        async with Session() as session, session.begin():
            if not await self._first_time(session, event):
                return
            await session.execute(
                text("UPDATE holds SET status = 'CONFIRMED', updated_at = now() "
                     "WHERE booking_id = :b AND status = 'HELD'"),
                {"b": uuid.UUID(event.data["booking_id"])},
            )

    async def on_booking_cancelled(self, event: Event) -> None:
        async with Session() as session, session.begin():
            if not await self._first_time(session, event):
                return
            result = await session.execute(
                text("UPDATE holds SET status = 'RELEASED', updated_at = now() "
                     "WHERE booking_id = :b AND status IN ('HELD', 'CONFIRMED')"),
                {"b": uuid.UUID(event.data["booking_id"])},
            )
        if result.rowcount:
            await self._reply("inventory.released", event, {"reason": "cancelled"})

    async def available(self, room_ids: list[int], check_in: date, check_out: date) -> list[int]:
        async with Session() as session:
            busy = await session.execute(
                text("SELECT DISTINCT room_id FROM holds WHERE room_id = ANY(:ids) "
                     "AND status IN ('HELD', 'CONFIRMED') AND stay && daterange(:ci, :co, '[)')"),
                {"ids": room_ids, "ci": check_in, "co": check_out},
            )
            taken = {r[0] for r in busy}
        return [r for r in room_ids if r not in taken]

    async def sweep_expired(self) -> int:
        async with Session() as session, session.begin():
            rows = (
                await session.execute(
                    text("UPDATE holds SET status = 'EXPIRED', updated_at = now() "
                         "WHERE status = 'HELD' AND expires_at < now() "
                         "RETURNING booking_id, room_id, lower(stay) AS ci, upper(stay) AS co")
                )
            ).all()
        for row in rows:
            await self.producer.publish(
                "inventory.released", "inventory.released", str(row.booking_id),
                {"booking_id": str(row.booking_id), "room_id": row.room_id, "check_in": row.ci.isoformat(),
                 "check_out": row.co.isoformat(), "reason": "expired"},
            )
        return len(rows)

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.sweep_interval_s)
            try:
                expired = await self.sweep_expired()
                if expired:
                    log.info(f"expired {expired} holds")
            except Exception:
                log.exception("hold sweeper failed")

    def start_sweeper(self) -> None:
        self._sweeper = asyncio.create_task(self._sweep_loop(), name="hold-sweeper")

    async def stop_sweeper(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
