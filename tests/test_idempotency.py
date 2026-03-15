from app.schemas.jobs import JobCreateRequest


def test_schema_accepts_basic_payload():
    req = JobCreateRequest(search_terms=['SEO Specialist'], sites=['indeed'])
    assert req.search_terms == ['SEO Specialist']
    assert req.sites == ['indeed']
