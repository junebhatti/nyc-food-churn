"""NYC TLC trip records -> pickups/dropoffs per taxi zone per year, with evening/night shares.

duckdb reads the public monthly parquet files remotely (HTTP range requests, only the time and
location columns) and aggregates; no raw trips are stored. All months are read (not sampled).
Services: yellow 2011+, green 2013-08+, fhv 2015+ (non-high-volume bases; before 2019-02 also
Uber/Lyft), fhvhv 2019-02+ (Uber, Lyft, Via, Juno).
TLC has back-filled LocationIDs into the 2011-2016 yellow files, so no lat/lon->zone step is
needed for 2011+ (only 2009-2010 files still carry coordinates; they are outside the panel).
FHV files before 2019 mostly lack dropoff zones; for those, pickups stand in for dropoffs.

Outputs (data/raw/traffic/):
  tlc_zone_year.parquet: zone, year, service, pickups, dropoffs, do_wkdy_eve (Mon-Fri 17-22h),
      do_night (any day 20:00-03:59), months, do_proxy ('dropoff' or 'pickup')
  tlc_zone_tract_weights.parquet: zone, geoid, w (share of the zone's land area in the tract)
"""
from __future__ import annotations

import io
import time
import zipfile

import duckdb
import pandas as pd

from traffic_common import METRIC_CRS, TMP, get, save, tracts

BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data/{s}_tripdata_{y}-{m:02d}.parquet"
ZONES = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"
START = {"yellow": (2011, 1), "green": (2013, 8), "fhv": (2015, 1), "fhvhv": (2019, 2)}


def _cols(con, url: str) -> tuple[str, str, str, str]:
    names = [r[0] for r in con.execute(f"select name from parquet_schema('{url}')").fetchall()]
    low = {n.lower(): n for n in names}
    pu_t = next(low[k] for k in ("tpep_pickup_datetime", "lpep_pickup_datetime", "pickup_datetime")
                if k in low)
    do_t = next(low[k] for k in ("tpep_dropoff_datetime", "lpep_dropoff_datetime",
                                 "dropoff_datetime") if k in low)
    return pu_t, do_t, low["pulocationid"], low["dolocationid"]


def _month(con, s: str, y: int, m: int) -> pd.DataFrame:
    cache = TMP / "tlc" / f"{s}_{y}{m:02d}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    url = BASE.format(s=s, y=y, m=m)
    pu_t, do_t, pu, do = _cols(con, url)
    a, b = f"{y}-{m:02d}-01", f"{y + (m == 12)}-{m % 12 + 1:02d}-01"
    q = []
    for side, t, loc in (("pu", pu_t, pu), ("do", do_t, do)):
        q.append(f"""select '{side}' as side, cast({loc} as int) as zone,
            isodow(cast({t} as timestamp)) as dow, hour(cast({t} as timestamp)) as hour, count(*) as n
            from read_parquet('{url}')
            where cast({pu_t} as timestamp) >= '{a}' and cast({pu_t} as timestamp) < '{b}'
            group by all""")
    df = con.execute(" union all ".join(q)).df()
    df["service"], df["year"], df["month"] = s, y, m
    cache.parent.mkdir(exist_ok=True)
    df.to_parquet(cache, index=False)
    return df


def zone_tract_weights() -> pd.DataFrame:
    import geopandas as gpd
    z = zipfile.ZipFile(io.BytesIO(get(ZONES).content))
    d = TMP / "taxi_zones"
    z.extractall(d)
    shp = next(d.rglob("*.shp"))
    zones = gpd.read_file(shp).to_crs(METRIC_CRS)[["LocationID", "zone", "borough", "geometry"]]
    t = tracts().to_crs(METRIC_CRS)[["geoid", "geometry"]]
    ov = gpd.overlay(zones, t, how="intersection", keep_geom_type=True)
    ov["a"] = ov.geometry.area
    ov["w"] = ov.a / ov.groupby("LocationID").a.transform("sum")
    out = ov[["LocationID", "zone", "geoid", "w"]].rename(columns={"LocationID": "zone_id",
                                                                   "zone": "zone_name"})
    out = out[out.w > 1e-4]
    save(out, "tlc_zone_tract_weights", source=ZONES,
         note="area share of each taxi zone in each 2020 tract (zone geometry clipped to tracts)")
    return out


def run() -> pd.DataFrame:
    con = duckdb.connect()
    con.execute("install httpfs; load httpfs; set enable_progress_bar=false")
    cutoff = pd.Timestamp.today() - pd.DateOffset(months=2)  # TLC publishes with ~2-month lag
    frames = []
    for s, (y0, m0) in START.items():
        for y in range(y0, cutoff.year + 1):
            for m in range(1, 13):
                if (y, m) < (y0, m0) or (y, m) > (cutoff.year, cutoff.month):
                    continue
                try:
                    frames.append(_month(con, s, y, m))
                except duckdb.HTTPException as e:  # not yet published: log and skip that month
                    print(f"  {s} {y}-{m:02d}: not available ({str(e)[:80]})", flush=True)
                time.sleep(0.2)
            print(f"  tlc {s} {y}: done", flush=True)
    df = pd.concat(frames, ignore_index=True)
    df = df[df.zone.between(1, 263)]  # 264/265 = unknown / outside NYC
    wk_eve = df.dow.between(1, 5) & df.hour.between(17, 22)
    night = (df.hour >= 20) | (df.hour <= 3)
    df["eve"], df["night"] = df.n.where(wk_eve, 0), df.n.where(night, 0)
    g = df.groupby(["zone", "year", "service", "side"]).agg(
        n=("n", "sum"), eve=("eve", "sum"), night=("night", "sum")).unstack("side", fill_value=0)
    g.columns = [f"{a}_{b}" for a, b in g.columns]
    g = g.reset_index()
    months = df.groupby(["year", "service"]).month.nunique().rename("months").reset_index()
    g = g.merge(months, on=["year", "service"])
    # FHV before 2019: dropoff zones mostly missing -> pickups as proxy
    do_share = g.groupby(["year", "service"]).n_do.transform("sum") / \
        g.groupby(["year", "service"]).n_pu.transform("sum")
    proxy = do_share < 0.5
    out = pd.DataFrame({
        "zone": g.zone, "year": g.year, "service": g.service, "months": g.months,
        "pickups": g.n_pu, "dropoffs": g.n_do.where(~proxy, g.n_pu),
        "do_wkdy_eve": g.eve_do.where(~proxy, g.eve_pu), "do_night": g.night_do.where(~proxy, g.night_pu),
        "do_proxy": proxy.map({True: "pickup", False: "dropoff"})})
    save(out, "tlc_zone_year", source=BASE.format(s="{service}", y="{y}", m=0),
         note="all months read remotely with duckdb; zones 264/265 dropped; fhv<2019 uses pickups")
    zone_tract_weights()
    return out


if __name__ == "__main__":
    run()
