from app.core.security import generate_webhook_signature


def test_generate_webhook_signature_stable():
    sig = generate_webhook_signature('secret123', '2026-03-15T00:00:00Z', '{"a":1}')
    assert sig.startswith('sha256=')
    assert len(sig) > 20
