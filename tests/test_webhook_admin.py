def test_admin_dlq_endpoint(test_client):
    resp = test_client.get('/v1/admin/webhooks/dlq', headers={'X-API-Key': 'change-me'})
    assert resp.status_code == 200
    assert 'items' in resp.json()
