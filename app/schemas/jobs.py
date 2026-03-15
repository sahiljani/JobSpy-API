from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

ALLOWED_SITES = {'indeed', 'linkedin', 'zip_recruiter', 'google', 'glassdoor'}


class WebhookConfig(BaseModel):
    url: HttpUrl
    secret: str = Field(min_length=3, max_length=512)


class JobOptions(BaseModel):
    max_runtime_sec: int = Field(default=1800, ge=60, le=14400)
    dedupe_by: Literal['job_url', 'none'] = 'job_url'
    progress_interval_sec: int = Field(default=5, ge=1, le=60)
    emit_partial_results: bool = True


class JobCreateRequest(BaseModel):
    search_terms: list[str] = Field(min_length=1)
    sites: list[str] = Field(min_length=1)
    location: str | None = None
    hours_old: int = Field(default=48, ge=1, le=720)
    results_wanted: int = Field(default=20, ge=1, le=50)
    country_indeed: str | None = 'Canada'
    proxies: list[str] | None = None
    webhook: WebhookConfig | None = None
    options: JobOptions = Field(default_factory=JobOptions)

    @field_validator('search_terms')
    @classmethod
    def validate_terms(cls, values: list[str]) -> list[str]:
        cleaned = []
        seen = set()
        for value in values:
            v = value.strip()
            if not v:
                continue
            if v.lower() in seen:
                continue
            seen.add(v.lower())
            cleaned.append(v)
        if not cleaned:
            raise ValueError('search_terms cannot be empty after normalization')
        return cleaned

    @field_validator('sites')
    @classmethod
    def validate_sites(cls, values: list[str]) -> list[str]:
        cleaned = []
        seen = set()
        for value in values:
            v = value.strip().lower()
            if v in seen:
                continue
            if v not in ALLOWED_SITES:
                raise ValueError(f'invalid site: {v}')
            seen.add(v)
            cleaned.append(v)
        if not cleaned:
            raise ValueError('sites cannot be empty')
        return cleaned

    @field_validator('proxies')
    @classmethod
    def validate_proxies(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        # jobspy accepts multiple proxy formats (http://user:pass@host:port,
        # host:port:user:pass, etc.) — pass through and let jobspy handle them.
        return [v.strip() for v in values if v.strip()]


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    status_url: str
    events_url: str
    cancel_url: str
    created_at: datetime


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress_percent: int
    total_units: int
    completed_units: int
    failed_units: int
    skipped_units: int
    rows_collected: int
    error_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None


class JobCancelResponse(BaseModel):
    job_id: str
    status: str
    cancel_requested_at: datetime
