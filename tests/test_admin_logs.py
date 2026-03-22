import os
from pathlib import Path

from app.services.log_diagnostics import LogDiagnosticsService

API_KEY = os.getenv('API_KEY', 'change-me')


def test_log_diagnostics_tail_caps_lines(tmp_path: Path):
    log_file = tmp_path / 'jobspy.log'
    log_file.write_text('\n'.join(f'line-{i}' for i in range(1200)), encoding='utf-8')

    result = LogDiagnosticsService().tail_log(str(log_file), limit=1000)

    assert result['ok'] is True
    assert result['line_count'] == 1000
    assert result['lines'][0] == 'line-200'
    assert result['lines'][-1] == 'line-1199'


def test_log_diagnostics_flags_proxy_errors():
    text = '\n'.join([
        'ERROR requests ProxyError tunnel connection failed',
        'WARNING upstream 407 proxy authentication required',
    ])

    result = LogDiagnosticsService().diagnose(text, 'is proxy the problem?')

    assert result['ok'] is True
    assert result['top_category'] == 'proxy'
    assert len(result['suggestions']) > 0


def test_admin_log_endpoints_require_api_key(test_client):
    resp = test_client.get('/v1/admin/logs/tail')
    assert resp.status_code == 401


def test_admin_log_tail_endpoint_returns_content(test_client):
    from app.core.config import get_settings

    settings = get_settings()
    log_path = Path(settings.log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text('hello\nworld\n', encoding='utf-8')

    resp = test_client.get('/v1/admin/logs/tail?limit=2', headers={'X-API-Key': API_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['line_count'] == 2
    assert body['lines'] == ['hello', 'world']


def test_admin_log_diagnose_endpoint_returns_summary(test_client):
    resp = test_client.post(
        '/v1/admin/logs/diagnose',
        headers={'X-API-Key': API_KEY},
        json={
            'log_text': 'ERROR 407 proxy authentication required',
            'prompt': 'tell me whether proxy is the issue',
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['ok'] is True
    assert body['top_category'] == 'proxy'
