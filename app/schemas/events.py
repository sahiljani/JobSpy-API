from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventEnvelope(BaseModel):
    event_id: str
    job_id: str
    type: str
    timestamp: datetime
    sequence: int
    data: dict[str, Any]
