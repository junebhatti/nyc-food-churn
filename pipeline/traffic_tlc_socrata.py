"""TLC aggregates from NYC Open Data (Socrata), used where the CloudFront parquet files are not.

  - c5iv-bn4s "Pickups and Drop-offs by Taxi Zone and Industry": monthly pickups and dropoffs per
    zone for Yellow, Green and FHV - High Volume, 2019-01 onward, every month (TLC's own counts).
  (FHV 2015-2018 used to be aggregated here from the yearly trip tables, e.g. am94-epxh, but
   Socrata's group-by takes ~70 s per week of 2018 trips and a month or more never returns,
   so traffic_tlc.py reads the CloudFront FHV parquet files instead.)
  - 8meu-9t5y: taxi zone polygons.
"""
from __future__ import annotations

import pandas as pd

from traffic_common import soql

D = "data.cityofnewyork.us"
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


def zones():
    import geopandas as gpd
    from shapely import wkt
    z = soql(D, "8meu-9t5y", select="locationid, zone, borough, the_geom")
    return gpd.GeoDataFrame(z[["locationid", "zone", "borough"]].astype({"locationid": int}),
                            geometry=z.the_geom.map(wkt.loads), crs="EPSG:4326")
