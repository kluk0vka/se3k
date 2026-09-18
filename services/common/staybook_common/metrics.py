from prometheus_client import Counter, Histogram

EVENTS_PRODUCED = Counter(
    "staybook_events_produced_total", "Events published to Kafka", ["topic"]
)
EVENTS_CONSUMED = Counter(
    "staybook_events_consumed_total", "Events consumed from Kafka", ["topic", "group", "result"]
)
EVENT_END_TO_END_LATENCY = Histogram(
    "staybook_event_end_to_end_latency_seconds",
    "Time from event creation to the start of its processing by a consumer",
    ["topic", "group"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
EVENT_HANDLER_DURATION = Histogram(
    "staybook_event_handler_duration_seconds",
    "Event handler execution time",
    ["topic", "group"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
PRODUCE_DURATION = Histogram(
    "staybook_kafka_produce_duration_seconds",
    "Time until the broker acknowledged a produced event",
    ["topic"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
