from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import bad_request, conflict, not_found, unauthorized
from app.db.models import Job, JobEvent, JobResult
from app.db.session import get_db
from app.schemas.admin import JobListItem, JobListResponse
from app.schemas.jobs import JobCancelResponse, JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.schemas.results import JobResultItem, JobResultsResponse
from app.services.export_service import ExportService
from app.services.job_service import JobService
from app.workers.tasks import run_orchestrator

router = APIRouter(prefix='/v1/jobs', tags=['jobs'])


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise unauthorized('invalid API key')


@router.get('', response_model=JobListResponse, dependencies=[Depends(_require_api_key)])
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> JobListResponse:
    q_stmt = select(Job)

    if status:
        q_stmt = q_stmt.where(Job.status == status)

    if q:
        like_expr = f'%{q.strip()}%'
        q_stmt = q_stmt.where(
            or_(
                Job.id.ilike(like_expr),
                Job.idempotency_key.ilike(like_expr),
            )
        )

    if cursor:
        row = db.get(Job, cursor)
        if row:
            q_stmt = q_stmt.where(
                or_(
                    Job.created_at < row.created_at,
                    and_(Job.created_at == row.created_at, Job.id < row.id),
                )
            )

    q_stmt = q_stmt.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)
    rows = db.scalars(q_stmt).all()

    next_cursor = rows[-1].id if rows else None
    return JobListResponse(
        jobs=[
            JobListItem(
                job_id=r.id,
                status=r.status,
                progress_percent=r.progress_percent,
                total_units=r.total_units,
                completed_units=r.completed_units,
                failed_units=r.failed_units,
                skipped_units=r.skipped_units,
                rows_collected=r.rows_collected,
                created_at=r.created_at,
                started_at=r.started_at,
                finished_at=r.finished_at,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


@router.post('', response_model=JobCreateResponse, dependencies=[Depends(_require_api_key)])
def create_job(
    payload: JobCreateRequest,
    db: Session = Depends(get_db),
    x_idempotency_key: str | None = Header(default=None, alias='X-Idempotency-Key'),
) -> JobCreateResponse:
    service = JobService(db)
    try:
        job, is_new = service.create_job(payload, idempotency_key=x_idempotency_key)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise bad_request(str(exc), code='validation_error') from exc

    if is_new:
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
        raise not_found('job not found')

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
        raise not_found('job not found')

    q_stmt = select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence.asc()).limit(limit)
    if cursor > 0:
        q_stmt = q_stmt.where(JobEvent.sequence > cursor)

    events = db.scalars(q_stmt).all()
    next_cursor = events[-1].sequence if events else cursor

    return {
        'job_id': job_id,
        'events': [e.payload_json for e in events],
        'next_cursor': next_cursor,
    }


@router.get('/{job_id}/results', response_model=JobResultsResponse, dependencies=[Depends(_require_api_key)])
def get_job_results(
    job_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: int = Query(default=0, ge=0),
) -> JobResultsResponse:
    job = db.get(Job, job_id)
    if not job:
        raise not_found('job not found')

    q_stmt = select(JobResult).where(JobResult.job_id == job_id).order_by(JobResult.id.asc()).limit(limit)
    if cursor > 0:
        q_stmt = q_stmt.where(JobResult.id > cursor)

    rows = db.scalars(q_stmt).all()
    next_cursor = rows[-1].id if rows else cursor

    return JobResultsResponse(
        job_id=job_id,
        results=[
            JobResultItem(
                id=r.id,
                site=r.site,
                search_term=r.search_term,
                title=r.title,
                company=r.company,
                job_url=r.job_url,
                location=r.location,
                date_posted=r.date_posted,
                raw_json=r.raw_json,
                created_at=r.created_at,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


@router.get('/{job_id}/export.csv', dependencies=[Depends(_require_api_key)])
def export_job_results_csv(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    exporter = ExportService(db)
    try:
        csv_path = exporter.export_job_results_csv(job_id)
    except ValueError as exc:
        if str(exc) == 'job not found':
            raise not_found('job not found') from exc
        raise conflict(str(exc), code='job_not_exportable') from exc

    return FileResponse(
        path=str(csv_path),
        media_type='text/csv',
        filename=f'{job_id}.csv',
    )


@router.post('/{job_id}/cancel', response_model=JobCancelResponse, dependencies=[Depends(_require_api_key)])
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> JobCancelResponse:
    job = db.get(Job, job_id)
    if not job:
        raise not_found('job not found')

    if job.status in {'completed', 'failed', 'cancelled', 'timed_out'}:
        raise conflict(f'job already terminal: {job.status}', code='job_terminal')

    job.cancel_requested_at = datetime.now(timezone.utc)
    db.commit()

    return JobCancelResponse(job_id=job.id, status=job.status, cancel_requested_at=job.cancel_requested_at)
