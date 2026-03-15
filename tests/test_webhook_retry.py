from datetime import datetime, timezone

from app.services.webhook_service import WebhookService


class _DummySettings:
    webhook_retry_schedule = [0, 60, 120]


def test_compute_next_retry_at_success_none(monkeypatch):
    service = WebhookService.__new__(WebhookService)
    service.settings = _DummySettings()

    assert service._compute_next_retry_at(success=True, attempt=1) is None


def test_compute_next_retry_at_failure(monkeypatch):
    service = WebhookService.__new__(WebhookService)
    service.settings = _DummySettings()

    dt = service._compute_next_retry_at(success=False, attempt=1)
    assert dt is not None
    assert dt > datetime.now(timezone.utc)


def test_compute_next_retry_at_exhausted(monkeypatch):
    service = WebhookService.__new__(WebhookService)
    service.settings = _DummySettings()

    assert service._compute_next_retry_at(success=False, attempt=3) is None
