#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[1/8] Python compile check"
python3 -m compileall app main.py tests >/dev/null

echo "[2/8] Unit/integration tests"
pytest -q tests

echo "[3/8] Alembic migration check"
alembic upgrade head

echo "[4/8] OpenAPI artifact existence"
[ -f openapi/openapi.v1.json ] || { echo "missing openapi/openapi.v1.json"; exit 1; }

echo "[5/8] Health endpoint local check"
curl -fsS http://127.0.0.1:8080/healthz >/dev/null || echo "(warn) local healthz unavailable"

echo "[6/8] TODO files present"
[ -f TODO-PHASE-4.md ] || { echo "missing TODO-PHASE-4.md"; exit 1; }

echo "[7/8] Docs present"
for f in docs/ALERTING_RUNBOOK.md docs/SLO_ERROR_BUDGET.md docs/INCIDENT_TEMPLATES.md docs/DEPLOYMENT_PLAYBOOK.md; do
  [ -f "$f" ] || { echo "missing $f"; exit 1; }
done

echo "[8/8] Git status"
git status --short

echo "Release checklist finished."
