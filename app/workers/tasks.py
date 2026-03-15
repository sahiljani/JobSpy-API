from datetime import datetime, timezone

from sqlalchemy import select

from app.core.metrics import metrics
from app.db.models import Job, JobUnit
from app.db.session import SessionLocal
from app.services.event_service import EventService
from app.services.results_service import ResultsService
from app.services.scraper_service import ScraperService
from app.services.webhook_service import WebhookService
from app.workers.celery_app import celery_app


@celery_app.task(name='jobs.run_orchestrator')
def run_orchestrator(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return

        events = EventService(db)
        scraper = ScraperService()
        results_service = ResultsService(db)
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

        units = db.scalars(select(JobUnit).where(JobUnit.job_id == job_id).order_by(JobUnit.sequence.asc())).all()
        request = job.request_json
        options = job.options_json or {}
        location = request.get('location') or 'Canada'
        hours_old = int(request.get('hours_old', 48))
        results_wanted = int(request.get('results_wanted', 20))
        country_indeed = request.get('country_indeed') or 'Canada'
        proxies = request.get('proxies')
        max_runtime_sec = int(options.get('max_runtime_sec', 1800))

        timed_out = False
        started_at = job.started_at or datetime.now(timezone.utc)

        for unit in units:
            elapsed_sec = int((datetime.now(timezone.utc) - started_at).total_seconds())
            if elapsed_sec > max_runtime_sec:
                timed_out = True
                break
            if job.cancel_requested_at:
                unit.status = 'cancelled'
                job.skipped_units += 1
                continue

            unit.status = 'running'
            unit.started_at = datetime.now(timezone.utc)
            db.flush()

            result = scraper.scrape_unit(
                site=unit.site,
                search_term=unit.search_term,
                location=location,
                hours_old=hours_old,
                results_wanted=results_wanted,
                country_indeed=country_indeed,
                proxies=proxies,
            )

            unit.attempts += 1
            unit.finished_at = datetime.now(timezone.utc)
            if result.ok:
                unit.status = 'succeeded'
                metrics.inc(f'unit_success_total:{unit.site}')
                saved_rows = results_service.persist_rows(
                    job_id=job_id,
                    unit_id=unit.id,
                    site=unit.site,
                    search_term=unit.search_term,
                    rows=result.items,
                )
                unit.rows = saved_rows
                job.completed_units += 1
                job.rows_collected += saved_rows
            else:
                unit.status = 'failed'
                metrics.inc(f'unit_failed_total:{unit.site}')
                unit.error_code = result.error_code
                unit.error_message = result.error_message
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
            db.commit()
            webhooks.dispatch_event(job, evt)
            db.commit()

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
