import csv
import json
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs

work = Path('/work')
terms = json.loads((work / 'search_terms.json').read_text())
terms = [t for t in terms if isinstance(t, str) and t.strip()][:4]

proxy_lines = [
    l.strip()
    for l in (work / 'scraping_proxies.txt').read_text().splitlines()
    if l.strip() and not l.strip().startswith('#')
]

proxies = []
for line in proxy_lines:
    parts = line.split(':')
    if len(parts) == 4:
        host, port, user, pwd = parts
        proxies.append(f'{user}:{pwd}@{host}:{port}')
proxies = proxies[:10]

all_df = []
logs = []

for term in terms:
    for site in ['indeed', 'linkedin', 'zip_recruiter']:
        try:
            df = scrape_jobs(
                site_name=[site],
                search_term=term,
                location='Canada',
                results_wanted=6,
                hours_old=48,
                country_indeed='Canada',
                proxies=proxies,
                google_search_term=f'{term} jobs in Canada since yesterday',
                verbose=0,
            )
            if not df.empty:
                df['source_search_term'] = term
                df['source_site'] = site
                all_df.append(df)
            logs.append({'term': term, 'site': site, 'rows': len(df), 'status': 'ok'})
            print(f"ok  | {site:12} | {len(df):3} | {term}")
        except Exception as exc:
            logs.append({'term': term, 'site': site, 'rows': 0, 'status': 'error', 'error': str(exc)})
            print(f"err | {site:12} |   0 | {term} | {exc}")

if all_df:
    out = pd.concat(all_df, ignore_index=True)
    if 'job_url' in out.columns:
        out = out.drop_duplicates(subset=['job_url'])
    out.to_csv(work / 'jobs-canada-48h-test.csv', quoting=csv.QUOTE_NONNUMERIC, escapechar='\\', index=False)
    print('saved_csv', len(out))
else:
    print('saved_csv', 0)

(work / 'run-log-canada-48h.json').write_text(json.dumps(logs, indent=2))
print('saved_log', len(logs))
