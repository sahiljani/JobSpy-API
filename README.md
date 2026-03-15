# JobSpy Async API (WIP)

Async scraping API using FastAPI + Celery + PostgreSQL.

## Implemented in current phase
- API endpoints:
  - `POST /v1/jobs`
  - `GET /v1/jobs/{job_id}`
  - `GET /v1/jobs/{job_id}/events`
  - `POST /v1/jobs/{job_id}/cancel`
- SQLAlchemy models for `jobs`, `job_units`, `job_events`, `webhook_deliveries`
- Alembic baseline migration
- Event emission service with per-job sequence
- Webhook signing + dispatch logging
- Celery orchestrator skeleton

## Local setup

1. Create `.env` from `.env.example`.
2. Install deps:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
alembic upgrade head
```

4. Run API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

5. Run worker:

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

## API examples

```bash
curl -X POST http://localhost:8080/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me" \
  -d '{
    "search_terms": ["SEO Specialist", "Laravel Developer"],
    "sites": ["indeed", "linkedin"],
    "location": "Canada",
    "hours_old": 48,
    "results_wanted": 20,
    "country_indeed": "Canada"
  }'
```

```bash
curl -H "X-API-Key: change-me" http://localhost:8080/v1/jobs/<job_id>
curl -H "X-API-Key: change-me" http://localhost:8080/v1/jobs/<job_id>/events
curl -X POST -H "X-API-Key: change-me" http://localhost:8080/v1/jobs/<job_id>/cancel
```

## Notes
- This is Phase 1 implementation.
- Next phase focuses on robustness, richer retries, integration tests, and result persistence.
