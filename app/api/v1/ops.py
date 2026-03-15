from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import unauthorized
from app.db.models import Job, WebhookDelivery
from app.db.session import get_db
from app.services.webhook_service import WebhookService

router = APIRouter(prefix='/v1/ops', tags=['ops'])


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise unauthorized('invalid API key')


@router.get('/health-summary', dependencies=[Depends(_require_api_key)])
def health_summary(db: Session = Depends(get_db), stuck_minutes: int = Query(default=30, ge=1, le=1440)) -> dict:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=stuck_minutes)

    running_count = db.scalar(select(func.count()).select_from(Job).where(Job.status == 'running')) or 0
    queued_count = db.scalar(select(func.count()).select_from(Job).where(Job.status == 'queued')) or 0
    failed_count = db.scalar(select(func.count()).select_from(Job).where(Job.status == 'failed')) or 0

    stuck_running = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.status == 'running')
        .where(Job.started_at.is_not(None))
        .where(Job.started_at < threshold)
    ) or 0

    dlq_count = len(WebhookService(db).list_dlq(limit=500))

    return {
        'timestamp': now.isoformat(),
        'jobs': {
            'running': int(running_count),
            'queued': int(queued_count),
            'failed': int(failed_count),
            'stuck_running': int(stuck_running),
            'stuck_threshold_minutes': stuck_minutes,
        },
        'webhooks': {
            'dlq_count': int(dlq_count),
        },
    }


@router.get('/queue-overview', dependencies=[Depends(_require_api_key)])
def queue_overview(db: Session = Depends(get_db)) -> dict:
    latest = db.scalars(
        select(Job)
        .order_by(Job.created_at.desc())
        .limit(20)
    ).all()

    latest_failed_deliveries = db.scalars(
        select(WebhookDelivery)
        .where(WebhookDelivery.success.is_(False))
        .order_by(WebhookDelivery.created_at.desc())
        .limit(20)
    ).all()

    return {
        'latest_jobs': [
            {
                'job_id': j.id,
                'status': j.status,
                'created_at': j.created_at.isoformat() if j.created_at else None,
                'progress_percent': j.progress_percent,
            }
            for j in latest
        ],
        'latest_failed_webhooks': [
            {
                'event_id': d.event_id,
                'job_id': d.job_id,
                'attempt': d.attempt,
                'status_code': d.status_code,
                'created_at': d.created_at.isoformat() if d.created_at else None,
            }
            for d in latest_failed_deliveries
        ],
    }


@router.get('/dashboard', dependencies=[Depends(_require_api_key)])
def dashboard_metrics(db: Session = Depends(get_db), hours: int = Query(default=24, ge=1, le=168)) -> dict:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=hours)

    status_rows = db.execute(
        select(Job.status, func.count())
        .where(Job.created_at >= window_start)
        .group_by(Job.status)
    ).all()

    avg_queue_lag_seconds = db.scalar(
        select(func.avg(func.extract('epoch', Job.started_at - Job.created_at)))
        .where(Job.created_at >= window_start)
        .where(Job.started_at.is_not(None))
    )

    avg_duration_seconds = db.scalar(
        select(func.avg(func.extract('epoch', Job.finished_at - Job.started_at)))
        .where(Job.created_at >= window_start)
        .where(Job.started_at.is_not(None))
        .where(Job.finished_at.is_not(None))
    )

    webhook_total = db.scalar(
        select(func.count()).select_from(WebhookDelivery).where(WebhookDelivery.created_at >= window_start)
    ) or 0

    webhook_failed = db.scalar(
        select(func.count())
        .select_from(WebhookDelivery)
        .where(WebhookDelivery.created_at >= window_start)
        .where(WebhookDelivery.success.is_(False))
    ) or 0

    status_counts = {row[0]: int(row[1]) for row in status_rows}

    return {
        'window_hours': hours,
        'window_start': window_start.isoformat(),
        'window_end': now.isoformat(),
        'job_status_counts': status_counts,
        'queue_lag_avg_seconds': float(avg_queue_lag_seconds or 0.0),
        'job_duration_avg_seconds': float(avg_duration_seconds or 0.0),
        'webhook_attempts_total': int(webhook_total),
        'webhook_attempts_failed': int(webhook_failed),
        'webhook_failure_rate': float((webhook_failed / webhook_total) if webhook_total else 0.0),
    }
