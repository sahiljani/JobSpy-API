def test_job_lifecycle_with_eager_worker(test_client):
    payload = {
        'search_terms': ['SEO Specialist', 'Laravel Developer'],
        'sites': ['indeed', 'linkedin'],
        'location': 'Canada',
        'hours_old': 48,
        'results_wanted': 10,
        'country_indeed': 'Canada',
        'options': {
            'max_runtime_sec': 1800,
            'dedupe_by': 'job_url',
            'progress_interval_sec': 5,
            'emit_partial_results': True,
        },
    }

    resp = test_client.post(
        '/v1/jobs',
        json=payload,
        headers={
            'X-API-Key': 'change-me',
            'X-Idempotency-Key': 'it-eager-001',
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    job_id = body['job_id']

    status_resp = test_client.get(f'/v1/jobs/{job_id}', headers={'X-API-Key': 'change-me'})
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status['status'] in {'completed'}
    assert status['total_units'] == 4
    assert status['completed_units'] == 4
    assert status['failed_units'] == 0

    events_resp = test_client.get(f'/v1/jobs/{job_id}/events', headers={'X-API-Key': 'change-me'})
    assert events_resp.status_code == 200
    events_body = events_resp.json()
    assert len(events_body['events']) >= 2

    results_resp = test_client.get(f'/v1/jobs/{job_id}/results', headers={'X-API-Key': 'change-me'})
    assert results_resp.status_code == 200
    results_body = results_resp.json()
    assert len(results_body['results']) > 0


def test_idempotency_reuses_job_id(test_client):
    payload = {
        'search_terms': ['SEO Specialist'],
        'sites': ['indeed'],
    }

    headers = {
        'X-API-Key': 'change-me',
        'X-Idempotency-Key': 'it-idempotent-123',
    }

    r1 = test_client.post('/v1/jobs', json=payload, headers=headers)
    r2 = test_client.post('/v1/jobs', json=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()['job_id'] == r2.json()['job_id']
