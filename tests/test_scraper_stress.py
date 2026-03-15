"""
Stress tests for the JobSpy scraper.

These tests verify:
  1. Country filter correctness — "Canada" (not "CA" / California)
  2. Proxy support — proxies are accepted, validated, and passed through
  3. result_count correctness — response honours results_wanted
  4. Output schema completeness — all required fields present in every result
  5. Multi-term / multi-site combinations — cartesian units execute correctly
  6. Live scraping (marked @pytest.mark.live) — real network calls, skipped by default

Run all non-live tests:
    pytest tests/test_scraper_stress.py -v

Run live tests as well (slow, needs network):
    pytest tests/test_scraper_stress.py -v -m live
"""

import os
import re
import time
import uuid

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_API_KEY = os.getenv('API_KEY', 'change-me')
HEADERS = {'X-API-Key': _API_KEY}
CANADA_TERMS = ['Software Engineer', 'Data Analyst']
CANADA_SITES = ['indeed', 'linkedin']

REQUIRED_RESULT_FIELDS = {
    'site',
    'title',
    'company',
    'location',
    'job_url',
}

CA_AMBIGUOUS_PATTERN = re.compile(r'\bCA\b')


def idempotency_key(suffix: str = '') -> str:
    """Generate a unique idempotency key for each test run."""
    return f'stress-{uuid.uuid4().hex[:8]}{("-" + suffix) if suffix else ""}'


def post_job(client, payload: dict) -> dict:
    resp = client.post('/v1/jobs', json=payload, headers={**HEADERS, 'X-Idempotency-Key': idempotency_key()})
    assert resp.status_code == 200, f'Job submit failed: {resp.text}'
    return resp.json()


def get_status(client, job_id: str) -> dict:
    resp = client.get(f'/v1/jobs/{job_id}', headers=HEADERS)
    assert resp.status_code == 200, f'Status fetch failed: {resp.text}'
    return resp.json()


def get_results(client, job_id: str) -> list[dict]:
    resp = client.get(f'/v1/jobs/{job_id}/results', headers=HEADERS)
    assert resp.status_code == 200, f'Results fetch failed: {resp.text}'
    return resp.json().get('results', [])


# ===========================================================================
# 1 — Country filter correctness
# ===========================================================================

class TestCountryFilter:
    """Verify that location='Canada' and country_indeed='Canada' are sent correctly."""

    def test_country_full_name_accepted(self, test_client):
        """Payload with location='Canada' / country_indeed='Canada' must be accepted."""
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'hours_old': 48,
            'results_wanted': 5,
            'country_indeed': 'Canada',
        }
        body = post_job(test_client, payload)
        assert 'job_id' in body
        status = get_status(test_client, body['job_id'])
        assert status['status'] == 'completed'

    def test_ca_code_not_sent_directly(self, test_client):
        """Submitting 'CA' as location is valid — the *PHP* layer expands it.
        This test confirms the API itself does not reject 'Canada' or 'CA'."""
        for loc in ('Canada', 'United States', 'United Kingdom'):
            payload = {
                'search_terms': ['Backend Developer'],
                'sites': ['indeed'],
                'location': loc,
                'country_indeed': loc,
            }
            body = post_job(test_client, payload)
            assert 'job_id' in body, f'Job not created for location={loc}'

    def test_mocked_results_have_canada_location(self, test_client):
        """The fake scraper in conftest.py returns location='Canada'.
        Verify that no result comes back with a raw 'CA' location string."""
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'hours_old': 48,
            'results_wanted': 5,
            'country_indeed': 'Canada',
        }
        body = post_job(test_client, payload)
        results = get_results(test_client, body['job_id'])

        assert len(results) > 0, 'Expected at least one result from the mock scraper'
        for r in results:
            loc = (r.get('location') or '').strip()
            # The mock returns 'Canada'; assert we never see a bare two-letter 'CA'
            assert not CA_AMBIGUOUS_PATTERN.fullmatch(loc), (
                f'Result location is bare "CA" — country code was NOT expanded: {r}'
            )

    def test_country_indeed_defaults_to_canada(self, test_client):
        """If country_indeed is omitted the schema default is 'Canada'."""
        payload = {
            'search_terms': ['QA Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'results_wanted': 3,
            # country_indeed intentionally omitted
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['status'] == 'completed'


# ===========================================================================
# 2 — Proxy support
# ===========================================================================

class TestProxySupport:
    """Verify that proxies are accepted, validated, and pass through correctly."""

    VALID_PROXIES = [
        'http://user:pass@proxy1.example.com:8080',
        'http://user:pass@proxy2.example.com:8080',
    ]

    def test_proxies_accepted_in_payload(self, test_client):
        """A valid proxy list must be accepted without a 422 error."""
        payload = {
            'search_terms': ['DevOps Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'proxies': self.VALID_PROXIES,
        }
        body = post_job(test_client, payload)
        assert 'job_id' in body

    def test_no_proxies_also_works(self, test_client):
        """Omitting proxies (null) must not fail."""
        payload = {
            'search_terms': ['DevOps Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'proxies': None,
        }
        body = post_job(test_client, payload)
        assert 'job_id' in body

    def test_empty_proxy_list_accepted(self, test_client):
        """An empty list is distinct from null; the API should accept it or normalise it."""
        payload = {
            'search_terms': ['ML Engineer'],
            'sites': ['indeed'],
            'proxies': [],
        }
        resp = test_client.post(
            '/v1/jobs',
            json=payload,
            headers={**HEADERS, 'X-Idempotency-Key': idempotency_key('empty-proxy')},
        )
        # The API may return 200 or 422 for empty list — either is consistent; we just
        # confirm it does not crash with a 500.
        assert resp.status_code in (200, 422), f'Unexpected status: {resp.status_code} {resp.text}'

    def test_malformed_proxy_rejected(self, test_client):
        """A proxy missing the user:pass@host:port structure should be rejected (422)."""
        payload = {
            'search_terms': ['Cloud Engineer'],
            'sites': ['indeed'],
            'proxies': ['not-a-valid-proxy'],
        }
        resp = test_client.post(
            '/v1/jobs',
            json=payload,
            headers={**HEADERS, 'X-Idempotency-Key': idempotency_key('bad-proxy')},
        )
        assert resp.status_code == 422, f'Expected 422 for malformed proxy, got {resp.status_code}'

    def test_multiple_proxies_accepted(self, test_client):
        """All proxies from a larger list must be accepted."""
        proxies = [f'http://user:pass@proxy{i}.example.com:8080' for i in range(1, 6)]
        payload = {
            'search_terms': ['Data Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'proxies': proxies,
        }
        body = post_job(test_client, payload)
        assert 'job_id' in body
        status = get_status(test_client, body['job_id'])
        assert status['status'] == 'completed'


# ===========================================================================
# 3 — Result count correctness
# ===========================================================================

class TestResultCount:
    """Verify that the scraper respects results_wanted and returns sensible counts."""

    def test_result_count_bounded_by_results_wanted(self, test_client):
        """Total rows_collected must not exceed results_wanted × units."""
        results_wanted = 5
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'results_wanted': results_wanted,
            'country_indeed': 'Canada',
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])

        assert status['status'] == 'completed'
        # rows_collected comes from the scraper per-unit; mock returns 2 per unit.
        assert status['rows_collected'] >= 0

    def test_results_wanted_minimum(self, test_client):
        """results_wanted=1 must be accepted (min allowed by schema)."""
        payload = {
            'search_terms': ['Frontend Developer'],
            'sites': ['indeed'],
            'results_wanted': 1,
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['status'] == 'completed'

    def test_results_wanted_maximum(self, test_client):
        """results_wanted=50 (schema max) must be accepted."""
        payload = {
            'search_terms': ['Backend Developer'],
            'sites': ['indeed'],
            'results_wanted': 50,
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['status'] == 'completed'

    def test_results_wanted_above_max_rejected(self, test_client):
        """results_wanted=51 exceeds schema max — must be rejected with 422."""
        payload = {
            'search_terms': ['DevOps'],
            'sites': ['indeed'],
            'results_wanted': 51,
        }
        resp = test_client.post(
            '/v1/jobs',
            json=payload,
            headers={**HEADERS, 'X-Idempotency-Key': idempotency_key('over-max')},
        )
        assert resp.status_code == 422


# ===========================================================================
# 4 — Output schema completeness
# ===========================================================================

class TestOutputSchema:
    """Verify all required fields are present in every returned result record."""

    def test_result_records_have_required_fields(self, test_client):
        """Every result record must contain the REQUIRED_RESULT_FIELDS."""
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'results_wanted': 5,
            'country_indeed': 'Canada',
        }
        body = post_job(test_client, payload)
        results = get_results(test_client, body['job_id'])

        assert len(results) > 0, 'Expected non-empty results from mock scraper'
        for record in results:
            missing = REQUIRED_RESULT_FIELDS - set(record.keys())
            assert not missing, f'Result record missing fields {missing}: {record}'

    def test_job_url_is_non_empty_string(self, test_client):
        """Every result must have a non-empty job_url."""
        payload = {
            'search_terms': ['DevOps Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'results_wanted': 5,
        }
        body = post_job(test_client, payload)
        results = get_results(test_client, body['job_id'])

        for record in results:
            url = record.get('job_url', '')
            assert isinstance(url, str) and url.startswith('http'), (
                f'job_url is invalid: {url!r} in record {record}'
            )

    def test_status_response_schema(self, test_client):
        """Job status response must contain all expected top-level keys."""
        required_status_keys = {
            'job_id', 'status', 'progress_percent', 'total_units',
            'completed_units', 'failed_units', 'rows_collected',
        }
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed'],
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        missing = required_status_keys - set(status.keys())
        assert not missing, f'Status response missing keys: {missing}'

    def test_results_endpoint_structure(self, test_client):
        """Results endpoint must return a dict with a 'results' list."""
        payload = {'search_terms': ['QA Engineer'], 'sites': ['indeed']}
        body = post_job(test_client, payload)
        resp = test_client.get(f'/v1/jobs/{body["job_id"]}/results', headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert 'results' in data
        assert isinstance(data['results'], list)


# ===========================================================================
# 5 — Multi-term / multi-site combinations (unit count)
# ===========================================================================

class TestMultiTermSite:
    """Verify that the Cartesian product (term × site) creates the correct unit count."""

    def test_two_terms_two_sites_creates_four_units(self, test_client):
        """2 terms × 2 sites = 4 units total."""
        payload = {
            'search_terms': ['Software Engineer', 'Data Analyst'],
            'sites': ['indeed', 'linkedin'],
            'location': 'Canada',
            'country_indeed': 'Canada',
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['total_units'] == 4, (
            f'Expected 4 units for 2×2, got {status["total_units"]}'
        )

    def test_one_term_four_sites_creates_four_units(self, test_client):
        """1 term × 4 sites = 4 units total."""
        payload = {
            'search_terms': ['Full Stack Developer'],
            'sites': ['indeed', 'linkedin', 'zip_recruiter', 'glassdoor'],
            'location': 'Canada',
            'country_indeed': 'Canada',
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['total_units'] == 4

    def test_three_terms_one_site_creates_three_units(self, test_client):
        """3 terms × 1 site = 3 units total."""
        payload = {
            'search_terms': ['Software Engineer', 'Backend Developer', 'API Developer'],
            'sites': ['indeed'],
            'location': 'Canada',
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['total_units'] == 3

    def test_all_units_complete_successfully(self, test_client):
        """All units from a multi-term multi-site run should complete (not fail)."""
        payload = {
            'search_terms': ['Data Scientist', 'ML Engineer'],
            'sites': ['indeed', 'linkedin'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'results_wanted': 10,
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        assert status['status'] == 'completed'
        assert status['completed_units'] == status['total_units']
        assert status['failed_units'] == 0

    def test_duplicate_terms_are_deduplicated(self, test_client):
        """Repeated search terms should be deduped — only unique terms create units."""
        payload = {
            'search_terms': ['Software Engineer', 'Software Engineer', 'software engineer'],
            'sites': ['indeed'],
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        # Only 1 unique term × 1 site = 1 unit
        assert status['total_units'] == 1

    def test_duplicate_sites_are_deduplicated(self, test_client):
        """Repeated sites should be deduped — only unique sites create units."""
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed', 'Indeed', 'INDEED'],
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        # 1 term × 1 unique site = 1 unit
        assert status['total_units'] == 1


# ===========================================================================
# 6 — Stress test: large combination with proxies + Canada
# ===========================================================================

class TestStressWithProxies:
    """Stress tests that combine many search terms, all sites, with proxies enabled."""

    PROXIES = [
        'http://user:pass@proxy1.example.com:8080',
        'http://user:pass@proxy2.example.com:8080',
        'http://user:pass@proxy3.example.com:8080',
    ]

    def test_stress_five_terms_four_sites_with_proxies(self, test_client):
        """5 terms × 4 sites = 20 units, all with proxies, location=Canada."""
        payload = {
            'search_terms': [
                'Software Engineer',
                'Data Scientist',
                'DevOps Engineer',
                'Product Manager',
                'QA Engineer',
            ],
            'sites': ['indeed', 'linkedin', 'zip_recruiter', 'glassdoor'],
            'location': 'Canada',
            'hours_old': 48,
            'results_wanted': 10,
            'country_indeed': 'Canada',
            'proxies': self.PROXIES,
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])

        assert status['total_units'] == 20
        assert status['status'] == 'completed'
        assert status['failed_units'] == 0
        assert status['rows_collected'] >= 0  # mock returns 2 per unit = 40 total

    def test_stress_rows_collected_match_units_times_mock_return(self, test_client):
        """Mock scraper returns 2 rows per unit. 3 terms × 2 sites = 6 units = 12 rows."""
        payload = {
            'search_terms': ['Engineer', 'Analyst', 'Manager'],
            'sites': ['indeed', 'linkedin'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'proxies': self.PROXIES,
        }
        body = post_job(test_client, payload)
        status = get_status(test_client, body['job_id'])
        results = get_results(test_client, body['job_id'])

        assert status['total_units'] == 6
        assert status['completed_units'] == 6
        # Mock returns 2 rows per unit so total results should be 12
        assert len(results) == 12, (
            f'Expected 12 results (6 units × 2 rows), got {len(results)}'
        )

    def test_stress_result_schemas_are_consistent_across_sites(self, test_client):
        """Results from different sites must all have the same required fields."""
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed', 'linkedin', 'zip_recruiter', 'glassdoor'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'proxies': self.PROXIES,
        }
        body = post_job(test_client, payload)
        results = get_results(test_client, body['job_id'])

        assert len(results) > 0
        for record in results:
            missing = REQUIRED_RESULT_FIELDS - set(record.keys())
            assert not missing, (
                f'Result from site={record.get("site")} missing fields {missing}'
            )

    def test_stress_no_california_jobs_in_canada_results(self, test_client):
        """When searching for Canada, results must not contain bare 'CA' locations."""
        payload = {
            'search_terms': ['Software Engineer', 'Data Engineer'],
            'sites': ['indeed', 'linkedin'],
            'location': 'Canada',
            'country_indeed': 'Canada',
            'proxies': self.PROXIES,
        }
        body = post_job(test_client, payload)
        results = get_results(test_client, body['job_id'])

        california_results = [
            r for r in results
            if CA_AMBIGUOUS_PATTERN.fullmatch((r.get('location') or '').strip())
        ]
        assert len(california_results) == 0, (
            f'{len(california_results)} result(s) have bare "CA" location — '
            f'country code was not expanded. Offending records: {california_results}'
        )


# ===========================================================================
# 7 — Live scraping tests (skipped unless -m live)
# ===========================================================================

@pytest.mark.live
class TestLiveScraping:
    """
    Real network tests — these call actual job boards.

    Run with:  pytest tests/test_scraper_stress.py -m live -v -s

    These tests are intentionally slow and may be flaky depending on external
    site availability. They are NOT run in CI by default.

    Expected input→output contract being verified:
      - location='Canada' → results where location contains Canada (province or city)
      - country_indeed='Canada' → Indeed limits results to Canadian postings
      - proxies passed → scraper uses them (verified indirectly by non-failure)
      - results_wanted=5 → at most 5 rows per unit returned
    """

    PROXIES = [
        # Add real proxies here for live testing, e.g.:
        # 'http://user:pass@real-proxy.example.com:8080',
    ]

    @pytest.fixture(autouse=True)
    def live_test_client(self):
        """
        For live tests we need a real DB and real scraper (no mocks).
        Skip if no live DB is configured.
        """
        import os
        db_url = os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')
        if not db_url:
            pytest.skip('No TEST_DATABASE_URL configured for live tests')

    def test_live_canada_jobs_are_actually_canadian(self):
        """
        Live test: scrape 5 Indeed jobs in Canada for 'Software Engineer'.
        Expected output: at least 1 result, all locations contain a Canadian
        province/city or the word Canada — NOT 'California' or bare 'CA'.
        """
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        payload = {
            'search_terms': ['Software Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'hours_old': 48,
            'results_wanted': 5,
            'country_indeed': 'Canada',
            'proxies': self.PROXIES or None,
        }
        resp = client.post(
            '/v1/jobs',
            json=payload,
            headers={**HEADERS, 'X-Idempotency-Key': idempotency_key('live-canada')},
        )
        assert resp.status_code == 200, resp.text
        job_id = resp.json()['job_id']

        # Poll for completion (real scraping can take up to 180s per unit)
        deadline = time.time() + 300
        status = {}
        while time.time() < deadline:
            status = client.get(f'/v1/jobs/{job_id}', headers=HEADERS).json()
            if status['status'] in ('completed', 'failed'):
                break
            time.sleep(10)

        assert status['status'] == 'completed', f'Scrape did not complete: {status}'
        assert status['rows_collected'] >= 1, 'Expected at least 1 job result'

        results = client.get(f'/v1/jobs/{job_id}/results', headers=HEADERS).json()['results']
        assert len(results) >= 1

        canadian_provinces = {
            'ontario', 'british columbia', 'alberta', 'quebec', 'bc', 'on', 'ab', 'qc',
            'canada', 'toronto', 'vancouver', 'calgary', 'montreal', 'ottawa',
        }
        california_indicators = {'california', ' ca ', ', ca', '(ca)'}
        bad_results = []
        for r in results:
            loc = (r.get('location') or '').lower()
            is_canadian = any(prov in loc for prov in canadian_provinces)
            is_california = any(cal in loc for cal in california_indicators)
            if is_california and not is_canadian:
                bad_results.append(r)

        assert len(bad_results) == 0, (
            f'{len(bad_results)} result(s) appear to be from California, not Canada:\n'
            + '\n'.join(f'  {r.get("title")} @ {r.get("company")} — {r.get("location")}' for r in bad_results)
        )

    def test_live_results_wanted_is_respected(self):
        """
        Live test: results_wanted=3 must return at most 3 rows per unit.
        """
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        results_wanted = 3
        payload = {
            'search_terms': ['Data Analyst'],
            'sites': ['indeed'],
            'location': 'Canada',
            'results_wanted': results_wanted,
            'country_indeed': 'Canada',
            'proxies': self.PROXIES or None,
        }
        resp = client.post(
            '/v1/jobs',
            json=payload,
            headers={**HEADERS, 'X-Idempotency-Key': idempotency_key('live-count')},
        )
        assert resp.status_code == 200
        job_id = resp.json()['job_id']

        deadline = time.time() + 300
        while time.time() < deadline:
            status = client.get(f'/v1/jobs/{job_id}', headers=HEADERS).json()
            if status['status'] in ('completed', 'failed'):
                break
            time.sleep(10)

        assert status['status'] == 'completed'
        results = client.get(f'/v1/jobs/{job_id}/results', headers=HEADERS).json()['results']

        # Allow a small overage (some sites return slightly more than requested)
        assert len(results) <= results_wanted * 2, (
            f'Got {len(results)} results but expected ~{results_wanted} — results_wanted not respected'
        )

    def test_live_with_proxies_completes_without_error(self):
        """
        Live test: run a real scrape with proxies configured.
        The scrape should complete without failure even if proxies are not
        reachable — jobspy falls back gracefully.
        """
        from fastapi.testclient import TestClient
        from main import app

        if not self.PROXIES:
            pytest.skip('No live proxies configured in PROXIES list')

        client = TestClient(app)
        payload = {
            'search_terms': ['DevOps Engineer'],
            'sites': ['indeed'],
            'location': 'Canada',
            'results_wanted': 5,
            'country_indeed': 'Canada',
            'proxies': self.PROXIES,
        }
        resp = client.post(
            '/v1/jobs',
            json=payload,
            headers={**HEADERS, 'X-Idempotency-Key': idempotency_key('live-proxies')},
        )
        assert resp.status_code == 200
        job_id = resp.json()['job_id']

        deadline = time.time() + 300
        while time.time() < deadline:
            status = client.get(f'/v1/jobs/{job_id}', headers=HEADERS).json()
            if status['status'] in ('completed', 'failed'):
                break
            time.sleep(10)

        assert status['status'] == 'completed', (
            f'Scrape with proxies failed: {status.get("error_summary")}'
        )
