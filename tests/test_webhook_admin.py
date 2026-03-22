import os


API_KEY = os.getenv('API_KEY', 'change-me')


def test_admin_dlq_endpoint(test_client):
    resp = test_client.get('/v1/admin/webhooks/dlq', headers={'X-API-Key': API_KEY})
    assert resp.status_code == 200
    assert 'items' in resp.json()
