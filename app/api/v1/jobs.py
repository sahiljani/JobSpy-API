from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Job, JobEvent
from app.db.session import get_db
from app.schemas.jobs import JobCancelResponse, JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services.job_service import JobService
from app.workers.tasks import run_orchestrator

router = APIRouter(prefix='/v1/jobs', tags=['jobs'])


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid API key')


@router.post('', response_model=JobCreateResponse, dependencies=[Depends(_require_api_key)])
def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)) -> JobCreateResponse:
    service = JobService(db)
    try:
        job = service.create_job(payload)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run_orchestrator.delay(job.id)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        status_url=f'/v1/jobs/{job.id}',
        events_url=f'/v1/jobs/{job.id}/events',
        cancel_url=f'/v1/jobs/{job.id}/cancel',
        created_at=job.created_at,
    )


@router.get('/{job_id}', response_model=JobStatusResponse, dependencies=[Depends(_require_api_key)])
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        progress_percent=job.progress_percent,
        total_units=job.total_units,
        completed_units=job.completed_units,
        failed_units=job.failed_units,
        skipped_units=job.skipped_units,
        rows_collected=job.rows_collected,
        error_summary=job.error_summary,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        cancel_requested_at=job.cancel_requested_at,
    )


@router.get('/{job_id}/events', dependencies=[Depends(_require_api_key)])
def get_job_events(
    job_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: int = Query(default=0, ge=0),
) -> dict:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')

    q = select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence.asc()).limit(limit)
    if cursor > 0:
        q = q.where(JobEvent.sequence > cursor)

    events = db.scalars(q).all()
    next_cursor = events[-1].sequence if events else cursor

    return {
        'job_id': job_id,
        'events': [e.payload_json for e in events],
        'next_cursor': next_cursor,
    }


@router.post('/{job_id}/cancel', response_model=JobCancelResponse, dependencies=[Depends(_require_api_key)])
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> JobCancelResponse:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='job not found')

    if job.status in {'completed', 'failed', 'cancelled', 'timed_out'}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'job already terminal: {job.status}')

    job.cancel_requested_at = datetime.now(timezone.utc)
    db.commit()

    return JobCancelResponse(job_id=job.id, status=job.status, cancel_requested_at=job.cancel_requested_at)
