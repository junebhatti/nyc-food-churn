"""Shared helpers for the bars (pre-2015 liquor licence) pulls.

One rate-limited HTTP client for archive.org (>= 3 s between requests, Retry-After / 503
backoff), since archive.org is shared with other agents.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "bars"
OUT.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nyc-food-churn research (python-requests)"
MIN_GAP = 3.0
_last = [0.0]


def ia_get(url: str, *, params=None, timeout=120, tries=6) -> requests.Response:
    """GET from archive.org with spacing and backoff. Raises on final failure."""
    err = None
    for i in range(tries):
        wait = MIN_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            err = e
            print(f"  ia_get retry {i + 1}: {type(e).__name__} {url[:120]}", flush=True)
            time.sleep(10 * (i + 1))
            continue
        if r.status_code in (429, 503, 502, 504):
            ra = r.headers.get("Retry-After")
            pause = int(ra) if ra and ra.isdigit() else 15 * (i + 1)
            print(f"  ia_get {r.status_code}, sleeping {pause}s: {url[:120]}", flush=True)
            time.sleep(pause)
            err = RuntimeError(f"HTTP {r.status_code}")
            continue
        return r
    raise RuntimeError(f"ia_get failed after {tries} tries: {url[:200]} ({err})")


def cdx(url: str, **kw) -> list[dict]:
    """Wayback CDX query -> list of dict rows (output=json)."""
    params = {"url": url, "output": "json", **kw}
    r = ia_get("http://web.archive.org/cdx/search/cdx", params=params, timeout=300)
    r.raise_for_status()
    if not r.text.strip():
        return []
    rows = r.json()
    if not rows:
        return []
    head = rows[0]
    return [dict(zip(head, x)) for x in rows[1:]]
