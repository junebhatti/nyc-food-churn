"""Shared helpers for the analysis-inputs area (data/raw/analysis_inputs/).

Inputs elsewhere in data/raw are READ-ONLY here. Everything we write goes to OUT.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "analysis_inputs"
SRC = OUT / "_src"
OUT.mkdir(parents=True, exist_ok=True)
SRC.mkdir(parents=True, exist_ok=True)

UNION = RAW / "dohmh" / "union_inspections.parquet"
LIVE_SNAPSHOT = "2026-10-16"  # pull date of socrata_live_20261018 (RECORD DATE)

log = logging.getLogger("ai")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

UA = {"User-Agent": "nyc-food-churn research (academic; contact via github)"}


def con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


# ---------- HTTP ----------
class Polite:
    """One HTTP client per host family. archive.org gets >=2 s spacing and 503 backoff."""

    def __init__(self, min_gap: float = 1.0):
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.min_gap = min_gap
        self._last = 0.0

    def get(self, url: str, tries: int = 6, **kw) -> requests.Response:
        delay = 10.0
        for i in range(tries):
            wait = self.min_gap - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.s.get(url, timeout=kw.pop("timeout", 60), **kw)
            except requests.RequestException as e:
                log.warning("GET %s failed (%s), retry %d", url, e, i + 1)
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code in (429, 502, 503, 504):
                log.warning("GET %s -> %d, backoff %.0fs", url, r.status_code, delay)
                time.sleep(delay)
                delay *= 2
                continue
            return r
        raise RuntimeError(f"GET {url} failed after {tries} tries")


WAYBACK = Polite(min_gap=2.5)  # the ONE archive.org client for this area
WEB = Polite(min_gap=1.0)


# ---------- normalisation ----------
BORO_MAP = {
    "1": "Manhattan", "MANHATTAN": "Manhattan",
    "2": "Bronx", "BRONX": "Bronx",
    "3": "Brooklyn", "BROOKLYN": "Brooklyn",
    "4": "Queens", "QUEENS": "Queens",
    "5": "Staten Island", "STATEN ISLAND": "Staten Island",
}


def norm_boro(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return BORO_MAP.get(str(v).strip().upper())


_SUFFIX = re.compile(
    r"\b(INC|LLC|L L C|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PLLC|THE|OF|NY|NYC|RESTAURANT|REST|"
    r"RESTAURANTS)\b"
)


def norm_name(s) -> str | None:
    """Business-name key: upper, ASCII-ish, punctuation and corporate suffixes stripped."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).upper().replace("&AMP;", "&").replace("&", " AND ").replace("'", "")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def norm_addr(building, street) -> str | None:
    if building is None or street is None:
        return None
    b = re.sub(r"\s+", "", str(building).upper())
    st = re.sub(r"[^A-Z0-9 ]+", " ", str(street).upper())
    st = re.sub(r"\b(STREET)\b", "ST", st)
    st = re.sub(r"\b(AVENUE)\b", "AVE", st)
    st = re.sub(r"\b(ROAD)\b", "RD", st)
    st = re.sub(r"\b(BOULEVARD)\b", "BLVD", st)
    st = re.sub(r"\b(PLACE)\b", "PL", st)
    st = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", st)
    st = re.sub(r"\s+", " ", st).strip()
    if not b or not st or b in ("0", "NAN", "NONE"):
        return None
    return f"{b} {st}"


# ---------- manifest ----------
MANIFEST = OUT / "manifest.json"


def write_out(df: pd.DataFrame, name: str, source: str, notes: str = "", fmt: str = "parquet") -> Path:
    path = OUT / f"{name}.{fmt}"
    if fmt == "parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)
    m = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    m[name] = {
        "file": path.name,
        "rows": int(len(df)),
        "columns": list(map(str, df.columns)),
        "source": source,
        "notes": notes,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": path.stat().st_size,
    }
    MANIFEST.write_text(json.dumps(m, indent=1, sort_keys=True))
    log.info("wrote %s (%d rows)", path.name, len(df))
    return path
