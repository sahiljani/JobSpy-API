import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.metrics import metrics
from app.db.models import Job, JobUnit
from app.db.session import SessionLocal
from app.services.event_service import EventService
from app.services.results_service import ResultsService
from app.services.retention_service import RetentionService
from app.services.scraper_service import ScrapeResult, ScraperService
from app.services.webhook_service import WebhookService
from app.workers.celery_app import celery_app

settings = get_settings()


@dataclass
class UnitOutcome:
    unit_id: int
    site: str
    search_term: str
    result: ScrapeResult
    started_at: datetime
    finished_at: datetime
    saved_rows: int = 0


def _run_unit(
    *,
    unit_id: int,
    site: str,
    search_term: str,
    scrape_params: dict[str, Any],
) -> UnitOutcome:
    """Executed in a worker thread. Uses its own DB session for persist_rows."""
    started_at = datetime.now(timezone.utc)
    scraper = ScraperService()
    result = scraper.scrape_unit(
        site=site,
        search_term=search_term,
        location=scrape_params['location'],
        hours_old=scrape_params['hours_old'],
        results_wanted=scrape_params['results_wanted'],
        country_indeed=scrape_params['country_indeed'],
        proxies=scrape_params['proxies'],
    )

    saved_rows = 0
    if result.ok and result.items:
        db = SessionLocal()
        try:
            rs = ResultsService(db)
            saved_rows = rs.persist_rows(
                job_id=scrape_params['job_id'],
                unit_id=unit_id,
                site=site,
                search_term=search_term,
                rows=result.items,
            )
            db.commit()
        finally:
            db.close()

    return UnitOutcome(
        unit_id=unit_id,
        site=site,
        search_term=search_term,
        result=result,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        saved_rows=saved_rows,
    )


@celery_app.task(name='jobs.run_orchestrator')
def run_orchestrator(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        events = EventService(db)
        webhooks = WebhookService(db)

        job.status = 'started'
        job.started_at = datetime.now(timezone.utc)
        metrics.inc('jobs_started_total')
        db.flush()
        evt = events.emit(job_id, 'job.started', {'status': 'started', 'progress_percent': 0})
        db.commit()
        webhooks.dispatch_event(job, evt)
        db.commit()

        job = db.get(Job, job_id)
        if not job:
            return
        job.status = 'running'
        db.flush()

        units: list[JobUnit] = list(
            db.scalars(select(JobUnit).where(JobUnit.job_id == job_id).order_by(JobUnit.sequence.asc())).all()
        )
        request = job.request_json
        options = job.options_json or {}
        location = request.get('location') or 'Canada'
        hours_old = int(request.get('hours_old', 48))
        results_wanted = int(request.get('results_wanted', 20))
        country_indeed = request.get('country_indeed') or 'Canada'
        proxies = request.get('proxies')
        max_runtime_sec = int(options.get('max_runtime_sec', 1800))

        scrape_params: dict[str, Any] = {
            'job_id': job_id,
            'location': location,
            'hours_old': hours_old,
            'results_wanted': results_wanted,
            'country_indeed': country_indeed,
            'proxies': proxies,
        }

        started_at = job.started_at or datetime.now(timezone.utc)
        timed_out = False
        lock = threading.Lock()

        # Build a map from unit_id → unit for main-thread updates
        unit_map: dict[int, JobUnit] = {u.id: u for u in units}

        # Mark all units running before we submit (avoids a double-flush race)
        for unit in units:
            unit.started_at = datetime.now(timezone.utc)
            unit.status = 'running'
        db.flush()
        db.commit()

        futures: dict[Future, JobUnit] = {}
        executor = ThreadPoolExecutor(max_workers=settings.orchestrator_max_workers)

        try:
            # Check cancel/timeout before submitting
            db.expire(job)
            job = db.get(Job, job_id)

            for unit in units:
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                if elapsed > max_runtime_sec:
                    timed_out = True
                    unit.status = 'skipped'
                    job.skipped_units += 1
                    continue
                if job.cancel_requested_at:
                    unit.status = 'cancelled'
                    job.skipped_units += 1
                    continue

                fut = executor.submit(
                    _run_unit,
                    unit_id=unit.id,
                    site=unit.site,
                    search_term=unit.search_term,
                    scrape_params=scrape_params,
                )
                futures[fut] = unit

            db.flush()
            db.commit()

            for fut in as_completed(futures):
                unit = futures[fut]

                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                if elapsed > max_runtime_sec:
                    timed_out = True

                db.expire(job)
                job = db.get(Job, job_id)

                outcome: UnitOutcome = fut.result()

                unit.attempts += 1
                unit.started_at = outcome.started_at
                unit.finished_at = outcome.finished_at

                if outcome.result.ok:
                    unit.status = 'succeeded'
                    unit.rows = outcome.saved_rows
                    metrics.inc(f'unit_success_total:{unit.site}')
                    job.completed_units += 1
                    job.rows_collected += outcome.saved_rows
                else:
                    unit.status = 'failed'
                    unit.error_code = outcome.result.error_code
                    unit.error_message = outcome.result.error_message
                    metrics.inc(f'unit_failed_total:{unit.site}')
                    job.failed_units += 1

                processed = job.completed_units + job.failed_units + job.skipped_units
                if job.total_units > 0:
                    job.progress_percent = int((processed / job.total_units) * 100)

                evt = events.emit(
                    job_id,
                    'job.progress',
                    {
                        'status': 'running',
                        'progress_percent': job.progress_percent,
                        'completed_units': job.completed_units,
                        'failed_units': job.failed_units,
                        'total_units': job.total_units,
                        'rows_collected': job.rows_collected,
                        'current': {'site': unit.site, 'search_term': unit.search_term},
                    },
                )
                db.flush()
                db.commit()
                webhooks.dispatch_event(job, evt)
                db.commit()

        finally:
            executor.shutdown(wait=False)

        # Final state
        db.expire(job)
        job = db.get(Job, job_id)
        if not job:
            return

        if timed_out:
            for unit in units:
                if unit.status in {'pending', 'running'}:
                    unit.status = 'skipped'
                    job.skipped_units += 1
            job.status = 'timed_out'
            terminal = 'job.failed'
            job.error_summary = f'job exceeded max_runtime_sec={max_runtime_sec}'
            metrics.inc('jobs_timed_out_total')
        elif job.cancel_requested_at:
            for unit in units:
                if unit.status in {'pending', 'running'}:
                    unit.status = 'cancelled'
                    job.skipped_units += 1
            job.status = 'cancelled'
            terminal = 'job.cancelled'
            metrics.inc('jobs_cancelled_total')
        elif job.completed_units > 0:
            job.status = 'completed'
            terminal = 'job.completed'
            metrics.inc('jobs_completed_total')
        else:
            job.status = 'failed'
            terminal = 'job.failed'
            metrics.inc('jobs_failed_total')

        job.finished_at = datetime.now(timezone.utc)
        processed = job.completed_units + job.failed_units + job.skipped_units
        if job.total_units > 0:
            job.progress_percent = int((processed / job.total_units) * 100)
        else:
            job.progress_percent = 100

        evt = events.emit(
            job_id,
            terminal,
            {
                'status': job.status,
                'progress_percent': job.progress_percent,
                'completed_units': job.completed_units,
                'failed_units': job.failed_units,
                'total_units': job.total_units,
                'rows_collected': job.rows_collected,
            },
        )
        db.commit()
        webhooks.dispatch_event(job, evt)
        db.commit()
    finally:
        db.close()


@celery_app.task(name='webhooks.retry_due')
def retry_due_webhooks(batch_size: int = 100) -> int:
    db = SessionLocal()
    try:
        webhooks = WebhookService(db)
        retried = webhooks.retry_due_deliveries(batch_size=batch_size)
        if retried > 0:
            metrics.inc('webhook_retry_attempts_total', retried)
        db.commit()
        return retried
    finally:
        db.close()


@celery_app.task(name='maintenance.cleanup_retention')
def cleanup_retention(retain_days: int = 14) -> dict:
    db = SessionLocal()
    try:
        retention = RetentionService(db)
        db_counts = retention.cleanup_db_records(retain_days=retain_days)
        exports_removed = retention.cleanup_exports(retain_days=retain_days)
        db.commit()

        result = {
            **db_counts,
            'deleted_exports': exports_removed,
            'retain_days': retain_days,
        }
        total_deleted = sum(v for k, v in result.items() if k.startswith('deleted_'))
        if total_deleted > 0:
            metrics.inc('maintenance_cleanup_total', total_deleted)
        return result
    finally:
        db.close()
