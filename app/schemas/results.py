from datetime import datetime

from pydantic import BaseModel


class JobResultItem(BaseModel):
    id: int
    site: str | None = None
    search_term: str
    title: str | None = None
    company: str | None = None
    job_url: str | None = None
    location: str | None = None
    date_posted: str | None = None
    created_at: datetime


class JobResultsResponse(BaseModel):
    job_id: str
    results: list[JobResultItem]
    next_cursor: int
