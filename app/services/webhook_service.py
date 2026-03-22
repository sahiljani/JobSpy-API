import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret, generate_webhook_signature
from app.db.models import Job, JobEvent, WebhookDelivery


class WebhookService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _compute_next_retry_at(self, *, success: bool, attempt: int) -> datetime | None:
        if success:
            return None

        schedule = self.settings.webhook_retry_schedule
        if attempt >= len(schedule):
            return None

        delay = schedule[attempt]
        return datetime.now(timezone.utc) + timedelta(seconds=delay)

    def dispatch_event(self, job: Job, event: JobEvent, attempt: int = 1) -> bool:
        if not job.webhook_url or not job.webhook_secret:
            return True

        secret = decrypt_secret(job.webhook_secret, self.settings.secret_encryption_key)

        payload = event.payload_json
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        ts = datetime.now(timezone.utc).isoformat()
        sig = generate_webhook_signature(secret, ts, body)

        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Event': event.type,
            'X-Webhook-Event-Id': event.id,
            'X-Webhook-Job-Id': event.job_id,
            'X-Webhook-Event-Sequence': str(event.sequence),
            'X-Webhook-Timestamp': ts,
            'X-Webhook-Signature': sig,
        }

        started = time.time()
        success = False
        status_code = None
        response_excerpt = None

        try:
            resp = httpx.post(job.webhook_url, content=body.encode('utf-8'), headers=headers, timeout=15.0)
            status_code = resp.status_code
            response_excerpt = (resp.text or '')[:1000]
            success = 200 <= resp.status_code < 300
        except Exception as exc:  # pragma: no cover
            response_excerpt = str(exc)[:1000]
            success = False

        latency_ms = int((time.time() - started) * 1000)
        next_retry_at = self._compute_next_retry_at(success=success, attempt=attempt)

        self.db.add(
            WebhookDelivery(
                event_id=event.id,
                job_id=event.job_id,
                url=job.webhook_url,
                attempt=attempt,
                request_headers_json=headers,
                status_code=status_code,
                response_excerpt=response_excerpt,
                latency_ms=latency_ms,
                success=success,
                next_retry_at=next_retry_at,
            )
        )
        self.db.flush()
        return success

    def retry_due_deliveries(self, *, batch_size: int = 100) -> int:
        """
        Retry webhook deliveries where latest attempt is failed and due for retry.
        Returns number of retry attempts dispatched.
        """
        now = datetime.now(timezone.utc)

        latest_attempt_subq = (
            select(
                WebhookDelivery.event_id.label('event_id'),
                func.max(WebhookDelivery.attempt).label('max_attempt'),
            )
            .group_by(WebhookDelivery.event_id)
            .subquery()
        )

        due_rows = self.db.scalars(
            select(WebhookDelivery)
            .join(
                latest_attempt_subq,
                and_(
                    WebhookDelivery.event_id == latest_attempt_subq.c.event_id,
                    WebhookDelivery.attempt == latest_attempt_subq.c.max_attempt,
                ),
            )
            .where(WebhookDelivery.success.is_(False))
            .where(WebhookDelivery.next_retry_at.is_not(None))
            .where(WebhookDelivery.next_retry_at <= now)
            .order_by(WebhookDelivery.next_retry_at.asc())
            .limit(batch_size)
        ).all()

        retried = 0
        for last_delivery in due_rows:
            event = self.db.get(JobEvent, last_delivery.event_id)
            if not event:
                continue
            job = self.db.get(Job, event.job_id)
            if not job:
                continue

            next_attempt = int(last_delivery.attempt) + 1
            self.dispatch_event(job, event, attempt=next_attempt)
            retried += 1

        self.db.flush()
        return retried

    def replay_event(self, *, event_id: str) -> bool:
        event = self.db.get(JobEvent, event_id)
        if not event:
            raise ValueError('event not found')

        job = self.db.get(Job, event.job_id)
        if not job:
            raise ValueError('job not found')

        latest_attempt = self.db.scalar(
            select(func.max(WebhookDelivery.attempt)).where(WebhookDelivery.event_id == event_id)
        )
        next_attempt = int(latest_attempt or 0) + 1
        return self.dispatch_event(job, event, attempt=next_attempt)

    def list_dlq(self, *, limit: int = 100) -> list[WebhookDelivery]:
        latest_attempt_subq = (
            select(
                WebhookDelivery.event_id.label('event_id'),
                func.max(WebhookDelivery.attempt).label('max_attempt'),
            )
            .group_by(WebhookDelivery.event_id)
            .subquery()
        )

        # DLQ condition = latest attempt failed and no next_retry_at scheduled.
        return self.db.scalars(
            select(WebhookDelivery)
            .join(
                latest_attempt_subq,
                and_(
                    WebhookDelivery.event_id == latest_attempt_subq.c.event_id,
                    WebhookDelivery.attempt == latest_attempt_subq.c.max_attempt,
                ),
            )
            .where(WebhookDelivery.success.is_(False))
            .where(WebhookDelivery.next_retry_at.is_(None))
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        ).all()
