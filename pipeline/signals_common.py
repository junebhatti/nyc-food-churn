"""Shared helpers for the proof-of-life signal fetchers (fetch_signals.py, signals_*.py).

Every source lands in data/raw/signals/<name>.parquet with the common event columns

    source, source_id, event_date, event_type, name, legal_name, address, house, street,
    boro (1-5), zip, bbl, bin, lat, lon, detail

plus a few source-specific extras. bbl/bin/lat/lon come from the source when present and
from the local PAD matcher (gov_geocode.PadGeocoder) otherwise; `geo_src` says which.
data/raw/signals/manifest.json lists rows, date range and fields per file.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from gov_common import socrata  # noqa: F401  (re-exported for the fetchers)
from gov_geocode import PadGeocoder, split_address

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "signals"
OUT.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT / "manifest.json"
NYC = "data.cityofnewyork.us"
NYS = "data.ny.gov"

EVENT_COLS = ["source", "source_id", "event_date", "event_type", "name", "legal_name", "address",
              "house", "street", "boro", "zip", "bbl", "bin", "lat", "lon", "geo_src", "detail"]
BORO_NUM = {"MANHATTAN": 1, "NEW YORK": 1, "BRONX": 2, "BROOKLYN": 3, "KINGS": 3, "QUEENS": 4,
            "STATEN ISLAND": 5, "RICHMOND": 5, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
            "MN": 1, "BX": 2, "BK": 3, "QN": 4, "SI": 5}
NYC_COUNTIES = ("NEW YORK", "KINGS", "QUEENS", "BRONX", "RICHMOND")

_geo: PadGeocoder | None = None


def geocoder() -> PadGeocoder:
    global _geo
    if _geo is None:
        _geo = PadGeocoder()
    return _geo


def norm_bbl(s: pd.Series) -> pd.Series:
    """'1012345678', '1012345678.0', 1.012e9 -> '1012345678'; anything else -> NA."""
    t = s.astype("string").str.replace(r"\.0+$", "", regex=True).str.strip()
    return t.where(t.str.fullmatch(r"[1-5]\d{9}") & ~t.str.fullmatch(r"[1-5]0{9}"))


def norm_bin(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.replace(r"\.0+$", "", regex=True).str.strip()
    # x000000 BINs are borough placeholders, not buildings
    return t.where(t.str.fullmatch(r"[1-5]\d{6}") & ~t.str.fullmatch(r"[1-5]000000"))


def norm_name(s: pd.Series) -> pd.Series:
    """Upper, strip punctuation and corporate suffixes: 'Joe's Pizza, Inc.' -> 'JOES PIZZA'."""
    t = s.astype("string").str.upper().str.replace("&", " AND ", regex=False)
    t = t.str.replace(r"[^A-Z0-9 ]", "", regex=True)
    t = t.str.replace(r"\b(INC|INCORPORATED|LLC|L L C|CORP|CORPORATION|CO|LTD|LP|LLP|PLLC|THE|DBA)\b",
                      " ", regex=True)
    return t.str.replace(r"\s+", " ", regex=True).str.strip().replace("", pd.NA)


def finish(df: pd.DataFrame, *, source: str) -> pd.DataFrame:
    """Fill the common columns, geocode rows without a usable BBL, order columns."""
    df = df.copy()
    df["source"] = source
    for c in EVENT_COLS:
        if c not in df:
            df[c] = pd.NA
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce", format="mixed")
    bad = df["event_date"].isna().sum()
    if bad:
        print(f"  {source}: dropping {bad:,} rows with no parseable date", flush=True)
        df = df[df["event_date"].notna()].copy()
    df["boro"] = df["boro"].astype("string").str.upper().str.strip().map(BORO_NUM).astype("Int64")
    df["zip"] = df["zip"].astype("string").str.extract(r"(\d{5})", expand=False)
    df["bbl"], df["bin"] = norm_bbl(df["bbl"]), norm_bin(df["bin"])
    for c in ("lat", "lon"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.loc[(df["lat"] < 40.4) | (df["lat"] > 41.0), ["lat", "lon"]] = np.nan
    # house/street from a one-line address where the source has no split
    need = df["house"].isna() & df["address"].notna()
    if need.any():
        hs = df.loc[need, "address"].map(split_address)
        df.loc[need, "house"] = hs.str[0].replace("", pd.NA)
        df.loc[need, "street"] = hs.str[1].replace("", pd.NA)
    df["geo_src"] = np.where(df["bbl"].notna(), "source", pd.NA)
    todo = df["bbl"].isna() & df["house"].notna() & df["street"].notna()
    if todo.any():
        g = geocoder()
        uniq = df.loc[todo, ["house", "street", "zip", "boro"]].drop_duplicates()
        res = [g.one(h, s, z if isinstance(z, str) else None, str(int(b)) if pd.notna(b) else None)
               for h, s, z, b in uniq.itertuples(index=False)]
        r = pd.concat([uniq.reset_index(drop=True), pd.DataFrame(res)], axis=1)
        r = r[r["status"] == "ok"][["house", "street", "zip", "boro", "bbl", "bin", "lat", "lon"]]
        m = df.loc[todo, ["house", "street", "zip", "boro"]].merge(r, how="left",
                                                                     on=["house", "street", "zip", "boro"])
        m.index = df.index[todo]
        hit = m["bbl"].notna()
        idx = m.index[hit]
        df.loc[idx, "bbl"] = norm_bbl(m.loc[hit, "bbl"])
        df.loc[idx, "bin"] = df.loc[idx, "bin"].fillna(norm_bin(m.loc[hit, "bin"]))
        df.loc[idx, "lat"] = df.loc[idx, "lat"].fillna(m.loc[hit, "lat"].astype(float))
        df.loc[idx, "lon"] = df.loc[idx, "lon"].fillna(m.loc[hit, "lon"].astype(float))
        df.loc[idx, "geo_src"] = "pad"
        print(f"  {source}: PAD geocoded {hit.sum():,} of {todo.sum():,} rows without BBL", flush=True)
    extra = [c for c in df.columns if c not in EVENT_COLS]
    for c in ["source_id", "event_type", "name", "legal_name", "address", "house", "street",
              "detail", "geo_src"] + [c for c in extra if df[c].dtype == object]:
        df[c] = df[c].astype("string")
    return df[EVENT_COLS + extra].reset_index(drop=True)


def save(df: pd.DataFrame, name: str, *, dataset_id: str, domain: str, note: str = "") -> Path:
    path = OUT / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    d = df["event_date"]
    entry = {"file": path.name, "dataset_id": dataset_id, "source": domain, "rows": int(len(df)),
             "date_range": [str(d.min().date()), str(d.max().date())] if len(df) else [],
             "event_types": df["event_type"].value_counts().to_dict(),
             "bbl_filled": round(float(df["bbl"].notna().mean()), 3) if len(df) else 0,
             "fields": list(map(str, df.columns)), "fetched": time.strftime("%Y-%m-%d"), "note": note}
    side = OUT / "_manifest"
    side.mkdir(exist_ok=True)
    (side / f"{name}.json").write_text(json.dumps(entry, indent=1, default=str))
    man = {p.stem: json.loads(p.read_text()) for p in sorted(side.glob("*.json"))}
    MANIFEST.write_text(json.dumps(man, indent=1, default=str))
    print(f"saved {path.name}: {len(df):,} rows, {path.stat().st_size/1e6:.1f} MB, "
          f"bbl {entry['bbl_filled']:.1%}", flush=True)
    return path


def soql_in(values) -> str:
    return ",".join("'" + str(v).replace("'", "''") + "'" for v in values)


def word_re(words) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(words) + r")\b", re.I)
