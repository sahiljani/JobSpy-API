from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


class LogDiagnosticsService:
    MAX_LINES = 1000

    def tail_log(self, path: str, limit: int = 200) -> dict:
        safe_limit = max(1, min(limit, self.MAX_LINES))
        file_path = Path(path)

        if not file_path.exists():
            return {
                'ok': False,
                'message': f'Log file not found: {file_path}',
                'path': str(file_path),
                'lines': [],
                'line_count': 0,
            }

        lines = file_path.read_text(encoding='utf-8', errors='replace').splitlines()
        tailed = lines[-safe_limit:]

        return {
            'ok': True,
            'path': str(file_path),
            'lines': tailed,
            'line_count': len(tailed),
            'truncated': len(lines) > safe_limit,
        }

    def diagnose(self, log_text: str, prompt: str = '') -> dict:
        text = (log_text or '').strip()
        prompt_text = (prompt or '').strip()

        if text == '':
            return {
                'ok': False,
                'message': 'No log text was provided for diagnosis.',
            }

        lowered = text.lower()
        categories = Counter()
        evidence: list[str] = []

        patterns = {
            'proxy': [r'proxy', r'407', r'proxyerror', r'tunnel connection failed', r'cannot connect to proxy'],
            'timeout': [r'timeout', r'timed out', r'read timed out', r'connect timeout'],
            'auth': [r'401', r'403', r'unauthorized', r'forbidden', r'invalid api key', r'permission denied'],
            'rate_limit': [r'429', r'rate limit', r'too many requests'],
            'network': [r'connection refused', r'name or service not known', r'temporary failure in name resolution', r'connection reset'],
            'upstream_site': [r'captcha', r'access denied', r'blocked', r'challenge'],
            'data_shape': [r'validation', r'keyerror', r'typeerror', r'valueerror', r'jsondecodeerror'],
        }

        sample_lines = text.splitlines()[-200:]
        for line in sample_lines:
            low = line.lower()
            for category, regexes in patterns.items():
                if any(re.search(regex, low) for regex in regexes):
                    categories[category] += 1
                    if len(evidence) < 12:
                        evidence.append(line[:500])

        top_category = categories.most_common(1)[0][0] if categories else 'unknown'

        explanation_map = {
            'proxy': 'Most likely a proxy issue: authentication, connectivity, or tunnel setup is failing before the scrape can proceed.',
            'timeout': 'Most likely a timeout issue: requests are reaching something, but the response is too slow or the worker is hanging.',
            'auth': 'Most likely an authentication or permission issue: API keys, headers, or upstream authorization should be checked.',
            'rate_limit': 'Most likely rate limiting: requests are being throttled by an upstream service.',
            'network': 'Most likely a network connectivity or DNS issue between the worker and the upstream target.',
            'upstream_site': 'Most likely an upstream anti-bot or site-blocking issue, not an internal application bug.',
            'data_shape': 'Most likely a parsing or payload-shape issue after data is returned.',
            'unknown': 'No strong error pattern was detected from the supplied log excerpt.',
        }

        suggestions_map = {
            'proxy': [
                'Test the same job without proxies to confirm whether the proxy layer is the blocker.',
                'Verify proxy credentials, protocol, and whether the proxy supports the target site.',
                'Look for repeated 407 or tunnel errors in the same timeframe.',
            ],
            'timeout': [
                'Check worker runtime and request timeout settings.',
                'Compare whether timeouts happen only with a specific site or proxy.',
                'Inspect whether retries eventually succeed or all attempts stall.',
            ],
            'auth': [
                'Verify API keys and admin credentials in both Laravel and JobSpy.',
                'Check whether the failing endpoint expects a different auth header or key.',
            ],
            'rate_limit': [
                'Reduce burst size and retry with backoff.',
                'Check if failures cluster around one provider or site.',
            ],
            'network': [
                'Verify DNS resolution and outbound connectivity from the JobSpy host.',
                'Check whether the target host is reachable without the application stack.',
            ],
            'upstream_site': [
                'Try the same scrape term/site through a different proxy or no proxy.',
                'Inspect whether only one source site is blocked.',
            ],
            'data_shape': [
                'Capture the offending response body and compare it to expected schema.',
                'Check whether one provider/site returns a different payload format.',
            ],
            'unknown': [
                'Increase the excerpt size or include lines closer to the first failure.',
                'Search for the first ERROR/Traceback before the current excerpt.',
            ],
        }

        return {
            'ok': True,
            'prompt': prompt_text,
            'top_category': top_category,
            'category_counts': dict(categories),
            'summary': explanation_map[top_category],
            'suggestions': suggestions_map[top_category],
            'evidence': evidence,
        }
