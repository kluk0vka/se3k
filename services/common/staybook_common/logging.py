import json
import logging
import sys

from opentelemetry import trace


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span().get_span_context()
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if span.is_valid:
            payload["trace_id"] = format(span.trace_id, "032x")
            payload["span_id"] = format(span.span_id, "016x")
        for key in ("event_type", "event_id", "booking_id", "topic"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("aiokafka", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
