"""NYC DOT pedestrian counts (point series).

  - Bi-Annual Pedestrian Counts (cqsj-cfgu): 114 locations, manual counts each spring (May/June)
    and fall (Sept/Oct) since 2007, in AM / midday (MD) / PM periods (weekday counts; DOT's
    methodology uses 2-hour windows). Wide columns like may_07_am, oct24_pm, may_23_p_m.
  - Automated counters (6up2-gnw8 sensor list, ct66-47at 15-minute counts): aggregated
    server-side to sensor x travel mode x year (bikes and pedestrians).
  - Brooklyn Bridge automated pedestrian counts (6fi9-q3ta), hourly 2017-2019, to yearly.
Outputs (data/raw/traffic/):
  dot_ped_biannual.parquet  loc, borough, street, from_street, to_street, lat, lon, year,
                            season, period (am/md/pm), count
  dot_counters_year.parquet sensor_id, name, lat, lon, travelmode, year, count, n_intervals,
                            coverage (share of 15-min intervals in the year with data)
"""
from __future__ import annotations

import re

import pandas as pd

from traffic_common import save, soql

D = "data.cityofnewyork.us"
SEASON = {"may": "spring", "june": "spring", "jun": "spring", "sept": "fall", "sep": "fall",
          "oct": "fall"}


def biannual() -> pd.DataFrame:
    df = soql(D, "cqsj-cfgu", select="*")
    pts = df.the_geom.str.extract(r"POINT \((-?[\d.]+) (-?[\d.]+)\)").astype(float)
    df["lon"], df["lat"] = pts[0], pts[1]
    pat = re.compile(r"^(may|june|jun|sept|sep|oct)_?(\d\d)_([a-z_]+)$")
    cols = [c for c in df.columns if pat.match(c)]
    long = df.melt(id_vars=["loc", "borough", "street_nam", "from_stree", "to_street", "lat", "lon"],
                   value_vars=cols, var_name="col", value_name="count")
    parts = long.col.str.extract(pat)
    long["year"] = 2000 + parts[1].astype(int)
    long["season"] = parts[0].map(SEASON)
    long["period"] = parts[2].str.replace("_", "")  # 'p_m' -> 'pm'
    long["count"] = pd.to_numeric(long["count"], errors="coerce")
    bad = set(long.period) - {"am", "md", "pm"}
    if bad:
        raise RuntimeError(f"unexpected bi-annual period codes: {bad}")
    long = long.dropna(subset=["count"]).drop(columns="col").rename(columns={
        "street_nam": "street", "from_stree": "from_street"})
    save(long, "dot_ped_biannual", source="data.cityofnewyork.us cqsj-cfgu",
         note="manual weekday counts; spring+fall; am/md/pm periods")
    return long


def counters() -> pd.DataFrame:
    sensors = soql(D, "6up2-gnw8", select="id, name, lat, lon, travelmodes, firstdata, lastdata")
    agg = soql(D, "ct66-47at", select="sensor_id, travelmode, date_extract_y(timestamp) as year, "
               "sum(counts) as count, count(*) as n_intervals",
               group="sensor_id, travelmode, year")
    agg = agg.merge(sensors.rename(columns={"id": "sensor_id"}), on="sensor_id", how="left")
    for c in ("year", "count", "n_intervals"):
        agg[c] = pd.to_numeric(agg[c])
    agg["coverage"] = agg.n_intervals / (365 * 96)  # per direction/flow intervals may exceed 1
    bb = soql(D, "6fi9-q3ta", select="date_extract_y(hour_beginning) as year, "
              "sum(pedestrians) as count, count(*) as n_intervals", group="year")
    bb = bb.assign(sensor_id="brooklyn_bridge_6fi9", name="Brooklyn Bridge (DOT demo)",
                   lat=40.7081639691088, lon=-73.9995087014816, travelmode="pedestrian")
    for c in ("year", "count", "n_intervals"):
        bb[c] = pd.to_numeric(bb[c])
    bb["coverage"] = bb.n_intervals / (365 * 24)
    out = pd.concat([agg, bb], ignore_index=True)
    out["lat"], out["lon"] = pd.to_numeric(out.lat), pd.to_numeric(out.lon)
    out = out[["sensor_id", "name", "lat", "lon", "travelmode", "year", "count", "n_intervals",
               "coverage", "firstdata", "lastdata"]]
    save(out, "dot_counters_year", source="data.cityofnewyork.us 6up2-gnw8, ct66-47at, 6fi9-q3ta",
         note="automated counters summed per sensor x mode x year; check coverage before use")
    return out


def run() -> None:
    biannual()
    counters()


if __name__ == "__main__":
    run()
