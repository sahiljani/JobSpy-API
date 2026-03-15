# JobSpy Async API

Production-oriented async scraping API using **FastAPI + Celery + PostgreSQL + Redis**.

## What this service does

1. Accepts scrape jobs via API
2. Returns `job_id` immediately
3. Runs scraping in background workers
4. Emits ordered job events
5. Sends signed webhook updates with retry handling
6. Persists normalized results and supports CSV export

---

## Architecture (high-level)

```text
Client
   |
   | POST /v1/jobs
   v
FastAPI (API)
   |  writes jobs + units + events
   |  enqueues orchestrator
   v
PostgreSQL <---- Celery Worker ----> JobSpy scrape_jobs
   ^                 |
   |                 | writes progress + results
   |                 v
Webhook Delivery Log + retry scheduler (Celery Beat)
   |
   +--> signed webhook POSTs to consumer endpoint
```

---

## Implemented features

### API endpoints
- `GET /v1/jobs` (list with filters + cursor pagination)
- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/events`
- `GET /v1/jobs/{job_id}/results`
- `GET /v1/jobs/{job_id}/export.csv`
- `POST /v1/jobs/{job_id}/cancel`
- `GET /v1/admin/webhooks/dlq`
- `POST /v1/admin/webhooks/replay/{event_id}`
- `GET /healthz`
- `GET /metrics`

### Async processing
- Celery orchestrator task for units (`search_term x site`)
- Unit-level status and counters
- Cooperative cancellation checks
- Timeout mapping to terminal outcome

### Webhooks
- HMAC-SHA256 signing (`X-Webhook-Signature`)
- Retry schedule persisted per failed delivery
- Periodic retry worker (`webhooks.retry_due`) via Celery Beat
- Manual replay endpoint for individual events
- DLQ inspection endpoint for exhausted retries

### Persistence
- `jobs`, `job_units`, `job_events`, `webhook_deliveries`, `job_results`
- Result dedupe by canonical URL hash + fallback composite hash
- CSV export from persisted results

### Security/robustness
- API key guard (`X-API-Key`)
- Idempotency key support (`X-Idempotency-Key`)
- Encrypted webhook secret storage (seed-based)
- Standardized API error envelope for HTTP errors + validation

### Ops/maintenance
- Daily retention cleanup task (`maintenance.cleanup_retention`)
- OpenAPI artifact pinned at `openapi/openapi.v1.json`
- CI workflow at `.github/workflows/ci.yml`
- Additional docs under `docs/`

---

## Project structure

```text
JobSpy/
  app/
  alembic/
  tests/
  docs/
  openapi/
  main.py
  requirements.txt
  docker-compose.yml
  .env.example
```

---

## Configuration

Copy and edit env:

```bash
cp .env.example .env
```

Important values:
- `DATABASE_URL=postgresql+psycopg://postgres:xxx@127.0.0.1:5433/llm_seo_studio`
- `REDIS_URL=redis://127.0.0.1:6379/1`
- `API_KEY=change-me`
- `SECRET_ENCRYPTION_KEY=change-me-encryption-seed`

---

## Local run

1. Install deps:

```bash
pip install -r requirements.txt
```

2. Run migrations:

```bash
alembic upgrade head
```

3. Start API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

4. Start worker:

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

5. Start beat scheduler:

```bash
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

---

## Docker compose run

```bash
docker compose up --build
```

Services:
- `api` on `:8080`
- `redis` on `:6379`
- `worker`
- `beat`

---

## API examples

### Create job

```bash
curl -X POST http://localhost:8080/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: change-me" \
  -H "X-Idempotency-Key: run-20260315-001" \
  -d '{
    "search_terms": ["SEO Specialist", "Laravel Developer"],
    "sites": ["indeed", "linkedin", "google"],
    "location": "Canada",
    "hours_old": 48,
    "results_wanted": 20,
    "country_indeed": "Canada",
    "webhook": {
      "url": "http://localhost:8090/webhooks/jobspy",
      "secret": "whsec_xxx"
    }
  }'
```

### List jobs

```bash
curl -H "X-API-Key: change-me" "http://localhost:8080/v1/jobs?limit=20&status=running"
```

### DLQ + replay

```bash
curl -H "X-API-Key: change-me" http://localhost:8080/v1/admin/webhooks/dlq
curl -X POST -H "X-API-Key: change-me" http://localhost:8080/v1/admin/webhooks/replay/<event_id>
```

### Export CSV

```bash
curl -H "X-API-Key: change-me" -o results.csv http://localhost:8080/v1/jobs/<job_id>/export.csv
```

---

## OpenAPI

Pinned OpenAPI schema artifact:
- `openapi/openapi.v1.json`

Regenerate artifact:

```bash
docker run --rm -v "$PWD":/app -w /app python:3.11-slim \
  bash -lc "pip install -r requirements.txt && python - <<'PY'
import json
from pathlib import Path
from main import app
p=Path('openapi/openapi.v1.json')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')
print('wrote', p)
PY"
```

---

## Ops docs

- `docs/LOAD_TEST_NOTES.md`
- `docs/ALERTING_RUNBOOK.md`
- `docs/SECRETS_STRATEGY.md`
- `docs/DEPLOYMENT_PLAYBOOK.md`
- `docs/SLO_ERROR_BUDGET.md`
- `docs/INCIDENT_TEMPLATES.md`
- `docs/DASHBOARD_SPEC.md`
- `docs/DEPLOYMENT_INCIDENTS.md`

---

## Current status

Phase 1 and 2 are complete. Phase 3 standalone production-readiness work is actively progressing.
