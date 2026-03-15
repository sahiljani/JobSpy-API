import pytest
from pydantic import ValidationError

from app.schemas.jobs import JobCreateRequest


def test_job_create_request_normalizes_terms_and_sites():
    payload = JobCreateRequest(
        search_terms=[' SEO Specialist ', 'seo specialist', 'Laravel Developer'],
        sites=['Indeed', 'linkedin', 'linkedin'],
    )
    assert payload.search_terms == ['SEO Specialist', 'Laravel Developer']
    assert payload.sites == ['indeed', 'linkedin']


def test_job_create_request_rejects_invalid_site():
    with pytest.raises(ValidationError):
        JobCreateRequest(search_terms=['x'], sites=['craigslist'])
