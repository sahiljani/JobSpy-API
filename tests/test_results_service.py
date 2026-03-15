from app.services.results_service import ResultsService


def test_compute_dedupe_hash_prefers_url():
    svc = ResultsService.__new__(ResultsService)
    h1 = svc.compute_dedupe_hash({'job_url': 'https://example.com/job/1/'}, 'SEO', 'indeed')
    h2 = svc.compute_dedupe_hash({'job_url': 'https://example.com/job/1'}, 'SEO', 'indeed')
    assert h1 == h2


def test_compute_dedupe_hash_fallback():
    svc = ResultsService.__new__(ResultsService)
    row = {
        'title': 'SEO Specialist',
        'company': 'Acme',
        'location': 'Canada',
        'date_posted': '2026-03-15',
    }
    h = svc.compute_dedupe_hash(row, 'SEO Specialist', 'linkedin')
    assert isinstance(h, str)
    assert len(h) == 64
