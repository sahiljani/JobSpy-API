#!/usr/bin/env python3
"""
Run JobSpy using search terms from resume-tailor-app DB + saved proxies.

- Reads active search terms from Laravel model: App\Models\JobSearchSetting
- Uses first 10 proxies from SEO/scraping_proxies.txt
- Scrapes per-site with a few safety cases to avoid common parameter conflicts
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from jobspy import scrape_jobs

WORKSPACE = Path("/home/sahil/.openclaw/workspace")
RESUME_APP = WORKSPACE / "resume-tailor-app"
PROXY_FILE = WORKSPACE / "SEO" / "scraping_proxies.txt"
OUT_DIR = WORKSPACE / "JobSpy"

DEFAULT_SITES = ["indeed", "linkedin", "zip_recruiter", "google"]
DEFAULT_RESULTS_WANTED = 20
DEFAULT_HOURS_OLD = 72
DEFAULT_COUNTRY_INDEED = "USA"


def _extract_json_array(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        raise RuntimeError("Could not parse JSON from artisan output.")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise RuntimeError("Expected a JSON array from Laravel query.")
    return [row for row in parsed if isinstance(row, dict)]


def load_active_search_settings() -> list[dict[str, Any]]:
    if not RESUME_APP.exists():
        raise RuntimeError(f"resume project not found: {RESUME_APP}")

    php = (
        "echo json_encode("
        "App\\Models\\JobSearchSetting::query()"
        "->where('is_active', true)"
        "->whereNull('deleted_at')"
        "->orderBy('sort_order')"
        "->orderBy('id')"
        "->get(['search_term','location','remote_preference','seniority_level'])"
        "->toArray()"
        ");"
    )

    proc = subprocess.run(
        ["php", "artisan", "tinker", "--execute", php],
        cwd=str(RESUME_APP),
        check=False,
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Failed reading search settings via artisan: {proc.stderr.strip()}")

    settings = _extract_json_array(proc.stdout)
    # Keep only rows with real search_term values.
    settings = [
        row
        for row in settings
        if str(row.get("search_term", "")).strip()
    ]
    return settings


def load_proxies(limit: int = 10) -> list[str]:
    if not PROXY_FILE.exists():
        raise RuntimeError(f"Proxy file not found: {PROXY_FILE}")

    proxies: list[str] = []
    for line in PROXY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(":")
        if len(parts) != 4:
            # skip malformed lines, keep going
            continue

        host, port, username, password = parts
        proxies.append(f"{username}:{password}@{host}:{port}")

        if len(proxies) >= limit:
            break

    if not proxies:
        raise RuntimeError("No valid proxies found in scraping_proxies.txt")

    return proxies


def build_google_term(search_term: str, location: str | None) -> str:
    place = (location or "United States").strip()
    return f"{search_term} jobs near {place} since yesterday"


def scrape_one_site(site: str, setting: dict[str, Any], proxies: list[str]) -> pd.DataFrame:
    search_term = str(setting.get("search_term", "")).strip()
    location = str(setting.get("location") or "").strip() or "United States"
    remote_pref = str(setting.get("remote_preference") or "any").strip().lower()

    params: dict[str, Any] = {
        "site_name": [site],
        "search_term": search_term,
        "location": location,
        "results_wanted": int(os.getenv("JOBSPY_RESULTS_WANTED", DEFAULT_RESULTS_WANTED)),
        "hours_old": int(os.getenv("JOBSPY_HOURS_OLD", DEFAULT_HOURS_OLD)),
        "proxies": proxies,
        "country_indeed": os.getenv("JOBSPY_COUNTRY_INDEED", DEFAULT_COUNTRY_INDEED),
        "google_search_term": build_google_term(search_term, location),
        "verbose": int(os.getenv("JOBSPY_VERBOSE", "1")),
    }

    # Case handling: remote preference
    # Indeed has filter limitations; keep it simple and stable.
    if remote_pref == "remote":
        if site in {"indeed", "google"}:
            params["location"] = "Remote"
        # Avoid setting is_remote for indeed due to limitation conflicts with hours_old.
        if site in {"linkedin", "zip_recruiter"}:
            params["is_remote"] = True

    # Google really relies on google_search_term syntax.
    if site == "google":
        params["google_search_term"] = build_google_term(search_term, params.get("location"))

    return scrape_jobs(**params)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sites_env = os.getenv("JOBSPY_SITES", "")
    sites = [s.strip() for s in sites_env.split(",") if s.strip()] or DEFAULT_SITES

    try:
        settings = load_active_search_settings()
        proxies = load_proxies(limit=10)
    except Exception as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 1

    if not settings:
        print("No active search settings found in resume-tailor-app DB.")
        return 0

    all_frames: list[pd.DataFrame] = []
    run_log: list[dict[str, Any]] = []

    for idx, setting in enumerate(settings, start=1):
        search_term = str(setting.get("search_term", "")).strip()
        for site in sites:
            try:
                df = scrape_one_site(site, setting, proxies)
                if not df.empty:
                    # annotate provenance
                    df["source_search_term"] = search_term
                    df["source_remote_preference"] = setting.get("remote_preference")
                    df["source_seniority_level"] = setting.get("seniority_level")
                    all_frames.append(df)

                run_log.append(
                    {
                        "setting_index": idx,
                        "search_term": search_term,
                        "site": site,
                        "rows": int(len(df)),
                        "status": "ok",
                    }
                )
                print(f"[ok] setting #{idx} | {site} | rows={len(df)} | term='{search_term}'")
            except Exception as exc:  # keep going across settings/sites
                run_log.append(
                    {
                        "setting_index": idx,
                        "search_term": search_term,
                        "site": site,
                        "rows": 0,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                print(f"[warn] setting #{idx} | {site} failed: {exc}")

    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        # best-effort dedupe on canonical URL if present
        url_col = "job_url" if "job_url" in combined.columns else None
        if url_col:
            combined = combined.drop_duplicates(subset=[url_col], keep="first")

        out_csv = OUT_DIR / "jobs.csv"
        combined.to_csv(out_csv, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
        print(f"Saved {len(combined)} rows to {out_csv}")
    else:
        print("No rows scraped.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = OUT_DIR / f"run-log-{ts}.json"
    log_path.write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    print(f"Saved run log: {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
