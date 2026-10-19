"""Weekday-evening (Mon-Fri 5-11pm) share of subway entries before 2017, from turnstile audits.

Turnstile counters are cumulative and read about every 4 hours, so for each sampled week:
  1. sort readings per turnstile (c_a, unit, scp), difference the entries counter;
  2. drop negative diffs (counter resets/reversed), diffs > 3,000 per interval or > 1,000/hour
     (counter jumps), and intervals shorter than 0.5 h or longer than 8 h;
  3. spread each interval's entries evenly over the clock hours it covers;
  4. sum per remote unit -> station complex (traffic_subway_map crosswalk).
Sample: 4 weeks a year (weeks ending on the Saturday closest to Mar/Jun/Sep/Nov 15), 2011-2019.
2014-2019 come from data.ny.gov yearly turnstile datasets; 2011-2013 from MTA's retired weekly
files via the Wayback Machine (old 8-readings-per-line format).
The 4-hour reading grid makes the raw share approximate, so it is calibrated per complex on
2017-2019, where the hourly ridership gives the true share: share = raw * median(true/raw).
Output: data/raw/traffic/subway_turnstile_eve_share.parquet
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from traffic_common import get, save, soql

D = "data.ny.gov"
TS = {2014: "i55r-43gk", 2015: "ug6q-shqc", 2016: "ekwu-khcy", 2017: "v5y5-mwpb",
      2018: "bjcb-yee3", 2019: "xfn5-qji9"}
MTA_URL = "web.mta.info/developers/data/nyct/turnstile/turnstile_{d:%y%m%d}.txt"
CDX = "https://web.archive.org/cdx/search/cdx"
YEARS = range(2011, 2020)


def _sample_saturdays(y: int) -> list[pd.Timestamp]:
    out = []
    for m in (3, 6, 9, 11):
        t = pd.Timestamp(y, m, 15)
        out.append(t + pd.Timedelta(days=(5 - t.dayofweek + 3) % 7 - 3))  # nearest Saturday
    return out


def _socrata_week(y: int, sat: pd.Timestamp) -> pd.DataFrame:
    a, b = sat - pd.Timedelta(days=8), sat
    df = soql(D, TS[y], select="c_a, unit, scp, date, time, entries",
              where=f"date >= '{a:%Y-%m-%d}T00:00:00' and date <= '{b:%Y-%m-%d}T00:00:00'",
              order="c_a, unit, scp, date, time", page=200_000)
    df["ts"] = pd.to_datetime(df.date.str[:10] + " " + df.time)
    return df[["c_a", "unit", "scp", "ts", "entries"]]


def _wayback_week(sat: pd.Timestamp) -> pd.DataFrame:
    # several captures are truncated (1 MB); take the largest 200 capture
    url = MTA_URL.format(d=sat)
    caps = get(CDX, params={"url": url, "output": "json", "fl": "timestamp,statuscode,length"}).json()
    caps = [c for c in caps[1:] if c[1] == "200"]
    if not caps:
        raise RuntimeError(f"no Wayback capture for {url}")
    ts = max(caps, key=lambda c: int(c[2]))[0]
    txt = get(f"https://web.archive.org/web/{ts}id_/http://{url}").text
    if len(txt) < 5e6:
        raise RuntimeError(f"Wayback capture {ts} of {url} looks truncated ({len(txt):,} bytes)")
    recs = []
    for line in txt.splitlines():
        f = line.strip().split(",")
        if len(f) < 8 or not f[1].startswith("R"):
            continue
        for i in range(3, len(f) - 4, 5):
            recs.append((f[0], f[1], f[2], f[i], f[i + 1], f[i + 3]))
    df = pd.DataFrame(recs, columns=["c_a", "unit", "scp", "date", "time", "entries"])
    df["ts"] = pd.to_datetime(df.date + " " + df.time, format="%m-%d-%y %H:%M:%S", errors="coerce")
    bad = df.ts.isna().mean()
    if bad > 0.01:
        raise RuntimeError(f"wayback {sat.date()}: {bad:.1%} unparseable timestamps")
    return df.dropna(subset=["ts"])[["c_a", "unit", "scp", "ts", "entries"]]


def _unit_week(df: pd.DataFrame, sat: pd.Timestamp) -> pd.DataFrame:
    """Difference counters and return per-unit total and weekday-evening entries for the week."""
    df = df.copy()
    df["entries"] = pd.to_numeric(df.entries, errors="coerce")
    df = df.dropna(subset=["entries"]).drop_duplicates(["c_a", "unit", "scp", "ts"])
    df = df.sort_values(["c_a", "unit", "scp", "ts"])
    g = df.groupby(["c_a", "unit", "scp"])
    df["d"] = g.entries.diff()
    df["t0"] = g.ts.shift()
    df = df.dropna(subset=["d", "t0"])
    hrs = (df.ts - df.t0).dt.total_seconds() / 3600
    start = sat - pd.Timedelta(days=7)
    keep = (df.d >= 0) & (df.d <= 3000) & hrs.between(0.5, 8) & (df.d / hrs <= 1000) & \
           (df.t0 >= start) & (df.ts <= sat + pd.Timedelta(days=1))
    kept_share = keep.mean()
    df, hrs = df[keep], hrs[keep]
    n = np.maximum(np.round(hrs).astype(int), 1)
    rep = df.loc[df.index.repeat(n)].copy()
    k = rep.groupby(level=0).cumcount()
    rep["hour_ts"] = rep.t0 + pd.to_timedelta(k, unit="h")
    rep["e"] = rep.d / n.loc[rep.index].values
    hr, dow = rep.hour_ts.dt.hour, rep.hour_ts.dt.dayofweek
    rep["eve"] = np.where((dow <= 4) & (hr >= 17) & (hr <= 22), rep.e, 0.0)
    out = rep.groupby("unit").agg(entries=("e", "sum"), eve=("eve", "sum")).reset_index()
    print(f"    week {sat.date()}: {len(out)} units, {out.entries.sum() / 1e6:.2f}M entries, "
          f"{kept_share:.1%} intervals kept", flush=True)
    return out


def evening_share(rmap: pd.DataFrame, hourly_year: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for y in YEARS:
        for sat in _sample_saturdays(y):
            raw = _socrata_week(y, sat) if y in TS else _wayback_week(sat)
            w = _unit_week(raw, sat)
            w["year"] = y
            frames.append(w)
    u = pd.concat(frames, ignore_index=True)
    u = u.merge(rmap[["remote", "complex_id"]], left_on="unit", right_on="remote", how="inner")
    c = u.groupby(["complex_id", "year"])[["entries", "eve"]].sum().reset_index()
    c["raw_share"] = c.eve / c.entries
    true = hourly_year[["complex_id", "year", "wkdy_eve_share"]].rename(
        columns={"wkdy_eve_share": "true_share"})
    cal = c[c.year >= 2017].merge(true, on=["complex_id", "year"])
    k = (cal.true_share / cal.raw_share).replace([np.inf, -np.inf], np.nan)
    kc = k.groupby(cal.complex_id).median()
    kmed = float(k.median())
    corr = cal[["true_share", "raw_share"]].corr().iloc[0, 1]
    print(f"  turnstile eve share: calib factor median {kmed:.3f}; raw vs true corr {corr:.3f} "
          f"(n={len(cal)})", flush=True)
    c["wkdy_eve_share"] = (c.raw_share * c.complex_id.map(kc).fillna(kmed)).clip(0, 0.6)
    c["eve_share_source"] = "turnstile_sample_calibrated"
    save(c, "subway_turnstile_eve_share", source="data.ny.gov turnstile 2014-19 + Wayback 2011-13",
         note="4 sampled weeks/yr; calibrated per complex to hourly 2017-19")
    return c[c.year <= 2016][["complex_id", "year", "wkdy_eve_share", "eve_share_source"]]
