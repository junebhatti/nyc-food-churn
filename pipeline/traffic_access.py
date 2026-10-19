"""Point-level access to activity sources (subway stations, Citi Bike docks): the building helper.

    from traffic_access import station_access
    station_access([40.7580], [-73.9855], year=2019)
    # -> nearest_complex_id, nearest_station, nearest_m, nearest_entries, subway_entries_w400

Kernel used everywhere in this project ("distance-weighted entries within 400 m"):
    w(d) = max(0, 1 - d / 400 m)      (linear decay: full weight at the door, 0 at 400 m)
    access = sum_s entries_s * w(d_s)
Distances are planar in NY State Plane (EPSG:2263) converted to metres.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

from traffic_common import OUT

RADIUS_M = 400.0
_TR = Transformer.from_crs(4326, 2263, always_xy=True)


def xy_m(lat, lon) -> np.ndarray:
    x, y = _TR.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.c_[x, y] * 0.3048


def kernel_pairs(P: np.ndarray, S: np.ndarray, radius: float = RADIUS_M):
    """(i_point, j_source, weight) for all point-source pairs closer than radius."""
    m = cKDTree(P).sparse_distance_matrix(cKDTree(S), radius, output_type="coo_matrix")
    return m.row, m.col, np.clip(1 - m.data / radius, 0, None)


def kernel_sum(P: np.ndarray, S: np.ndarray, values: np.ndarray, radius: float = RADIUS_M):
    i, j, w = kernel_pairs(P, S, radius)
    return np.bincount(i, weights=w * values[j], minlength=len(P))


def station_access(lat, lon, year: int | None = None, stations: pd.DataFrame | None = None):
    """Nearest subway complex (distance, its entries in `year`) and 400 m kernel access.

    year=None uses each station's mean annual entries over 2017-2019 (pre-COVID baseline).
    """
    st = stations if stations is not None else pd.read_parquet(OUT / "subway_station_year.parquet")
    if year is None:
        v = st[st.year.between(2017, 2019)].groupby("complex_id").entries.mean()
    else:
        v = st[st.year == year].set_index("complex_id").entries
    loc = st.drop_duplicates("complex_id").set_index("complex_id")[["station", "lat", "lon"]]
    loc = loc.loc[loc.index.intersection(v.index)]
    vals = v.reindex(loc.index).fillna(0).to_numpy()
    P, S = xy_m(lat, lon), xy_m(loc.lat, loc.lon)
    d, k = cKDTree(S).query(P)
    return pd.DataFrame({
        "nearest_complex_id": loc.index[k], "nearest_station": loc.station.to_numpy()[k],
        "nearest_m": d, "nearest_entries": vals[k],
        "subway_entries_w400": kernel_sum(P, S, vals)})
