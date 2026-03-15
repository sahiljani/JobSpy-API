from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import JobEvent
from app.schemas.events import EventEnvelope


class EventService:
    def __init__(self, db: Session):
        self.db = db

    def emit(self, job_id: str, event_type: str, data: dict) -> JobEvent:
        current_seq = self.db.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id))
        next_seq = int(current_seq or 0) + 1
        event_id = JobEvent.new_id()

        envelope = EventEnvelope(
            event_id=event_id,
            job_id=job_id,
            type=event_type,
            timestamp=datetime.now(timezone.utc),
            sequence=next_seq,
            data=data,
        )

        evt = JobEvent(
            id=event_id,
            job_id=job_id,
            sequence=next_seq,
            type=event_type,
            payload_json=envelope.model_dump(mode='json'),
        )
        self.db.add(evt)
        self.db.flush()
        return evt
