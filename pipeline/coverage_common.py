"""Shared helpers for the coverage pulls (data/raw/coverage/).

Every output parquet has the common columns in COLS (plus source-specific ones):
    source, source_id, name, legal_name, address, house, street, zip, boro (1-5),
    category, category_raw, start_date, end_date, first_seen, last_seen,
    bbl, bin, lat, lon, nta2020, geo_src, extra (json string)
start/end_date are dates the source states (license issue, SNAP authorization...);
first/last_seen are snapshot presence bounds (Wayback copies).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "coverage"
CACHE = OUT / "_cache"
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parent))

COLS = ["source", "source_id", "name", "legal_name", "address", "house", "street", "zip", "boro",
        "category", "category_raw", "start_date", "end_date", "first_seen", "last_seen",
        "bbl", "bin", "lat", "lon", "nta2020", "geo_src", "extra"]

NYC_COUNTIES = {"NEW YORK": 1, "BRONX": 2, "KINGS": 3, "QUEENS": 4, "RICHMOND": 5}
BORO_NAMES = {"MANHATTAN": 1, "NEW YORK": 1, "BRONX": 2, "BROOKLYN": 3, "KINGS": 3,
              "QUEENS": 4, "STATEN ISLAND": 5, "RICHMOND": 5}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nyc-food-churn research (python-requests; open data)"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(url, *, params=None, timeout=300, tries=5, sleep=4):
    """Plain GET with backoff (non-archive.org hosts). Raises on final failure."""
    last = None
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                wait = int(r.headers.get("Retry-After", 0) or 0) or sleep * (2 ** i)
                log(f"  {r.status_code} {url[:90]} -> sleep {wait}s")
                time.sleep(min(wait, 300))
                last = RuntimeError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            log(f"  error {e!r} on {url[:90]}, retry {i + 1}/{tries}")
            time.sleep(sleep * (2 ** i))
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


class Wayback:
    """The ONE archive.org client for coverage: >= 2 s between requests, honours Retry-After."""
    MIN_GAP = 2.5
    _last = 0.0

    @classmethod
    def get(cls, url, *, params=None, timeout=180, tries=6):
        last = None
        for i in range(tries):
            gap = time.time() - cls._last
            if gap < cls.MIN_GAP:
                time.sleep(cls.MIN_GAP - gap)
            cls._last = time.time()
            try:
                hdr = {"Accept-Encoding": "identity"} if i else None  # some captures have bad gzip framing
                r = SESSION.get(url, params=params, timeout=timeout, headers=hdr)
            except requests.RequestException as e:
                last = e
                log(f"  wayback error {e!r}; sleep {10 * (i + 1)}s")
                time.sleep(10 * (i + 1))
                continue
            if r.status_code in (429, 502, 503, 504):
                wait = int(r.headers.get("Retry-After", 0) or 0) or 15 * (i + 1)
                log(f"  wayback {r.status_code}; sleep {wait}s")
                time.sleep(min(wait, 300))
                last = RuntimeError(f"HTTP {r.status_code}")
                continue
            return r
        raise RuntimeError(f"wayback GET failed: {url}") from last

    @classmethod
    def cdx(cls, url, **kw):
        p = {"url": url, "output": "json", "fl": "timestamp,original,statuscode,length,mimetype"}
        p.update(kw)
        r = cls.get("https://web.archive.org/cdx/search/cdx", params=p)
        r.raise_for_status()
        rows = r.json() if r.text.strip() else []
        return pd.DataFrame(rows[1:], columns=rows[0]) if rows else pd.DataFrame()

    @classmethod
    def raw(cls, ts, original):
        """Fetch the archived bytes (id_ playback); tries https then http spelling."""
        for orig in (original, re.sub(r"^https://", "http://", original)):
            r = cls.get(f"https://web.archive.org/web/{ts}id_/{orig}")
            if r.status_code == 200:
                return r.content
        raise RuntimeError(f"wayback playback {r.status_code}: {ts} {original}")


def socrata_all(domain, dsid, where=None, select=None, page=50000):
    out, off = [], 0
    while True:
        p = {"$limit": page, "$offset": off, "$order": ":id"}
        if where:
            p["$where"] = where
        if select:
            p["$select"] = select
        rows = get(f"https://{domain}/resource/{dsid}.json", params=p).json()
        if isinstance(rows, dict):
            raise RuntimeError(f"socrata error {dsid}: {rows}")
        out += rows
        if len(rows) < page:
            break
        off += page
    return pd.DataFrame(out)


_GEO = None


def geocoder():
    global _GEO
    if _GEO is None:
        from gov_geocode import PadGeocoder
        _GEO = PadGeocoder()
    return _GEO


def geocode(df: pd.DataFrame) -> pd.DataFrame:
    """Fill bbl/bin/lat/lon/nta2020 from house/street/zip/boro with PadGeocoder.
    Rows that already have lat/lon keep them (geo_src='source') but still get a BBL try."""
    g = geocoder()
    d = df.copy()
    boro = d["boro"].map(lambda b: {1: "MANHATTAN", 2: "BRONX", 3: "BROOKLYN", 4: "QUEENS",
                                    5: "STATEN ISLAND"}.get(b) if pd.notna(b) else None)
    tmp = pd.DataFrame({"h": d["house"].fillna("").astype(str), "s": d["street"].fillna("").astype(str),
                        "z": d["zip"].fillna("").astype(str), "b": boro})
    uniq = tmp.drop_duplicates().reset_index(drop=True)
    res = g.geocode_df(uniq, house="h", street="s", zip="z", boro="b")
    uniq = pd.concat([uniq, res], axis=1)
    m = tmp.merge(uniq, on=["h", "s", "z", "b"], how="left")
    m.index = d.index
    ok = m["status"].eq("ok")
    for c in ("bbl", "bin", "nta2020"):
        d[c] = m[c].where(ok)
    had = d["lat"].notna() & d["lon"].notna() if "lat" in d else pd.Series(False, index=d.index)
    d["geo_src"] = None
    d.loc[had, "geo_src"] = "source"
    fill = ~had & ok
    d.loc[fill, "lat"] = m.loc[fill, "lat"]
    d.loc[fill, "lon"] = m.loc[fill, "lon"]
    d.loc[fill, "geo_src"] = "pad"
    d.loc[had & ok, "geo_src"] = "source+pad_bbl"
    d["geo_status"] = m["status"]
    return d


def finish(df: pd.DataFrame) -> pd.DataFrame:
    for c in COLS:
        if c not in df:
            df[c] = None
    for c in ("start_date", "end_date", "first_seen", "last_seen"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["boro"] = pd.to_numeric(df["boro"], errors="coerce").astype("Int64")
    rest = [c for c in df.columns if c not in COLS]
    return df[COLS + rest]


MANIFEST = OUT / "manifest.json"


def save(df: pd.DataFrame, name: str, *, source: str, url: str, note: str):
    df = finish(df)
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, index=False)
    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    dr = {}
    for c in ("start_date", "end_date", "first_seen", "last_seen"):
        s = pd.to_datetime(df[c], errors="coerce").dropna()
        if len(s):
            dr[c] = [str(s.min().date()), str(s.max().date()), int(len(s))]
    man[name] = {"file": path.name, "rows": int(len(df)), "source": source, "url": url,
                 "date_range": dr, "bbl_fill": round(float(df["bbl"].notna().mean()), 3) if len(df) else 0,
                 "categories": df["category"].value_counts().head(12).to_dict(),
                 "note": note, "built": time.strftime("%Y-%m-%d %H:%M")}
    MANIFEST.write_text(json.dumps(man, indent=1, default=str))
    log(f"saved {name}: {len(df):,} rows, bbl {man[name]['bbl_fill']:.1%}")
    return df
