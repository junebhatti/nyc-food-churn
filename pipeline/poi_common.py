"""Shared helpers for the non-government POI pulls (Foursquare, Overture, OSM).

Every source is normalized to the same columns (NORM_COLS) and clipped to the
five boroughs before it is written to data/raw/poi/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "poi"
OUT.mkdir(parents=True, exist_ok=True)

# Rough NYC bbox used for remote predicate pushdown; borough clip happens after.
XMIN, XMAX, YMIN, YMAX = -74.26, -73.70, 40.49, 40.92

BOROUGHS_URL = "https://data.cityofnewyork.us/resource/gthc-hcne.geojson?$limit=10"
BOROUGHS_PATH = OUT / "nyc_boroughs.geojson"

NORM_COLS = [
    "source", "source_id", "name", "category_raw", "category", "lat", "lon",
    "address", "date_created", "date_closed", "first_seen", "last_seen", "extra",
]
CATEGORIES = ("restaurant", "bar", "cafe_coffee", "bakery_dessert", "other_food")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    con.sql("SET enable_progress_bar=false; SET http_retries=8; SET http_timeout=120000;")
    return con


def boroughs_path() -> Path:
    if not BOROUGHS_PATH.exists():
        r = requests.get(BOROUGHS_URL, timeout=120)
        r.raise_for_status()
        gj = r.json()
        if len(gj.get("features", [])) != 5:
            raise ValueError(f"expected 5 borough features, got {len(gj.get('features', []))}")
        BOROUGHS_PATH.write_text(json.dumps(gj))
    return BOROUGHS_PATH


def s3_list(base_url: str, prefix: str) -> list[tuple[str, int]]:
    """List (key, size) under prefix for an anonymous S3-compatible bucket (handles paging)."""
    keys: list[tuple[str, int]] = []
    token = None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        r = requests.get(base_url, params=params, timeout=120)
        r.raise_for_status()
        x = r.text
        keys += [(k, int(s)) for k, s in re.findall(r"<Key>([^<]*)</Key>.*?<Size>(\d+)</Size>", x, re.S)]
        m = re.search(r"<NextContinuationToken>([^<]*)</NextContinuationToken>", x)
        if "<IsTruncated>true</IsTruncated>" in x and m:
            token = m.group(1)
        else:
            return keys


def s3_prefixes(base_url: str, prefix: str) -> list[str]:
    r = requests.get(base_url, params={"list-type": "2", "prefix": prefix, "delimiter": "/"}, timeout=120)
    r.raise_for_status()
    return [p for p in re.findall(r"<Prefix>([^<]*)</Prefix>", r.text) if p != prefix]


def clip_and_write(con: duckdb.DuckDBPyConnection, rel_sql: str, out_name: str) -> Path:
    """rel_sql must yield NORM_COLS. Keeps rows inside a borough, adds borough into extra."""
    bpath = boroughs_path()
    out = OUT / out_name
    con.sql(f"""
        CREATE OR REPLACE TEMP TABLE _b AS
        SELECT boroname, geom FROM ST_Read('{bpath}')
    """)
    con.sql(f"""
        COPY (
          SELECT n.source, n.source_id, n.name, n.category_raw, n.category,
                 n.lat::DOUBLE AS lat, n.lon::DOUBLE AS lon, n.address,
                 n.date_created, n.date_closed, n.first_seen, n.last_seen,
                 json_merge_patch(coalesce(n.extra, '{{}}')::JSON,
                                  json_object('borough', b.boroname))::VARCHAR AS extra
          FROM ({rel_sql}) n
          JOIN _b b ON ST_Intersects(b.geom, ST_Point(n.lon, n.lat))
          WHERE n.category IN {CATEGORIES}
        ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n = con.sql(f"SELECT count(*) FROM '{out}'").fetchone()[0]
    print(f"  wrote {out.name}: {n:,} rows")
    return out
