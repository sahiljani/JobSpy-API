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
Client (Laravel/other)
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
- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs/{job_id}/events`
- `GET /v1/jobs/{job_id}/results`
- `GET /v1/jobs/{job_id}/export.csv`
- `POST /v1/jobs/{job_id}/cancel`
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

### Persistence
- `jobs`, `job_units`, `job_events`, `webhook_deliveries`, `job_results`
- Result dedupe by canonical URL hash + fallback composite hash
- CSV export from persisted results

### Security/robustness
- API key guard (`X-API-Key`)
- Idempotency key support (`X-Idempotency-Key`)
- Encrypted webhook secret storage (seed-based)
- Standardized API error envelope for HTTP errors + validation

---

## Project structure

```text
JobSpy/
  app/
    api/v1/jobs.py
    core/config.py
    core/errors.py
    core/logging.py
    core/metrics.py
    core/security.py
    db/base.py
    db/models.py
    db/session.py
    schemas/
    services/
    workers/
  alembic/
  tests/
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

## Local run (without Docker compose)

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
    },
    "options": {
      "max_runtime_sec": 1800,
      "dedupe_by": "job_url",
      "progress_interval_sec": 5,
      "emit_partial_results": true
    }
  }'
```

### Check job

```bash
curl -H "X-API-Key: change-me" http://localhost:8080/v1/jobs/<job_id>
```

### List events

```bash
curl -H "X-API-Key: change-me" "http://localhost:8080/v1/jobs/<job_id>/events?limit=100&cursor=0"
```

### List results

```bash
curl -H "X-API-Key: change-me" "http://localhost:8080/v1/jobs/<job_id>/results?limit=100&cursor=0"
```

### Export CSV

```bash
curl -H "X-API-Key: change-me" -o results.csv http://localhost:8080/v1/jobs/<job_id>/export.csv
```

### Cancel job

```bash
curl -X POST -H "X-API-Key: change-me" http://localhost:8080/v1/jobs/<job_id>/cancel
```

---

## Webhook signature verification example

Use provided script:

```bash
python scripts_webhook_verify_example.py
```

File:
- `scripts_webhook_verify_example.py`

---

## Troubleshooting

### 1) `401 unauthorized`
- Check `X-API-Key` matches `.env` value.

### 2) Jobs stay queued
- Worker is not running or Redis unavailable.
- Verify worker logs and `REDIS_URL`.

### 3) Webhook not arriving
- Ensure webhook URL reachable from API host.
- Check `webhook_deliveries` table for attempts/failures.
- Run beat scheduler for retries.

### 4) No results for some sites
- Expected for restrictive job boards/time windows.
- Use proxies and broaden search term or hours window.

### 5) Migration issues
- Confirm DB URL/credentials and PostgreSQL port (`5433` in this setup).
- Re-run: `alembic upgrade head`.

---

## Current status

This project has completed Phase 1 and substantial Phase 2 hardening. Remaining work is primarily integration testing and final polish.
