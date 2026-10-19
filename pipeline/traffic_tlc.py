"""NYC TLC trips -> pickups/dropoffs per taxi zone per year, with evening/night shares.

Sources (no raw trips are stored):
  1. Yellow 2011+: the public monthly parquet files on CloudFront, read remotely with duckdb
     (only time + zone columns). SAMPLED: Jan, Apr, Jul, Oct (annual = 4 months x 3). TLC has
     back-filled zone IDs into the 2011-16 yellow files, so no lat/lon->zone step is needed
     (only 2009-10 still carry coordinates; outside the panel). Reading many files got this
     client blocked by CloudFront (HTTP 403, >1 h), so reads are sequential with pauses.
  2. Yellow, green and HVFHV (Uber/Lyft/Via) 2019+: TLC's monthly zone counts on NYC Open Data
     (c5iv-bn4s), every month. Totals come from here; yellow's evening/night shares from (1).
  3. FHV 2015-2018 (Uber/Lyft before the high-volume category): yearly NYC Open Data trip
     tables aggregated server-side, all weeks. Pickup zone only, used as the dropoff proxy.
Not covered: green 2013-2018 (about 1-2% of trips citywide, more in upper Manhattan / outer
boroughs), non-high-volume FHV 2019+ (black cars, liveries; a few % of trips).

Outputs (data/raw/traffic/):
  tlc_zone_year.parquet: zone, year, service, source, dropoffs, pickups (annual estimates),
      do_wkdy_eve (Mon-Fri 17-22h) and do_night (any day 20:00-03:59), NaN where no hourly data,
      months (months observed), do_proxy ('dropoff' or 'pickup')
  tlc_zone_tract_weights.parquet: zone_id, zone_name, geoid, w (share of zone area in tract)
"""
from __future__ import annotations

import time

import duckdb
import pandas as pd

import traffic_tlc_socrata
from traffic_common import METRIC_CRS, TMP, save, tracts

BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data/{s}_tripdata_{y}-{m:02d}.parquet"
MONTHS = (1, 4, 7, 10)


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


def _month_retry(con, s: str, y: int, m: int, tries: int = 6) -> pd.DataFrame:
    for i in range(tries):
        try:
            cached = (TMP / "tlc" / f"{s}_{y}{m:02d}.parquet").exists()
            df = _month(con, s, y, m)
            if not cached:
                time.sleep(20)  # be polite to CloudFront
            return df
        except duckdb.HTTPException as e:
            if i == tries - 1:
                raise
            print(f"  {s} {y}-{m:02d}: {str(e)[:90]} -> retry in {600 * (i + 1)} s", flush=True)
            time.sleep(600 * (i + 1))


def zone_tract_weights() -> pd.DataFrame:
    import geopandas as gpd
    zones = traffic_tlc_socrata.zones().to_crs(METRIC_CRS)
    t = tracts().to_crs(METRIC_CRS)[["geoid", "geometry"]]
    ov = gpd.overlay(zones, t, how="intersection", keep_geom_type=True)
    ov["a"] = ov.geometry.area
    ov["w"] = ov.a / ov.groupby("locationid").a.transform("sum")
    out = ov[["locationid", "zone", "geoid", "w"]].rename(columns={"locationid": "zone_id",
                                                                   "zone": "zone_name"})
    out = out[out.w > 1e-4]
    save(out, "tlc_zone_tract_weights", source="data.cityofnewyork.us 8meu-9t5y",
         note="area share of each taxi zone in each 2020 tract")
    return out


def _shares(df: pd.DataFrame, weekday) -> pd.DataFrame:
    """Per zone-year: share of trips Mon-Fri 17-22h and 20:00-03:59 (df has dow, hour, n)."""
    eve = df.n.where(weekday & df.hour.between(17, 22), 0)
    night = df.n.where((df.hour >= 20) | (df.hour <= 3), 0)
    g = df.assign(eve=eve, night=night).groupby(["zone", "year"])[["n", "eve", "night"]].sum()
    return pd.DataFrame({"eve_share": g.eve / g.n, "night_share": g.night / g.n}).reset_index()


def run() -> pd.DataFrame:
    con = duckdb.connect()
    # few concurrent range requests: CloudFront blocks bursty clients for a while (HTTP 403)
    con.execute("install httpfs; load httpfs; set enable_progress_bar=false; set threads=2")
    cutoff = pd.Timestamp.today() - pd.DateOffset(months=2)  # TLC publishes with ~2-month lag
    frames = [_month_retry(con, "yellow", y, m) for y in range(2011, cutoff.year + 1)
              for m in MONTHS if (y, m) <= (cutoff.year, cutoff.month)]
    yl = pd.concat(frames, ignore_index=True)
    yl = yl[yl.zone.between(1, 263)]  # 264/265 = unknown / outside NYC
    ydo = yl[yl.side == "do"]
    ysh = _shares(ydo, ydo.dow.between(1, 5))  # duckdb isodow: Mon=1..Sun=7
    months = yl.groupby("year").month.nunique()
    ya = yl.groupby(["zone", "year", "side"]).n.sum().unstack("side", fill_value=0).reset_index()
    ya["months"] = ya.year.map(months)
    ya = ya[ya.year <= 2018]
    yellow = pd.DataFrame({"zone": ya.zone, "year": ya.year, "service": "yellow",
                           "source": "parquet_quarterly", "months": ya.months,
                           "dropoffs": ya["do"] * 12 / ya.months, "pickups": ya.pu * 12 / ya.months})

    zm = traffic_tlc_socrata.zone_monthly()
    zm = zm[zm.zone.between(1, 263)]
    za = zm.groupby(["zone", "year", "service", "side"]).n.sum().unstack("side", fill_value=0)
    za = za.reset_index()
    za["months"] = za.year.map(zm.groupby("year").month.nunique())
    recent = pd.DataFrame({"zone": za.zone, "year": za.year, "service": za.service,
                           "source": "c5iv-bn4s_monthly", "months": za.months,
                           "dropoffs": za["do"] * 12 / za.months, "pickups": za.pu * 12 / za.months})

    fp = traffic_tlc_socrata.fhv_pickups()
    fp = fp[fp.zone.between(1, 263)]
    fsh = _shares(fp, fp.dow.between(1, 5))  # Socrata dow: Sun=0, Mon=1..Sat=6
    fa = fp.groupby(["zone", "year"]).n.sum().reset_index()
    fhv = pd.DataFrame({"zone": fa.zone, "year": fa.year, "service": "fhv",
                        "source": "socrata_fhv_pickups", "months": 12, "dropoffs": fa.n,
                        "pickups": fa.n, "do_proxy": "pickup"})

    out = pd.concat([yellow, recent, fhv], ignore_index=True)
    out["do_proxy"] = out.do_proxy.fillna("dropoff")
    sh = pd.concat([ysh.assign(service="yellow"), fsh.assign(service="fhv")])
    out = out.merge(sh, on=["zone", "year", "service"], how="left")
    out["do_wkdy_eve"] = out.dropoffs * out.eve_share
    out["do_night"] = out.dropoffs * out.night_share
    out = out.drop(columns=["eve_share", "night_share"])
    save(out, "tlc_zone_year", source="TLC parquet (yellow, quarterly) + NYC Open Data c5iv-bn4s, "
         "FHV 2015-18", note="annual estimates; zones 264/265 dropped; see module docstring")
    zone_tract_weights()
    return out


if __name__ == "__main__":
    run()
