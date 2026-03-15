import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base


@pytest.fixture(scope='session')
def integration_db_url() -> str:
    """
    Integration DB URL. Set TEST_DATABASE_URL explicitly for isolation.

    Example:
    postgresql+psycopg://postgres:xxx@127.0.0.1:5433/llm_seo_studio
    """
    return os.getenv('TEST_DATABASE_URL', os.getenv('DATABASE_URL', 'postgresql+psycopg://postgres:xxx@127.0.0.1:5433/llm_seo_studio'))


@pytest.fixture(scope='session')
def test_engine(integration_db_url: str):
    engine = create_engine(integration_db_url, future=True, pool_pre_ping=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def test_session_maker(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False, class_=Session)


@pytest.fixture()
def db_session(test_session_maker) -> Generator[Session, None, None]:
    session = test_session_maker()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def test_client(test_session_maker):
    from app.db.session import get_db
    from app.services.scraper_service import ScrapeResult
    from app.services.scraper_service import ScraperService
    from app.workers import tasks
    from app.workers.celery_app import celery_app
    from main import app

    def _override_get_db():
        db = test_session_maker()
        try:
            yield db
        finally:
            db.close()

    def _fake_scrape_unit(self, **kwargs):
        term = kwargs.get('search_term', 'unknown')
        site = kwargs.get('site', 'indeed')
        return ScrapeResult(
            ok=True,
            rows=2,
            sample=[
                {
                    'site': site,
                    'title': f'{term} Role A',
                    'company': 'Acme',
                    'location': 'Canada',
                    'job_url': f'https://example.com/{site}/{term}/a',
                    'date_posted': '2026-03-15',
                }
            ],
            items=[
                {
                    'site': site,
                    'title': f'{term} Role A',
                    'company': 'Acme',
                    'location': 'Canada',
                    'job_url': f'https://example.com/{site}/{term}/a',
                    'date_posted': '2026-03-15',
                },
                {
                    'site': site,
                    'title': f'{term} Role B',
                    'company': 'Acme',
                    'location': 'Canada',
                    'job_url': f'https://example.com/{site}/{term}/b',
                    'date_posted': '2026-03-15',
                },
            ],
        )

    app.dependency_overrides[get_db] = _override_get_db

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    tasks.SessionLocal = test_session_maker
    ScraperService.scrape_unit = _fake_scrape_unit

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
