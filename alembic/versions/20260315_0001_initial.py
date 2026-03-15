"""initial tables for jobspy async api

Revision ID: 20260315_0001
Revises: 
Create Date: 2026-03-15 02:26:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260315_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('request_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('options_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('webhook_url', sa.String(length=512), nullable=True),
        sa.Column('webhook_secret', sa.String(length=512), nullable=True),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('total_units', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_units', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_units', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_units', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rows_collected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jobs_status', 'jobs', ['status'], unique=False)
    op.create_index('ix_jobs_idempotency_key', 'jobs', ['idempotency_key'], unique=True)

    op.create_table(
        'job_units',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('site', sa.String(length=64), nullable=False),
        sa.Column('search_term', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'sequence', name='uq_job_units_job_id_sequence'),
    )
    op.create_index('ix_job_units_job_id', 'job_units', ['job_id'], unique=False)

    op.create_table(
        'job_events',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'sequence', name='uq_job_events_job_id_sequence'),
    )
    op.create_index('ix_job_events_job_id', 'job_events', ['job_id'], unique=False)

    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('url', sa.String(length=512), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('request_headers_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_excerpt', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_webhook_deliveries_event_id', 'webhook_deliveries', ['event_id'], unique=False)
    op.create_index('ix_webhook_deliveries_job_event_attempt', 'webhook_deliveries', ['job_id', 'event_id', 'attempt'], unique=False)
    op.create_index('ix_webhook_deliveries_job_id', 'webhook_deliveries', ['job_id'], unique=False)

    op.create_table(
        'job_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('site', sa.String(length=64), nullable=True),
        sa.Column('search_term', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('company', sa.String(length=512), nullable=True),
        sa.Column('job_url', sa.String(length=2048), nullable=True),
        sa.Column('location', sa.String(length=512), nullable=True),
        sa.Column('date_posted', sa.String(length=64), nullable=True),
        sa.Column('dedupe_hash', sa.String(length=64), nullable=False),
        sa.Column('raw_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unit_id'], ['job_units.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'dedupe_hash', name='uq_job_results_job_id_dedupe_hash'),
    )
    op.create_index('ix_job_results_dedupe_hash', 'job_results', ['dedupe_hash'], unique=False)
    op.create_index('ix_job_results_job_id', 'job_results', ['job_id'], unique=False)
    op.create_index('ix_job_results_unit_id', 'job_results', ['unit_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_job_results_unit_id', table_name='job_results')
    op.drop_index('ix_job_results_job_id', table_name='job_results')
    op.drop_index('ix_job_results_dedupe_hash', table_name='job_results')
    op.drop_table('job_results')

    op.drop_index('ix_webhook_deliveries_job_id', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_job_event_attempt', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_event_id', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')

    op.drop_index('ix_job_events_job_id', table_name='job_events')
    op.drop_table('job_events')

    op.drop_index('ix_job_units_job_id', table_name='job_units')
    op.drop_table('job_units')

    op.drop_index('ix_jobs_idempotency_key', table_name='jobs')
    op.drop_index('ix_jobs_status', table_name='jobs')
    op.drop_table('jobs')
