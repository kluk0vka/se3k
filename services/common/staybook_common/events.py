import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    producer: str
    data: dict[str, Any]

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Event":
        return cls.model_validate(json.loads(raw))

    def age_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.occurred_at).total_seconds()
