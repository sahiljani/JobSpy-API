from unittest.mock import Mock, patch

from app.core.security import encrypt_secret, generate_webhook_signature
from app.db.models import Job
from app.services.event_service import EventService
from app.services.webhook_service import WebhookService


def test_dispatch_event_sends_event_sequence_header(db_session):
    job = Job(
        id=Job.new_id(),
        status='running',
        request_json={'search_terms': ['Laravel Developer'], 'sites': ['indeed']},
        options_json={},
        webhook_url='https://resume-tailor.test/webhooks/jobspy',
        webhook_secret=encrypt_secret('test-webhook-secret', 'change-me-encryption-seed'),
        total_units=1,
    )
    db_session.add(job)
    db_session.flush()

    event = EventService(db_session).emit(
        job.id,
        'job.progress',
        {
            'status': 'running',
            'progress_percent': 50,
        },
    )

    response = Mock(status_code=204, text='')

    with patch('app.services.webhook_service.httpx.post', return_value=response) as mock_post:
        success = WebhookService(db_session).dispatch_event(job, event)

    assert success is True

    _, kwargs = mock_post.call_args
    headers = kwargs['headers']
    body = kwargs['content'].decode('utf-8')

    assert headers['X-Webhook-Event'] == 'job.progress'
    assert headers['X-Webhook-Event-Id'] == event.id
    assert headers['X-Webhook-Job-Id'] == job.id
    assert headers['X-Webhook-Event-Sequence'] == str(event.sequence)
    assert headers['X-Webhook-Signature'] == generate_webhook_signature(
        'test-webhook-secret',
        headers['X-Webhook-Timestamp'],
        body,
    )
