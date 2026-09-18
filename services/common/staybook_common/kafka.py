import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

from staybook_common.events import Event
from staybook_common.metrics import (
    EVENT_END_TO_END_LATENCY,
    EVENT_HANDLER_DURATION,
    EVENTS_CONSUMED,
    EVENTS_PRODUCED,
    PRODUCE_DURATION,
)

log = logging.getLogger(__name__)
tracer = trace.get_tracer("staybook.kafka")

Handler = Callable[[Event], Awaitable[None]]


class _HeaderSetter:
    def set(self, carrier: list, key: str, value: str) -> None:
        carrier.append((key, value.encode()))


class _HeaderGetter:
    def get(self, carrier: dict, key: str) -> list[str] | None:
        value = carrier.get(key)
        return [value] if value is not None else None

    def keys(self, carrier: dict) -> list[str]:
        return list(carrier)


class EventProducer:
    def __init__(self, bootstrap_servers: str, service: str):
        self.service = service
        self.bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self.started = False

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks="all",
            enable_idempotence=True,
            linger_ms=5,
            client_id=self.service,
        )
        await self._producer.start()
        self.started = True

    async def stop(self) -> None:
        if self.started:
            await self._producer.stop()
            self.started = False

    async def publish(self, topic: str, event_type: str, key: str, data: dict) -> Event:
        event = Event(event_type=event_type, producer=self.service, data=data)
        await self.publish_event(topic, key, event)
        return event

    async def publish_event(self, topic: str, key: str, event: Event) -> None:
        with tracer.start_as_current_span(f"{topic} publish", kind=SpanKind.PRODUCER) as span:
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination.name", topic)
            span.set_attribute("messaging.message.id", event.event_id)
            headers: list[tuple[str, bytes]] = [("event_type", event.event_type.encode())]
            propagate.inject(headers, setter=_HeaderSetter())
            started = time.perf_counter()
            await self._producer.send_and_wait(topic, event.to_bytes(), key=key.encode(), headers=headers)
            PRODUCE_DURATION.labels(topic).observe(time.perf_counter() - started)
            EVENTS_PRODUCED.labels(topic).inc()


class EventConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str, handlers: dict[str, Handler]):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.handlers = handlers
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task | None = None
        self.running = False

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self.handlers.keys(),
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            client_id=self.group_id,
        )
        await self._consumer.start()
        self.running = True
        self._task = asyncio.create_task(self._run(), name=f"consumer-{self.group_id}")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer:
            await self._consumer.stop()

    async def _run(self) -> None:
        async for message in self._consumer:
            await self._handle(message)
            await self._consumer.commit()

    async def _handle(self, message) -> None:
        topic = message.topic
        headers = {k: v.decode() for k, v in (message.headers or [])}
        ctx = propagate.extract(headers, getter=_HeaderGetter())
        with tracer.start_as_current_span(f"{topic} process", context=ctx, kind=SpanKind.CONSUMER) as span:
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination.name", topic)
            span.set_attribute("messaging.consumer.group.name", self.group_id)
            try:
                event = Event.from_bytes(message.value)
            except Exception:
                log.exception("undecodable message skipped", extra={"topic": topic})
                EVENTS_CONSUMED.labels(topic, self.group_id, "invalid").inc()
                return
            span.set_attribute("messaging.message.id", event.event_id)
            EVENT_END_TO_END_LATENCY.labels(topic, self.group_id).observe(max(event.age_seconds(), 0))
            started = time.perf_counter()
            for attempt in range(1, 4):
                try:
                    await self.handlers[topic](event)
                    EVENTS_CONSUMED.labels(topic, self.group_id, "ok").inc()
                    break
                except Exception:
                    log.exception(
                        "event handler failed",
                        extra={"topic": topic, "event_id": event.event_id, "event_type": event.event_type},
                    )
                    if attempt == 3:
                        EVENTS_CONSUMED.labels(topic, self.group_id, "failed").inc()
                        span.set_status(trace.Status(trace.StatusCode.ERROR))
                    else:
                        await asyncio.sleep(0.2 * attempt)
            EVENT_HANDLER_DURATION.labels(topic, self.group_id).observe(time.perf_counter() - started)
