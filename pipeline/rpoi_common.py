"""Shared helpers for the research-POI pipeline (pipeline/fetch_research_poi.py).

- polite streaming HTTP (descriptive User-Agent, retries)
- HttpRangeFile: a seekable file over HTTP Range requests, so zipfile can pull a
  single member out of a remote multi-GB zip without storing the zip
- NYC + food/drink filters
- per-venue summary writer: first/last activity date, counts by year
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = RAW / "research_poi"
DL = OUT / "_dl"
UA = "nyc-food-churn research script (personal, non-commercial; polite rate)"

# Bounding box of the five boroughs (clipped later by ZIP or borough polygon).
BBOX = (40.49, 40.92, -74.27, -73.68)

# Food & drink category names (English Google / Foursquare labels).
FOOD = (r"(?i)restaurant|\bcaf[eé]|coffee|\bbar\b|\bbars\b|\bpub\b|bakery|pizz|\bdeli\b|diner|"
        r"bistro|brewery|brewpub|tavern|lounge|tea ?(house|room)|bubble tea|dessert|ice cream|"
        r"frozen yogurt|juice|bagel|donut|doughnut|taco|taqueria|sushi|ramen|noodle|steak|"
        r"food court|gastropub|wine bar|cocktail|beer|izakaya|dumpling|sandwich|burger|wings|"
        r"barbecue|bbq|bar-?b-?q|takeaway|take ?out|delivery|caterer|food truck|creperie|"
        r"patisserie|cupcake|chocolate|gelato|bar & grill|night ?club|hookah|karaoke|speakeasy|"
        r"snack|bodega|salad|soup|falafel|gyro|cuisine|food\b|breakfast|brunch|tapas|"
        r"fried chicken|hot dog|empanada|arepa|dim sum|bbq joint|joint\b|grill")
# Non-food words that the broad FOOD pattern would otherwise catch.
NOT_FOOD = r"(?i)grocery|supermarket|liquor store|convenience store|gas station|food bank|pet food"

_session = requests.Session()
_session.headers["User-Agent"] = UA


def get(url: str, delay: float = 1.0, **kw) -> requests.Response:
    """GET with retries on 429/5xx and connection errors; raises on final failure."""
    time.sleep(delay)
    last = None
    for attempt in range(4):
        try:
            r = _session.get(url, timeout=120, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                last = f"HTTP {r.status_code}"
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last = repr(e)
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"GET failed after retries: {url} ({last})")


def download(url: str, dest: Path) -> Path:
    """Stream url to dest (skips if already present). Partial files are removed."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print("downloading", url)
    with get(url, stream=True) as r, open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def gdrive_url(file_id: str) -> str:
    return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"


class HttpRangeFile(io.RawIOBase):
    """Read-only seekable view of a remote file. Sequential reads reuse one
    streaming response; a seek elsewhere opens a new Range request."""

    def __init__(self, url: str):
        self.url = url
        h = _session.head(url, allow_redirects=True, timeout=60)
        h.raise_for_status()
        if h.headers.get("Accept-Ranges") != "bytes":
            raise RuntimeError(f"server does not support Range requests: {url}")
        self.size = int(h.headers["Content-Length"])
        self.pos = 0
        self._resp = None
        self._it = None
        self._rpos = -1
        self._buf = b""

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def _open(self):
        if self._resp is not None:
            self._resp.close()
        for attempt in range(4):
            try:
                self._resp = _session.get(self.url, headers={"Range": f"bytes={self.pos}-"},
                                          stream=True, timeout=120)
                if self._resp.status_code != 206:
                    raise RuntimeError(f"expected 206, got {self._resp.status_code}")
                break
            except (requests.ConnectionError, requests.Timeout, RuntimeError) as e:
                if attempt == 3:
                    raise RuntimeError(f"range GET failed at {self.pos}: {self.url}") from e
                time.sleep(15 * (attempt + 1))
        self._it = self._resp.iter_content(1 << 20)
        self._rpos = self.pos
        self._buf = b""

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        if self._rpos != self.pos:
            self._open()
        while not self._buf:
            try:
                self._buf = next(self._it)
            except StopIteration:
                return 0
            except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                print(f"  stream broke at byte {self.pos:,} ({e!r}); reopening")
                self._open()
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        self.pos += n
        self._rpos = self.pos
        return n

    def close(self):
        if self._resp is not None:
            self._resp.close()
        super().close()


def connect() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute(r"""
    create macro norm(s) as trim(regexp_replace(regexp_replace(
      regexp_replace(upper(strip_accents(coalesce(s, ''))), '&', ' AND ', 'g'),
      '[^A-Z0-9 ]', '', 'g'),
      '\b(THE|INC|LLC|CORP|RESTAURANT|RESTAURANTS|CAFE|BAR|AND|NYC|NY)\b', '', 'g'))
    """)
    c.execute("""
    create macro dist_m(lat1, lon1, lat2, lon2) as
      111320 * sqrt(power(lat1 - lat2, 2) + power((lon1 - lon2) * cos(radians(lat1)), 2))
    """)
    return c


def in_bbox(lat, lon) -> bool:
    return lat is not None and lon is not None and BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]


def clip_boroughs(c: duckdb.DuckDBPyConnection, table: str) -> None:
    """Delete rows of `table` (lat, lon) outside the five boroughs."""
    c.execute("install spatial; load spatial")
    c.execute(f"""
    create or replace temp table _boro as
    select geom from st_read('{RAW / 'poi' / 'nyc_boroughs.geojson'}')""")
    before = c.execute(f"select count(*) from {table}").fetchone()[0]
    c.execute(f"""delete from {table} t where lat is null or not exists (
        select 1 from _boro b where st_contains(b.geom, st_point(t.lon, t.lat)))""")
    after = c.execute(f"select count(*) from {table}").fetchone()[0]
    print(f"  borough clip {table}: {before:,} -> {after:,}")


def write_venues(c: duckdb.DuckDBPyConnection, source: str, venues: str, acts: str) -> None:
    """venues: venue_id, name, lat, lon, category (+ any extra columns).
    acts: venue_id, d (date), n (count of activity events that day).
    Writes <source>_venues.parquet and <source>_yearly.parquet."""
    c.execute(f"""
    create or replace temp table _sum as
    select venue_id, min(d) first_date, max(d) last_date, sum(n)::bigint n_activity,
           count(distinct d) n_days
    from {acts} group by 1""")
    c.execute(f"""
    create or replace temp table _out as
    select '{source}' as source, v.*, s.first_date, s.last_date, s.n_activity, s.n_days
    from {venues} v join _sum s using (venue_id)""")
    n = c.execute("select count(*) from _out").fetchone()[0]
    if n == 0:
        raise RuntimeError(f"{source}: no venues with activity; refusing to write empty output")
    OUT.mkdir(parents=True, exist_ok=True)
    c.execute(f"copy _out to '{OUT / (source + '_venues.parquet')}' (format parquet)")
    c.execute(f"""
    copy (select '{source}' as source, venue_id, year(d) "year", sum(n)::bigint n
          from {acts} where venue_id in (select venue_id from _out) group by all order by 2, 3)
    to '{OUT / (source + '_yearly.parquet')}' (format parquet)""")
    yrs = c.execute("select min(first_date), max(last_date), sum(n_activity) from _out").fetchone()
    print(f"  wrote {source}: {n:,} venues, activity {yrs[0]} -> {yrs[1]}, {yrs[2]:,} events")


def df_to(c: duckdb.DuckDBPyConnection, df: pd.DataFrame, name: str) -> None:
    c.register("_tmpdf", df)
    c.execute(f"create or replace temp table {name} as select * from _tmpdf")
    c.unregister("_tmpdf")
