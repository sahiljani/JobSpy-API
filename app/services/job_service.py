from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.db.models import Job, JobUnit
from app.schemas.jobs import JobCreateRequest
from app.services.event_service import EventService


class JobService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.events = EventService(db)

    def create_job(self, payload: JobCreateRequest, *, idempotency_key: str | None = None) -> tuple[Job, bool]:
        if len(payload.search_terms) > self.settings.max_search_terms:
            raise ValueError('too many search_terms')
        if len(payload.sites) > self.settings.max_sites:
            raise ValueError('too many sites')
        if payload.proxies and len(payload.proxies) > self.settings.max_proxies:
            raise ValueError('too many proxies')

        if idempotency_key:
            existing = self.db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
            if existing:
                return existing, False

        total_units = len(payload.search_terms) * len(payload.sites)

        job = Job(
            id=Job.new_id(),
            status='queued',
            request_json=payload.model_dump(mode='json'),
            options_json=payload.options.model_dump(mode='json'),
            webhook_url=str(payload.webhook.url) if payload.webhook else None,
            webhook_secret=(
                encrypt_secret(payload.webhook.secret, self.settings.secret_encryption_key)
                if payload.webhook
                else None
            ),
            idempotency_key=idempotency_key,
            total_units=total_units,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(job)
        self.db.flush()

        seq = 0
        for term in payload.search_terms:
            for site in payload.sites:
                seq += 1
                self.db.add(
                    JobUnit(
                        job_id=job.id,
                        sequence=seq,
                        site=site,
                        search_term=term,
                        status='pending',
                    )
                )

        self.events.emit(
            job.id,
            'job.queued',
            {
                'status': 'queued',
                'progress_percent': 0,
                'completed_units': 0,
                'failed_units': 0,
                'total_units': total_units,
                'rows_collected': 0,
            },
        )

        self.db.flush()
        return job, True

    def get_job(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def get_job_events(self, job_id: str, limit: int = 100) -> list[dict]:
        rows = self.db.scalars(
            select(JobUnit).where(JobUnit.job_id == job_id).order_by(JobUnit.sequence.asc()).limit(limit)
        ).all()
        return [
            {
                'sequence': r.sequence,
                'site': r.site,
                'search_term': r.search_term,
                'status': r.status,
                'rows': r.rows,
            }
            for r in rows
        ]
