"""Shared helpers for the menu fetchers (fetch_menus.py and menus_*.py).

Outputs land in data/raw/menus/. Only archived copies (Internet Archive) and open
datasets are used; see data/notes/menus.md for what was ruled out and why.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "menus"
OUT.mkdir(parents=True, exist_ok=True)
DOHMH = ROOT / "data" / "raw" / "dohmh" / "union_inspections.parquet"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nyc-food-churn research (python-requests; menus)"


class Gone(Exception):
    """Permanent miss (404/403 etc.): don't retry."""


def get(url: str, *, timeout: int = 120, tries: int = 6, params=None) -> requests.Response:
    """Polite GET: retries with growing backoff; long pause on 429/503 (rate limit).
    Raises Gone on 4xx other than 429, RuntimeError after the last retry."""
    last: Exception | None = None
    for i in range(tries):
        try:
            r = SESSION.get(url, timeout=timeout, params=params)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503, 504, 502, 500):
                last = RuntimeError(f"HTTP {r.status_code} for {url}")
                wait = 60 * (i + 1) if r.status_code == 429 else 10 * (i + 1)
                print(f"  {r.status_code} -> sleep {wait}s ({url[:90]})", flush=True)
                time.sleep(wait)
                continue
            raise Gone(f"HTTP {r.status_code} for {url}")
        except requests.RequestException as e:
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last
