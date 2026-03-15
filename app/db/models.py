import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Job(Base):
    __tablename__ = 'jobs'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_json: Mapped[dict] = mapped_column(JSONB)
    options_json: Mapped[dict] = mapped_column(JSONB)

    webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)

    total_units: Mapped[int] = mapped_column(Integer, default=0)
    completed_units: Mapped[int] = mapped_column(Integer, default=0)
    failed_units: Mapped[int] = mapped_column(Integer, default=0)
    skipped_units: Mapped[int] = mapped_column(Integer, default=0)
    rows_collected: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)

    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    units: Mapped[list['JobUnit']] = relationship(back_populates='job', cascade='all, delete-orphan')
    events: Mapped[list['JobEvent']] = relationship(back_populates='job', cascade='all, delete-orphan')

    @staticmethod
    def new_id() -> str:
        return f"job_{uuid.uuid4().hex}"


class JobUnit(Base):
    __tablename__ = 'job_units'
    __table_args__ = (
        UniqueConstraint('job_id', 'sequence', name='uq_job_units_job_id_sequence'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    site: Mapped[str] = mapped_column(String(64))
    search_term: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped['Job'] = relationship(back_populates='units')


class JobEvent(Base):
    __tablename__ = 'job_events'
    __table_args__ = (
        UniqueConstraint('job_id', 'sequence', name='uq_job_events_job_id_sequence'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    job: Mapped['Job'] = relationship(back_populates='events')

    @staticmethod
    def new_id() -> str:
        return f"evt_{uuid.uuid4().hex}"


class WebhookDelivery(Base):
    __tablename__ = 'webhook_deliveries'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(String(512))
    attempt: Mapped[int] = mapped_column(Integer)
    request_headers_json: Mapped[dict] = mapped_column(JSONB)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class JobResult(Base):
    __tablename__ = 'job_results'
    __table_args__ = (
        UniqueConstraint('job_id', 'dedupe_hash', name='uq_job_results_job_id_dedupe_hash'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id', ondelete='CASCADE'), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey('job_units.id', ondelete='SET NULL'), index=True, nullable=True)
    site: Mapped[str | None] = mapped_column(String(64), nullable=True)
    search_term: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company: Mapped[str | None] = mapped_column(String(512), nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    date_posted: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_json: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Index('ix_webhook_deliveries_job_event_attempt', WebhookDelivery.job_id, WebhookDelivery.event_id, WebhookDelivery.attempt)
