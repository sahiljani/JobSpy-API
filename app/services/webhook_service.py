import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_webhook_signature
from app.db.models import Job, JobEvent, WebhookDelivery


class WebhookService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def dispatch_event(self, job: Job, event: JobEvent, attempt: int = 1) -> bool:
        if not job.webhook_url or not job.webhook_secret:
            return True

        payload = event.payload_json
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        ts = datetime.now(timezone.utc).isoformat()
        sig = generate_webhook_signature(job.webhook_secret, ts, body)

        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Event': event.type,
            'X-Webhook-Event-Id': event.id,
            'X-Webhook-Job-Id': event.job_id,
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
        retry_schedule = self.settings.webhook_retry_schedule

        next_retry_at = None
        if not success and attempt < len(retry_schedule):
            delay = retry_schedule[attempt]
            next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)

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
