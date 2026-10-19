"""Shared helpers for the foot-traffic fetchers (fetch_traffic.py and traffic_*.py).

Outputs land in data/raw/traffic/ as parquet; each save() writes a sidecar in
data/raw/traffic/_manifest/ and rebuilds data/raw/traffic/manifest.json.
Raw downloads that are only needed transiently go to data/raw/traffic/_tmp/ and are deleted.
"""
from __future__ import annotations

import gzip
import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "traffic"
GOV = ROOT / "data" / "raw" / "gov"
TMP = OUT / "_tmp"
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(exist_ok=True)

NYC_COUNTY_FIPS = {"005": "BX", "047": "BK", "061": "MN", "081": "QN", "085": "SI"}
YEARS = list(range(2011, 2026))  # target panel years
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nyc-food-churn research (python-requests)"


def get(url: str, *, params=None, timeout=600, tries=4, stream=False) -> requests.Response:
    """GET with retries and backoff; raises on final failure."""
    last = None
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout, stream=stream)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} for {r.url}: {r.text[:300]}")
            if r.status_code in (400, 401, 403, 404):
                break
        except requests.RequestException as e:
            last = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"GET failed: {url} params={params}") from last


def soql(domain: str, dsid: str, *, select: str, where: str | None = None,
         group: str | None = None, order: str | None = None, page: int = 50_000) -> pd.DataFrame:
    """Run a (possibly aggregating) SoQL query, paging through results. All-string columns."""
    frames, offset = [], 0
    while True:
        params = {"$select": select, "$limit": page, "$offset": offset}
        if where:
            params["$where"] = where
        if group:
            params["$group"] = group
        params["$order"] = order or (group or ":id")
        r = get(f"https://{domain}/resource/{dsid}.csv", params=params)
        df = pd.read_csv(io.BytesIO(r.content), dtype=str, keep_default_na=False, na_values=[""])
        frames.append(df)
        if len(df) < page:
            break
        offset += page
    return pd.concat(frames, ignore_index=True)


def tracts():
    """2020 census tracts (GeoDataFrame, EPSG:4326) with geoid, boroct2020, nta2020."""
    import geopandas as gpd
    g = gpd.read_file(gzip.open(GOV / "geo_census_tracts2020.geojson.gz"))
    return g[["geoid", "boroct2020", "ct2020", "borocode", "nta2020", "ntaname", "geometry"]]


METRIC_CRS = "EPSG:2263"  # NY State Plane Long Island, feet


def save(df: pd.DataFrame, name: str, *, source: str, note: str = "") -> Path:
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    side = OUT / "_manifest"
    side.mkdir(exist_ok=True)
    entry = {"file": path.name, "source": source, "rows": int(len(df)),
             "fields": list(map(str, df.columns)), "fetched": time.strftime("%Y-%m-%d"),
             "note": note}
    (side / f"{name}.json").write_text(json.dumps(entry, indent=1))
    man = {p.stem: json.loads(p.read_text()) for p in sorted(side.glob("*.json"))}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))
    print(f"saved {path.name}: {len(df):,} rows, {path.stat().st_size/1e6:.1f} MB", flush=True)
    return path
