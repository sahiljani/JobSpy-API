import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import JobResult


class ResultsService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _canonicalize_url(url: str | None) -> str:
        if not url:
            return ''
        url = url.strip()
        if url.endswith('/'):
            url = url[:-1]
        return url.lower()

    def compute_dedupe_hash(self, row: dict[str, Any], search_term: str, site: str) -> str:
        canonical_url = self._canonicalize_url((row.get('job_url') or row.get('url')))
        if canonical_url:
            base = f"url|{canonical_url}"
        else:
            title = str(row.get('title') or '').strip().lower()
            company = str(row.get('company') or '').strip().lower()
            location = str(row.get('location') or '').strip().lower()
            date_posted = str(row.get('date_posted') or '').strip().lower()
            base = f"fallback|{site}|{search_term.lower()}|{title}|{company}|{location}|{date_posted}"

        return hashlib.sha256(base.encode('utf-8')).hexdigest()

    def persist_rows(
        self,
        *,
        job_id: str,
        unit_id: int | None,
        site: str,
        search_term: str,
        rows: list[dict[str, Any]],
    ) -> int:
        saved = 0
        for row in rows:
            dedupe_hash = self.compute_dedupe_hash(row, search_term, site)
            exists = self.db.query(JobResult).filter_by(job_id=job_id, dedupe_hash=dedupe_hash).first()
            if exists:
                continue

            self.db.add(
                JobResult(
                    job_id=job_id,
                    unit_id=unit_id,
                    site=site,
                    search_term=search_term,
                    title=(row.get('title') or None),
                    company=(row.get('company') or None),
                    job_url=(row.get('job_url') or row.get('url') or None),
                    location=(row.get('location') or None),
                    date_posted=(row.get('date_posted') or None),
                    dedupe_hash=dedupe_hash,
                    raw_json=json.loads(json.dumps(row, default=str)),
                )
            )
            saved += 1

        self.db.flush()
        return saved
