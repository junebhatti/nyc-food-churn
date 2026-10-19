"""NYC TLC trips -> pickups/dropoffs per taxi zone per year, with evening/night shares.

Sources (no raw trips are stored):
  1. Yellow 2011+, green 2014-2018 and FHV 2015-2018: the public monthly parquet files on
     CloudFront, read remotely with duckdb (only time + zone columns). SAMPLED: Jan, Apr, Jul,
     Oct (annual = 4 months x 3). TLC has back-filled zone IDs into the 2011-16 yellow files,
     so no lat/lon->zone step is needed. Reading many files got this client blocked by
     CloudFront (HTTP 403, >1 h), so reads are sequential with pauses. Months CloudFront does
     not publish (403/404 while a known file still loads) are logged and skipped: all green
     2013 (green began 2013-08 but TLC's files start 2014-01).
     FHV 2015-2018 holds the pre-high-volume Uber/Lyft/Via trips, with no company field and
     mostly blank dropoff zones: pickups stand in for dropoffs (do_proxy = 'pickup').
  2. Yellow, green and HVFHV (Uber/Lyft/Via) 2019+: TLC's monthly zone counts on NYC Open Data
     (c5iv-bn4s), every month. Totals come from here; yellow's evening/night shares from (1).
Not covered: green 2013-08..12 (no files; ~1% of 2013 trips), non-high-volume FHV 2019+
(black cars, liveries; a few % of trips), hourly shares for HVFHV and green 2019+.

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
import requests

import traffic_tlc_socrata
from traffic_common import METRIC_CRS, SESSION, TMP, save, tracts

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


PROBE = BASE.format(s="yellow", y=2015, m=1)  # a file that certainly exists
SKIPPED: list[str] = []  # "service YYYY-MM" months CloudFront does not publish


def _status(url: str) -> int | None:
    """HTTP status of a HEAD request, or None if the request itself failed."""
    try:
        return SESSION.head(url, timeout=(10, 30)).status_code
    except requests.RequestException as e:
        print(f"  HEAD {url}: {type(e).__name__}", flush=True)
        return None


def _month_retry(con, s: str, y: int, m: int, tries: int = 4) -> pd.DataFrame | None:
    """One month's counts, or None if TLC never published that file.

    CloudFront (S3 behind it) answers 403 for a missing key, and also 403 when it is
    throttling this client. A 403/404 counts as "not published" only if a known file still
    returns 200; anything else (block, 5xx, timeout, reset) is transient: retried with
    backoff, at most `tries` times, then raised."""
    if (TMP / "tlc" / f"{s}_{y}{m:02d}.parquet").exists():
        return _month(con, s, y, m)
    url = BASE.format(s=s, y=y, m=m)
    for i in range(tries):
        code = _status(url)
        if code in (403, 404) and _status(PROBE) == 200:
            print(f"  {s} {y}-{m:02d}: HTTP {code}, not published -> skipped", flush=True)
            SKIPPED.append(f"{s} {y}-{m:02d}")
            return None
        if code == 200:
            try:
                df = _month(con, s, y, m)
                time.sleep(20)  # be polite to CloudFront
                return df
            except (duckdb.HTTPException, duckdb.IOException) as e:
                err = str(e)[:90]
        else:
            err = f"HEAD {code}"
        if i == tries - 1:
            raise RuntimeError(f"{s} {y}-{m:02d}: still failing after {tries} tries ({err})")
        print(f"  {s} {y}-{m:02d}: {err} -> retry in {300 * (i + 1)} s", flush=True)
        time.sleep(300 * (i + 1))


def _quarterly(con, s: str, years, last=(9999, 12)) -> pd.DataFrame:
    """Sampled months (MONTHS) up to `last` for one service; unpublished months skipped."""
    frames = [_month_retry(con, s, y, m) for y in years for m in MONTHS if (y, m) <= last]
    print(f"  tlc {s} {years[0]}-{years[-1]}: done", flush=True)
    df = pd.concat([f for f in frames if f is not None], ignore_index=True)
    return df[df.zone.between(1, 263)]  # 264/265 = unknown / outside NYC


def _annual(df: pd.DataFrame, s: str, proxy: bool = False) -> pd.DataFrame:
    """Zone-year annual estimates from sampled months (scaled by 12 / months observed)."""
    months = df.groupby("year").month.nunique()
    a = df.groupby(["zone", "year", "side"]).n.sum().unstack("side", fill_value=0).reset_index()
    a["months"] = a.year.map(months)
    pu = a.pu * 12 / a.months
    return pd.DataFrame({"zone": a.zone, "year": a.year, "service": s,
                         "source": "parquet_quarterly", "months": a.months,
                         "dropoffs": pu if proxy else a["do"] * 12 / a.months, "pickups": pu,
                         "do_proxy": "pickup" if proxy else "dropoff"})


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
    con.execute("install httpfs; load httpfs; set enable_progress_bar=false; set threads=2; "
                "set http_timeout=120; set http_retries=3")
    cutoff = pd.Timestamp.today() - pd.DateOffset(months=2)  # TLC publishes with ~2-month lag
    yl = _quarterly(con, "yellow", range(2011, cutoff.year + 1), (cutoff.year, cutoff.month))
    gr = _quarterly(con, "green", range(2013, 2019))  # green began 2013-08
    fh = _quarterly(con, "fhv", range(2015, 2019))  # Uber/Lyft filed as FHV until 2019-01
    fh = fh[fh.side == "pu"]  # FHV dropoff zones are mostly blank: pickups stand in
    sh = pd.concat([_shares(d, d.dow.between(1, 5)).assign(service=s)  # isodow Mon=1..Sun=7
                    for s, d in (("yellow", yl[yl.side == "do"]), ("green", gr[gr.side == "do"]),
                                 ("fhv", fh))])
    old = [_annual(yl[yl.year <= 2018], "yellow"), _annual(gr, "green"),
           _annual(fh, "fhv", proxy=True)]

    zm = traffic_tlc_socrata.zone_monthly()
    zm = zm[zm.zone.between(1, 263)]
    za = zm.groupby(["zone", "year", "service", "side"]).n.sum().unstack("side", fill_value=0)
    za = za.reset_index()
    za["months"] = za.year.map(zm.groupby("year").month.nunique())
    recent = pd.DataFrame({"zone": za.zone, "year": za.year, "service": za.service,
                           "source": "c5iv-bn4s_monthly", "months": za.months,
                           "dropoffs": za["do"] * 12 / za.months, "pickups": za.pu * 12 / za.months,
                           "do_proxy": "dropoff"})

    out = pd.concat([*old, recent], ignore_index=True)
    out = out.merge(sh, on=["zone", "year", "service"], how="left")
    out["do_wkdy_eve"] = out.dropoffs * out.eve_share
    out["do_night"] = out.dropoffs * out.night_share
    out = out.drop(columns=["eve_share", "night_share"])
    print(f"  months not published (skipped): {SKIPPED or 'none'}", flush=True)
    save(out, "tlc_zone_year", source="TLC CloudFront parquet (yellow/green/FHV, Jan/Apr/Jul/Oct) "
         "+ NYC Open Data c5iv-bn4s (2019+)",
         note=f"annual estimates; zones 264/265 dropped; skipped (unpublished): {SKIPPED}")
    zone_tract_weights()
    return out


if __name__ == "__main__":
    run()
