from datetime import datetime

from pydantic import BaseModel


class JobListItem(BaseModel):
    job_id: str
    status: str
    progress_percent: int
    total_units: int
    completed_units: int
    failed_units: int
    skipped_units: int
    rows_collected: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
    next_cursor: str | None = None


class WebhookDlqItem(BaseModel):
    event_id: str
    job_id: str
    attempt: int
    status_code: int | None = None
    response_excerpt: str | None = None
    created_at: datetime


class WebhookDlqResponse(BaseModel):
    items: list[WebhookDlqItem]
