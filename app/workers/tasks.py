from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Job, JobUnit
from app.db.session import SessionLocal
from app.services.event_service import EventService
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
        webhooks = WebhookService(db)

        job.status = 'started'
        job.started_at = datetime.now(timezone.utc)
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
        location = request.get('location') or 'Canada'
        hours_old = int(request.get('hours_old', 48))
        results_wanted = int(request.get('results_wanted', 20))
        country_indeed = request.get('country_indeed') or 'Canada'
        proxies = request.get('proxies')

        for unit in units:
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
                unit.rows = result.rows
                job.completed_units += 1
                job.rows_collected += result.rows
            else:
                unit.status = 'failed'
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

        if job.cancel_requested_at:
            job.status = 'cancelled'
            terminal = 'job.cancelled'
        elif job.completed_units > 0:
            job.status = 'completed'
            terminal = 'job.completed'
        else:
            job.status = 'failed'
            terminal = 'job.failed'

        job.finished_at = datetime.now(timezone.utc)
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
