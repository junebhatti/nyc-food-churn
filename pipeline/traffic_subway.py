"""MTA subway entries per station complex per year (2011-now) + weekday-evening share.

Sources (all data.ny.gov):
  - Hourly ridership 2017-2019 (t69i-h2me), 2020-2024 (wujg-7c2s), 2025+ (5wq4-mkjj):
    aggregated server-side per month to station complex x day-of-week x hour.
  - MetroCard History 2010-2021 (v7qc-gwpn): weekly fare swipes per remote unit (= turnstile
    entries without counter differencing). Used for 2011-2016, mapped remote -> complex
    (traffic_subway_map.py) and scaled per complex to the hourly series on the 2017-2018 overlap.
  - Weekday-evening share before 2017 comes from sampled turnstile weeks (traffic_turnstile.py).

Outputs (data/raw/traffic/):
  subway_hourly_profile.parquet  complex_id, year, month, dow (0=Sun), hour, ridership
  subway_station_year.parquet    complex_id, station, borough, lat, lon, year, entries,
                                 entries_source, days_covered, wkdy_eve_share, eve_share_source
"""
from __future__ import annotations

import calendar
import time

import numpy as np
import pandas as pd

from traffic_common import OUT, TMP, save, soql
import traffic_subway_map
import traffic_turnstile

D = "data.ny.gov"
HOURLY = [("t69i-h2me", 2017, 2019), ("wujg-7c2s", 2020, 2024), ("5wq4-mkjj", 2025, 2026)]
EVE_HOURS = range(17, 23)  # 5pm-11pm = hours 17..22


def _hourly_month(dsid: str, y: int, m: int) -> pd.DataFrame:
    """One month as 7-day chunks (whole-month aggregations time out on Socrata)."""
    cache = TMP / f"hourly_{y}{m:02d}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    last = calendar.monthrange(y, m)[1]
    frames = []
    for d0 in range(1, last + 1, 7):
        a = pd.Timestamp(y, m, d0)
        b = min(a + pd.Timedelta(days=7), pd.Timestamp(y, m, last) + pd.Timedelta(days=1))
        df = soql(D, dsid, select="station_complex_id, date_extract_dow(transit_timestamp) as dow, "
                  "date_extract_hh(transit_timestamp) as hour, sum(ridership) as ridership",
                  where=f"transit_timestamp >= '{a:%Y-%m-%dT%H:%M:%S}' and "
                        f"transit_timestamp < '{b:%Y-%m-%dT%H:%M:%S}'",
                  group="station_complex_id, dow, hour", page=100_000)
        if df.empty:
            continue
        df["dow"] = df.dow.astype(int)
        df["days"] = 1  # each dow occurs once in a <=7-day chunk; a present dow = a day with data
        frames.append(df)
        time.sleep(0.5)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).rename(columns={"station_complex_id": "complex_id"})
    df["hour"] = df.hour.astype(int)
    df["ridership"] = df.ridership.astype(float)
    # days with data: per chunk, distinct dows present (approximation: assumes no station-level gaps)
    ndays = sum(f.dow.nunique() for f in frames)
    df = df.groupby(["complex_id", "dow", "hour"], as_index=False).agg(
        ridership=("ridership", "sum"), days=("days", "sum"))
    df["year"], df["month"], df["month_days"] = y, m, ndays
    df.to_parquet(cache, index=False)
    return df


def hourly_profile() -> pd.DataFrame:
    today = pd.Timestamp.today()
    frames = []
    for dsid, y0, y1 in HOURLY:
        for y in range(y0, y1 + 1):
            for m in range(1, 13):
                if (y, m) >= (today.year, today.month):
                    break
                df = _hourly_month(dsid, y, m)
                if df.empty:
                    print(f"  hourly {y}-{m:02d}: no rows", flush=True)
                    continue
                frames.append(df)
            print(f"  hourly {y}: done ({dsid})", flush=True)
    out = pd.concat(frames, ignore_index=True)
    save(out.drop(columns=["days", "month_days"]), "subway_hourly_profile",
         source="data.ny.gov " + ", ".join(h[0] for h in HOURLY),
         note="sum of hourly ridership (entries incl. OMNY) per complex x month x dow x hour")
    return out


def _hourly_year(prof: pd.DataFrame) -> pd.DataFrame:
    """Annual entries per complex; partial years annualized by days with data."""
    p = prof.copy()
    p["wkdy_eve"] = p.dow.between(1, 5) & p.hour.isin(EVE_HOURS)
    days = p.groupby(["year", "month"]).month_days.first().groupby("year").sum()
    g = p.groupby(["complex_id", "year"])
    yr = pd.DataFrame({"entries_raw": g.ridership.sum(),
                       "eve": p[p.wkdy_eve].groupby(["complex_id", "year"]).ridership.sum()})
    yr = yr.reset_index()
    yr["days_covered"] = yr.year.map(days)
    ndays = yr.year.map(lambda y: 366 if calendar.isleap(y) else 365)
    yr["entries"] = yr.entries_raw * ndays / yr.days_covered.clip(upper=ndays)
    yr["wkdy_eve_share"] = yr.eve.fillna(0) / yr.entries_raw
    yr["entries_source"] = "hourly"
    yr["eve_share_source"] = "hourly"
    return yr.drop(columns=["entries_raw", "eve"])


def metrocard_weekly() -> pd.DataFrame:
    mc = soql(D, "v7qc-gwpn", select="*", page=100_000)
    fare = [c for c in mc.columns if c not in ("from_date", "to_date", "remote_station_id", "station")]
    mc["swipes"] = mc[fare].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    mc["from_date"] = pd.to_datetime(mc.from_date)
    return mc[["from_date", "remote_station_id", "station", "swipes"]]


def run() -> pd.DataFrame:
    stations = traffic_subway_map.complexes()
    prof = hourly_profile()
    hy = _hourly_year(prof)

    mc = metrocard_weekly()
    rmap = traffic_subway_map.remote_to_complex(stations)
    mc = mc.merge(rmap[["remote", "complex_id"]], left_on="remote_station_id", right_on="remote",
                  how="left")
    unm = mc[mc.complex_id.isna()]
    print(f"  metrocard: {unm.swipes.sum() / mc.swipes.sum():.2%} of swipes on unmapped remotes "
          f"({unm.remote_station_id.nunique()} remotes)", flush=True)
    mc = mc.dropna(subset=["complex_id"])
    mc["year"] = mc.from_date.dt.year
    wk = mc.groupby("year").from_date.nunique()
    my = mc.groupby(["complex_id", "year"]).swipes.sum().reset_index()
    my["swipes_ann"] = my.swipes * 52.18 / my.year.map(wk)

    # per-complex scale factor hourly/metrocard on the 2017-2018 overlap (OMNY not yet live)
    ov = hy[hy.year.isin([2017, 2018])].merge(my, on=["complex_id", "year"])
    ratio = (ov.groupby("complex_id").entries.sum() / ov.groupby("complex_id").swipes_ann.sum())
    med = float(ratio.median())
    print(f"  hourly/metrocard ratio 2017-18: median {med:.3f}, IQR "
          f"{ratio.quantile(.25):.3f}-{ratio.quantile(.75):.3f}, n={len(ratio)}", flush=True)
    ratio = ratio.where(ratio.between(0.67, 1.5), med)  # implausible -> systemwide median
    early = my[my.year.between(2011, 2016)].copy()
    early["entries"] = early.swipes_ann * early.complex_id.map(ratio).fillna(med)
    early["entries_source"] = "metrocard_history_scaled"
    early["days_covered"] = early.year.map(wk) * 7

    eve = traffic_turnstile.evening_share(rmap, hy)
    early = early.merge(eve, on=["complex_id", "year"], how="left")
    out = pd.concat([early.drop(columns=["swipes", "swipes_ann"]), hy], ignore_index=True)
    out = out.merge(stations[["complex_id", "station", "borough", "lat", "lon"]],
                    on="complex_id", how="left")
    miss = out[out.lat.isna()].complex_id.unique()
    if len(miss):
        print(f"  WARNING: {len(miss)} complex ids without coordinates dropped: {list(miss)[:10]}")
    out = out.dropna(subset=["lat"])
    out = out[["complex_id", "station", "borough", "lat", "lon", "year", "entries",
               "entries_source", "days_covered", "wkdy_eve_share", "eve_share_source"]]
    save(out.sort_values(["complex_id", "year"]), "subway_station_year",
         source="data.ny.gov hourly ridership + v7qc-gwpn MetroCard history + turnstile samples",
         note="annual entries per station complex; see data/notes/traffic.md")
    return out


if __name__ == "__main__":
    run()
