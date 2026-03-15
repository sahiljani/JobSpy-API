import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job, JobResult


class ExportService:
    def __init__(self, db: Session):
        self.db = db

    def export_job_results_csv(self, job_id: str) -> Path:
        job = self.db.get(Job, job_id)
        if not job:
            raise ValueError('job not found')
        if job.status not in {'completed', 'failed', 'cancelled', 'timed_out'}:
            raise ValueError('job is not terminal yet')

        rows = self.db.scalars(select(JobResult).where(JobResult.job_id == job_id).order_by(JobResult.id.asc())).all()

        exports_dir = Path('/home/sahil/.openclaw/workspace/JobSpy/exports')
        exports_dir.mkdir(parents=True, exist_ok=True)
        out = exports_dir / f'{job_id}.csv'

        fields = ['id', 'site', 'search_term', 'title', 'company', 'job_url', 'location', 'date_posted', 'created_at']
        with out.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for r in rows:
                writer.writerow(
                    {
                        'id': r.id,
                        'site': r.site,
                        'search_term': r.search_term,
                        'title': r.title,
                        'company': r.company,
                        'job_url': r.job_url,
                        'location': r.location,
                        'date_posted': r.date_posted,
                        'created_at': r.created_at.isoformat() if r.created_at else None,
                    }
                )

        return out
