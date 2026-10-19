"""Citi Bike station-year activity (starts, ends, evening share), sampled months annualized.

Source: https://s3.amazonaws.com/tripdata/ (public trip files; JC-* Jersey City files skipped).
Sampling: two months per year (May and October); where a month is unavailable (2013 began
June 1; the latest year may not have October yet) the nearest available month is substituted.
Zip archives are read remotely with HTTP Range requests (zipfile over a seekable HTTP file),
so only the sampled months' members are transferred. Each CSV is extracted to TMP,
aggregated with duckdb, and deleted before the next one.
Run: .venv/bin/python pipeline/traffic_citibike.py
"""
from __future__ import annotations

import gzip
import io
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from traffic_common import GOV, METRIC_CRS, SESSION, TMP, save  # noqa: E402

BASE = "https://s3.amazonaws.com/tripdata/"
PREFERRED_MONTHS = (5, 10)
FIRST_YEAR = 2013
EVENING_HOURS = (17, 22)  # inclusive: 17:00-22:59
NYC_BUFFER_FT = 500  # borough polygons are shoreline-clipped; keep waterfront/pier stations
BBOX = dict(lat=(40.49, 40.92), lon=(-74.26, -73.69))
WORK = TMP / "citibike"


class HttpFile(io.RawIOBase):
    """Read-only seekable file over HTTP Range requests (enough for zipfile)."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        r = SESSION.head(url, timeout=60)
        r.raise_for_status()
        self.size = int(r.headers["Content-Length"])

    def readable(self): return True  # noqa: E704
    def seekable(self): return True  # noqa: E704
    def tell(self): return self.pos  # noqa: E704

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        last = None
        for i in range(4):
            try:
                r = SESSION.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=300)
                if r.status_code == 206 and len(r.content) == end - self.pos + 1:
                    n = len(r.content)
                    b[:n] = r.content
                    self.pos += n
                    return n
                last = RuntimeError(f"HTTP {r.status_code}, {len(r.content)} bytes")
            except Exception as e:  # network error: retry, re-raise below
                last = e
            print(f"  range retry {i + 1} {self.url} @{self.pos}: {last}", flush=True)
            time.sleep(5 * (i + 1))
        raise RuntimeError(f"range read failed: {self.url} bytes={self.pos}-{end}") from last


def open_remote_zip(name: str) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BufferedReader(HttpFile(BASE + name), buffer_size=8 << 20))


def list_bucket() -> list[str]:
    r = SESSION.get(BASE, timeout=120)
    r.raise_for_status()
    if "<IsTruncated>true" in r.text:
        raise RuntimeError("bucket listing truncated; pagination not implemented")
    return [k for k in re.findall(r"<Key>([^<]+)</Key>", r.text)
            if k.endswith(".zip") and not k.startswith("JC")]


def pick_members(names: list[str], y: int, m: int) -> list[str]:
    """CSV/zip members for month y-m. Old yearly zips hold each month twice (a top-level CSV
    and split CSVs in a 'N_Month/' folder): prefer the folder copy; never mix the two."""
    pat = re.compile(rf"(^|/){y}{m:02d}[-_]citibike[-_]tripdata(\.csv)?(_\d+)?\.(csv|zip)$", re.I)
    c = [n for n in names if "__MACOSX" not in n and pat.search(n)]
    folder = [n for n in c if re.search(r"/\d{1,2}_[A-Za-z]+/", n)]
    if folder:
        return sorted(folder)
    split = [n for n in c if re.search(r"_\d+\.(csv|zip)$", n)]
    return sorted(split or c)


def month_sources(keys: list[str]) -> dict[int, dict[int, tuple[str, str]]]:
    """year -> month -> (zip key, kind) where kind is 'year' or 'month'."""
    out: dict[int, dict[int, tuple[str, str]]] = {}
    for k in keys:
        if (mt := re.match(r"^(\d{4})-citibike-tripdata\.zip$", k)):
            y = int(mt.group(1))
            with open_remote_zip(k) as z:
                names = z.namelist()
            for m in range(1, 13):
                if pick_members(names, y, m):
                    out.setdefault(y, {})[m] = (k, "year")
        elif (mt := re.match(r"^(\d{4})(\d{2})-citibike-tripdata(\.csv)?\.zip$", k)):
            out.setdefault(int(mt.group(1)), {})[int(mt.group(2))] = (k, "month")
    return out


def choose_months(avail: set[int]) -> list[int]:
    chosen: list[int] = []
    for p in PREFERRED_MONTHS:
        opts = sorted((abs(m - p), m) for m in avail if m not in chosen)
        if opts:
            chosen.append(opts[0][1])
    return sorted(chosen)


def col(cols: dict[str, str], *cands: str) -> str:
    for c in cands:
        if c in cols:
            return cols[c]
    raise KeyError(f"none of {cands} in columns {list(cols)}")


def agg_csv(con, path: Path) -> pd.DataFrame:
    """Per station name: starts, ends, evening starts+ends, coordinate medians, for one CSV."""
    src = f"read_csv('{path}', all_varchar=true, header=true)"
    raw = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()]
    cols = {re.sub(r"\s+", "_", c.strip().lower()): c for c in raw}
    q = lambda c: '"' + c + '"'  # noqa: E731
    sides = []
    for side, tcands, latc, lonc in (
        ("start", ("starttime", "start_time", "started_at"), ("start_station_latitude", "start_lat"),
         ("start_station_longitude", "start_lng")),
        ("end", ("stoptime", "stop_time", "ended_at"), ("end_station_latitude", "end_lat"),
         ("end_station_longitude", "end_lng"))):
        sides.append(f"""SELECT trim({q(col(cols, f'{side}_station_name'))}) AS name,
            try_cast({q(col(cols, *latc))} AS DOUBLE) AS lat,
            try_cast({q(col(cols, *lonc))} AS DOUBLE) AS lon,
            try_cast(regexp_extract({q(col(cols, *tcands))}, '[ T](\\d{{1,2}}):', 1) AS INT) AS h,
            {1 if side == 'start' else 0} AS is_start FROM {src}""")
    lo, hi = EVENING_HOURS
    sql = f"""WITH t AS ({' UNION ALL '.join(sides)})
        SELECT name, sum(is_start) AS starts, sum(1 - is_start) AS ends,
               sum(CASE WHEN h BETWEEN {lo} AND {hi} THEN 1 ELSE 0 END) AS evening_trips,
               count(h) AS n_hour, median(lat) AS lat, median(lon) AS lon
        FROM t WHERE name IS NOT NULL AND name <> '' AND lat IS NOT NULL AND lat <> 0
        GROUP BY name"""
    df = con.execute(sql).df()
    total = int(df.starts.sum() + df.ends.sum())
    if total == 0 or df.n_hour.sum() < 0.99 * total:
        raise RuntimeError(f"{path.name}: {total} station events, {df.n_hour.sum()} parsed hours")
    return df.drop(columns="n_hour")


def extract(z: zipfile.ZipFile, member: str) -> Path:
    dest = WORK / Path(member).name
    with z.open(member) as fi, open(dest, "wb") as fo:
        shutil.copyfileobj(fi, fo, 8 << 20)
    return dest


def agg_members(con, z: zipfile.ZipFile, members: list[str], y: int, m: int) -> list[pd.DataFrame]:
    parts = []
    for mem in members:
        p = extract(z, mem)
        try:
            if p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as inner:
                    names = inner.namelist()
                    sub = pick_members(names, y, m) or sorted(
                        n for n in names if n.lower().endswith(".csv") and "__MACOSX" not in n)
                    if not sub:
                        raise RuntimeError(f"no CSVs in nested {mem}: {names}")
                    parts += agg_members(con, inner, sub, y, m)
            else:
                parts.append(agg_csv(con, p))
        finally:
            p.unlink()
    return parts


def nyc_filter(df: pd.DataFrame) -> pd.DataFrame:
    import geopandas as gpd
    b = df.lat.between(*BBOX["lat"]) & df.lon.between(*BBOX["lon"])
    df = df[b].copy()
    boro = gpd.read_file(gzip.open(GOV / "geo_boroughs.geojson.gz")).to_crs(METRIC_CRS)
    area = boro.geometry.buffer(NYC_BUFFER_FT).union_all()
    pts = gpd.GeoSeries(gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326").to_crs(METRIC_CRS)
    inside = pts.within(area).to_numpy()
    print(f"NYC filter: kept {inside.sum():,} of {len(df):,} station-years in bbox "
          f"({(~b).sum():,} outside bbox dropped earlier)", flush=True)
    return df[inside]


def run() -> None:
    t0 = time.time()
    WORK.mkdir(parents=True, exist_ok=True)
    src = month_sources(list_bucket())
    con = duckdb.connect()
    con.execute("SET threads TO 4")
    rows, sampled = [], {}
    for y in sorted(v for v in src if v >= FIRST_YEAR):
        months = choose_months(set(src[y]))
        sampled[y] = months
        for m in months:
            key, kind = src[y][m]
            with open_remote_zip(key) as z:
                members = pick_members(z.namelist(), y, m) if kind == "year" else sorted(
                    n for n in z.namelist() if n.lower().endswith(".csv") and "__MACOSX" not in n)
                parts = agg_members(con, z, members, y, m)
            d = pd.concat(parts, ignore_index=True)
            d["w"] = d.starts + d.ends
            d["lat_w"], d["lon_w"] = d.lat * d.w, d.lon * d.w
            g = d.groupby("name", as_index=False)[["starts", "ends", "evening_trips", "w", "lat_w", "lon_w"]].sum()
            g["year"], g["month"] = y, m
            rows.append(g)
            print(f"{y}-{m:02d} [{key}: {len(members)} member(s)] stations={len(g):,} "
                  f"starts={int(g.starts.sum()):,} ({time.time() - t0:.0f}s)", flush=True)
    a = pd.concat(rows, ignore_index=True)
    out = a.groupby(["year", "name"], as_index=False).agg(
        starts=("starts", "sum"), ends=("ends", "sum"), evening_trips=("evening_trips", "sum"),
        w=("w", "sum"), lat_w=("lat_w", "sum"), lon_w=("lon_w", "sum"),
        months_present=("month", "nunique"))
    out["lat"], out["lon"] = out.lat_w / out.w, out.lon_w / out.w
    out = out.rename(columns={"name": "station_name"})
    out["months_sampled"] = out.year.map(lambda y: len(sampled[y]))
    out["sampled_months"] = out.year.map(lambda y: ",".join(f"{m:02d}" for m in sampled[y]))
    out["trips"] = out.starts + out.ends
    out["annualized_trips"] = out.trips * 12 / out.months_sampled
    out["evening_share"] = out.evening_trips / out.trips
    out["station_key"] = (out.station_name + "|" + out.lat.round(3).astype(str) + "|"
                          + out.lon.round(3).astype(str))
    out = nyc_filter(out)
    cols = ["year", "station_name", "station_key", "lat", "lon", "starts", "ends", "trips",
            "evening_trips", "months_sampled", "sampled_months", "months_present",
            "annualized_trips", "evening_share"]
    out = out[cols].sort_values(["year", "station_name"]).reset_index(drop=True)
    for c in ("starts", "ends", "trips", "evening_trips"):
        out[c] = out[c].astype("int64")
    note = ("Sampled months per year: " + "; ".join(f"{y}: {','.join(map(str, ms))}"
                                                  for y, ms in sampled.items())
            + ". trips = starts+ends at station (each trip counted at both ends); "
              "annualized_trips = trips*12/months_sampled (May/Oct are above-average months; "
              "2013 began June and latest year is partial). Evening = hours 17-22 local. "
              "Station = name within year; lat/lon = trip-weighted mean of per-file medians; NYC borough filter "
              f"with {NYC_BUFFER_FT} ft buffer drops NJ stations.")
    save(out, "citibike_station_year", source=BASE, note=note)
    sysw = out.groupby("year").agg(stations=("station_name", "size"),
                                   annualized_trips=("annualized_trips", "sum"),
                                   evening_share=("evening_trips", "sum"))
    sysw["evening_share"] = sysw.evening_share / out.groupby("year").trips.sum()
    # each trip counted at start and end station -> systemwide trips = half of station events
    sysw["annualized_system_trips_M"] = sysw.annualized_trips / 2 / 1e6
    print(sysw.round(3).to_string())
    ly = out.year.max()
    print(f"Top 10 stations {ly}:")
    print(out[out.year == ly].nlargest(10, "annualized_trips")[
        ["station_name", "lat", "lon", "annualized_trips", "evening_share"]].to_string(index=False))
    shutil.rmtree(WORK)
    print(f"done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    run()
