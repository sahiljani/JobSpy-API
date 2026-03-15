from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import JobEvent, JobResult, WebhookDelivery


class RetentionService:
    def __init__(self, db: Session):
        self.db = db

    def cleanup_db_records(self, *, retain_days: int = 14) -> dict[str, int]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retain_days)

        deleted_events = self.db.execute(delete(JobEvent).where(JobEvent.created_at < cutoff)).rowcount or 0
        deleted_deliveries = self.db.execute(delete(WebhookDelivery).where(WebhookDelivery.created_at < cutoff)).rowcount or 0
        deleted_results = self.db.execute(delete(JobResult).where(JobResult.created_at < cutoff)).rowcount or 0

        self.db.flush()
        return {
            'deleted_events': int(deleted_events),
            'deleted_deliveries': int(deleted_deliveries),
            'deleted_results': int(deleted_results),
        }

    def cleanup_exports(self, *, retain_days: int = 14, exports_dir: str = '/home/sahil/.openclaw/workspace/JobSpy/exports') -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retain_days)
        root = Path(exports_dir)
        if not root.exists():
            return 0

        removed = 0
        for path in root.glob('*.csv'):
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1

        return removed
