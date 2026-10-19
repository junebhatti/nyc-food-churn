"""Shared helpers for the menu fetchers (fetch_menus.py and menus_*.py).

Outputs land in data/raw/menus/. Only archived copies (Internet Archive) and open
datasets are used; see data/notes/menus.md for what was ruled out and why.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "menus"
OUT.mkdir(parents=True, exist_ok=True)
DOHMH = ROOT / "data" / "raw" / "dohmh" / "union_inspections.parquet"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nyc-food-churn research (python-requests; menus)"


# Shared across worker threads: one 429/5xx pauses ALL workers (not just the one that hit it),
# and per-status counts + latency feed the progress line (see stats_line()).
_gate = threading.Lock()
_pause_until = 0.0
STATS: Counter = Counter()
_lat: list[float] = []


def stats_line(reset: bool = True) -> str:
    """Counts since last call: 200 / Gone(4xx) / 429 / 5xx / net errors, mean+p90 latency of 200s."""
    with _gate:
        c, lat = dict(STATS), sorted(_lat)
        if reset:
            STATS.clear()
            _lat.clear()
    n = sum(c.values()) or 1
    bad = c.get("429", 0) + c.get("5xx", 0)
    p90 = lat[int(len(lat) * 0.9)] if lat else 0
    mean = sum(lat) / len(lat) if lat else 0
    return (f"[req {sum(c.values())}: {c} | 429+5xx {bad / n:.1%} | "
            f"lat mean {mean:.2f}s p90 {p90:.2f}s]")


def read_done(*paths: Path, key: str = "slug") -> set[str]:
    """Keys already recorded in JSONL files. Records whose err is not a permanent HTTP 4xx
    (i.e. retries exhausted on 429/5xx/network) are NOT counted, so a rerun retries them.
    A truncated last line (process killed mid-write) is cut off, with a message."""
    done: set[str] = set()
    for f in paths:
        if not f.exists():
            continue
        raw = f.read_bytes()
        if raw and not raw.endswith(b"\n"):
            cut = raw.rfind(b"\n") + 1
            print(f"  {f.name}: dropping truncated last line ({len(raw) - cut} bytes)", flush=True)
            with open(f, "r+b") as fh:
                fh.truncate(cut)
            raw = raw[:cut]
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if "err" in rec and not rec["err"].startswith("HTTP 4"):
                continue
            done.add(rec[key])
    return done


class Gone(Exception):
    """Permanent miss (404/403 etc.): don't retry."""


def get(url: str, *, timeout: int = 120, tries: int = 6, params=None) -> requests.Response:
    """Polite GET: retries with growing backoff; long pause on 429/503 (rate limit).
    Raises Gone on 4xx other than 429, RuntimeError after the last retry."""
    global _pause_until
    last: Exception | None = None
    for i in range(tries):
        while (w := _pause_until - time.time()) > 0:  # another worker hit a rate limit
            time.sleep(w)
        try:
            t0 = time.time()
            r = SESSION.get(url, timeout=timeout, params=params)
            if r.status_code == 200:
                with _gate:
                    STATS["200"] += 1
                    _lat.append(time.time() - t0)
                return r
            if r.status_code in (429, 503, 504, 502, 500):
                last = RuntimeError(f"HTTP {r.status_code} for {url}")
                # honour Retry-After (seconds) when given; else exponential 30s, 60s, 120s ...
                ra = r.headers.get("Retry-After", "")
                wait = int(ra) if ra.isdigit() else min(30 * 2 ** i, 600)
                with _gate:
                    STATS["429" if r.status_code == 429 else "5xx"] += 1
                    _pause_until = max(_pause_until, time.time() + wait)
                print(f"  {r.status_code} -> sleep {wait}s (Retry-After={ra or '-'}) ({url[:90]})",
                      flush=True)
                time.sleep(wait)
                continue
            with _gate:
                STATS["gone"] += 1
            raise Gone(f"HTTP {r.status_code} for {url}")
        except requests.RequestException as e:
            last = e
            with _gate:
                STATS["neterr"] += 1
            print(f"  {type(e).__name__} -> sleep {5 * (i + 1)}s ({url[:90]})", flush=True)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last
