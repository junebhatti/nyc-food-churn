"""Shared helpers for the government-data fetchers (fetch_gov.py and gov_*.py).

Everything lands in data/raw/gov/ as parquet; each write appends/updates an entry
in data/raw/gov/manifest.json (dataset id, rows, date range, fields).
"""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "gov"
MANIFEST = OUT / "manifest.json"
OUT.mkdir(parents=True, exist_ok=True)

NYC_COUNTIES = {"NEW YORK", "KINGS", "QUEENS", "BRONX", "RICHMOND"}
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nyc-food-churn research (python-requests)"


def get(url: str, *, params=None, timeout=300, tries=4, stream=False) -> requests.Response:
    """GET with retries; raises on final failure (never returns a bad response)."""
    last = None
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout, stream=stream)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} for {r.url}: {r.text[:300]}")
            if r.status_code in (400, 401, 403, 404):
                break
        except requests.RequestException as e:  # network hiccup -> retry
            last = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"GET failed: {url} params={params}") from last


def socrata(domain: str, dsid: str, where: str | None = None, select: str | None = None,
            page: int = 200_000) -> pd.DataFrame:
    """Pull a whole Socrata dataset (optionally filtered) as all-string DataFrame."""
    frames, offset = [], 0
    while True:
        params = {"$limit": page, "$offset": offset, "$order": ":id"}
        if where:
            params["$where"] = where
        if select:
            params["$select"] = select
        r = get(f"https://{domain}/resource/{dsid}.csv", params=params)
        df = pd.read_csv(io.BytesIO(r.content), dtype=str, keep_default_na=False, na_values=[""])
        frames.append(df)
        print(f"  {dsid}: +{len(df):,} rows (offset {offset:,})", flush=True)
        if len(df) < page:
            break
        offset += page
    out = pd.concat(frames, ignore_index=True)
    # drop Socrata computed-region helper columns
    return out[[c for c in out.columns if not c.startswith(":@computed")]]


def date_range(df: pd.DataFrame, cols: list[str]) -> dict:
    rng = {}
    for c in cols:
        if c in df:
            d = pd.to_datetime(df[c], errors="coerce", format="mixed")
            if d.notna().any():
                rng[c] = [str(d.min().date()), str(d.max().date()), int(d.notna().sum())]
    return rng


def rebuild_manifest() -> None:
    side = OUT / "_manifest"
    man = {p.stem: json.loads(p.read_text()) for p in sorted(side.glob("*.json"))}
    MANIFEST.write_text(json.dumps(man, indent=1))


def register_file(name: str, path: Path, *, source: str, dataset_id: str, rows: int,
                  fields=(), date_range=None, note: str = "") -> None:
    """Manifest entry for a non-parquet output (GeoJSON, CSV)."""
    side = OUT / "_manifest"
    side.mkdir(exist_ok=True)
    entry = {"file": path.name, "dataset_id": dataset_id, "source": source, "rows": int(rows),
             "date_range": date_range or {}, "fields": list(fields),
             "fetched": time.strftime("%Y-%m-%d"), "note": note}
    (side / f"{name}.json").write_text(json.dumps(entry, indent=1))
    rebuild_manifest()


def save(df: pd.DataFrame, name: str, *, source: str, dataset_id: str, date_cols=(),
         note: str = "") -> Path:
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    entry = {
        "file": path.name, "dataset_id": dataset_id, "source": source, "rows": int(len(df)),
        "date_range": date_range(df, list(date_cols)), "fields": list(map(str, df.columns)),
        "fetched": time.strftime("%Y-%m-%d"), "note": note,
    }
    # one sidecar per dataset (safe when fetchers run in parallel), merged into manifest.json
    side = OUT / "_manifest"
    side.mkdir(exist_ok=True)
    (side / f"{name}.json").write_text(json.dumps(entry, indent=1))
    rebuild_manifest()
    print(f"saved {path.name}: {len(df):,} rows, {path.stat().st_size/1e6:.1f} MB", flush=True)
    return path
