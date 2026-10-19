"""TLC aggregates from NYC Open Data (Socrata), used where the CloudFront parquet files are not.

  - c5iv-bn4s "Pickups and Drop-offs by Taxi Zone and Industry": monthly pickups and dropoffs per
    zone for Yellow, Green and FHV - High Volume, 2019-01 onward, every month (TLC's own counts).
  - FHV trip data 2015-2018 (yearly datasets): pre-high-volume Uber/Lyft/Via trips were filed
    as ordinary FHV. Pickup zone only (dropoff zones are mostly blank). Aggregated server-side
    to zone x day-of-week x hour over the whole year (all trips, not sampled).
  - 8meu-9t5y: taxi zone polygons.
"""
from __future__ import annotations


import pandas as pd

from traffic_common import TMP, soql

D = "data.cityofnewyork.us"
FHV = {2015: ("7dfh-3irt", "pickup_date", "locationid"),
       2016: ("yini-w76t", "pickup_date", "locationid"),
       2017: ("avz8-mqzz", "pickup_datetime", "pulocationid"),
       2018: ("am94-epxh", "pickup_datetime", "pulocationid")}
INDUSTRY = {"Yellow Taxi": "yellow", "Green Cab": "green", "FHV - High Volume": "fhvhv"}


def zone_monthly() -> pd.DataFrame:
    """zone, year, month, service, side ('pu'/'do'), n -- complete months 2019+."""
    df = soql(D, "c5iv-bn4s", select="metric_month, industry, pickup_dropoff, locationid, trip_count",
              page=100_000)
    unknown = set(df.industry) - set(INDUSTRY)
    if unknown:
        raise RuntimeError(f"c5iv-bn4s: unexpected industries {unknown}")
    m = pd.to_datetime(df.metric_month)
    return pd.DataFrame({"zone": pd.to_numeric(df.locationid), "year": m.dt.year,
                         "month": m.dt.month, "service": df.industry.map(INDUSTRY),
                         "side": df.pickup_dropoff.map({"Pick-up": "pu", "Drop-off": "do"}),
                         "n": pd.to_numeric(df.trip_count)})


def fhv_pickups() -> pd.DataFrame:
    """zone, year, dow (0=Sun), hour, n -- FHV pickups 2015-2018, all trips."""
    frames = []
    for y, (ds, tcol, loc) in FHV.items():
        cache = TMP / "tlc" / f"socrata_fhv_{y}.parquet"
        if cache.exists():
            frames.append(pd.read_parquet(cache))
            continue
        # one whole-year aggregation (~2-4 min server-side); 7-day chunks were slower overall
        df = soql(D, ds, select=f"{loc} as zone, date_extract_dow({tcol}) as dow, "
                  f"date_extract_hh({tcol}) as hour, count(*) as n",
                  where=f"{loc} is not null", group=f"{loc}, dow, hour", page=100_000)
        parts = [df]
        df = pd.concat(parts, ignore_index=True).apply(pd.to_numeric)
        df = df.groupby(["zone", "dow", "hour"], as_index=False).n.sum()
        df["year"] = y
        cache.parent.mkdir(exist_ok=True)
        df.to_parquet(cache, index=False)
        print(f"  FHV {y}: {df.n.sum() / 1e6:.1f}M pickups with a zone", flush=True)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def zones():
    import geopandas as gpd
    from shapely import wkt
    z = soql(D, "8meu-9t5y", select="locationid, zone, borough, the_geom")
    return gpd.GeoDataFrame(z[["locationid", "zone", "borough"]].astype({"locationid": int}),
                            geometry=z.the_geom.map(wkt.loads), crs="EPSG:4326")
