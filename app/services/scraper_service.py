from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

from jobspy import scrape_jobs

# Per-unit timeout. Celery workers are daemon processes so we cannot spawn
# child processes. We use a thread instead — it cannot be forcibly killed but
# the orchestrator will stop waiting and continue with the next unit.
UNIT_TIMEOUT_SEC = 120


@dataclass
class ScrapeResult:
    ok: bool
    rows: int
    sample: list[dict[str, Any]]
    items: list[dict[str, Any]]
    error_code: str | None = None
    error_message: str | None = None


class ScraperService:
    def scrape_unit(
        self,
        *,
        site: str,
        search_term: str,
        location: str,
        hours_old: int,
        results_wanted: int,
        country_indeed: str,
        proxies: list[str] | None,
    ) -> ScrapeResult:
        params: dict[str, Any] = {
            'site_name': [site],
            'search_term': search_term,
            'location': location,
            'results_wanted': results_wanted,
            'hours_old': hours_old,
            'country_indeed': country_indeed,
            'proxies': proxies,
            'google_search_term': f'{search_term} jobs near {location} since yesterday',
            'verbose': 0,
        }

        executor = ThreadPoolExecutor(max_workers=1)
        future: Future = executor.submit(scrape_jobs, **params)

        try:
            df = future.result(timeout=UNIT_TIMEOUT_SEC)
        except FuturesTimeoutError:
            executor.shutdown(wait=False)
            return ScrapeResult(
                ok=False,
                rows=0,
                sample=[],
                items=[],
                error_code='UNIT_TIMEOUT',
                error_message=f'{site} scrape timed out after {UNIT_TIMEOUT_SEC}s — skipping unit',
            )
        except Exception as exc:
            executor.shutdown(wait=False)
            return ScrapeResult(
                ok=False,
                rows=0,
                sample=[],
                items=[],
                error_code='SCRAPE_ERROR',
                error_message=str(exc)[:1000],
            )
        finally:
            executor.shutdown(wait=False)

        sample: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        if not df.empty:
            cols = [c for c in ['site', 'title', 'company', 'location', 'job_url', 'date_posted'] if c in df.columns]
            if cols:
                sample = df[cols].head(3).to_dict(orient='records')
            items = df.to_dict(orient='records')

        return ScrapeResult(ok=True, rows=len(items), sample=sample, items=items)
