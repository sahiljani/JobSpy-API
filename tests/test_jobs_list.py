import os
from datetime import datetime, timezone

from app.db.models import Job

API_KEY = os.getenv('API_KEY', 'change-me')


def test_list_jobs_empty(test_client):
    resp = test_client.get('/v1/jobs', headers={'X-API-Key': API_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body['jobs'] == []


def test_list_jobs_status_filter(test_client, test_session_maker):
    db = test_session_maker()
    try:
        now = datetime.now(timezone.utc)
        db.add(
            Job(
                id='job_a',
                status='running',
                request_json={},
                options_json={},
                total_units=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Job(
                id='job_b',
                status='completed',
                request_json={},
                options_json={},
                total_units=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    finally:
        db.close()

    resp = test_client.get('/v1/jobs?status=running', headers={'X-API-Key': API_KEY})
    assert resp.status_code == 200
    jobs = resp.json()['jobs']
    assert len(jobs) == 1
    assert jobs[0]['status'] == 'running'
