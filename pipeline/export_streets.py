"""Export street lines for the zoomed-in map (web/public/data/streets.json).

Source: NYC Street Centerline (CSCL), NYC Open Data inkn-q76z, fetched once and cached in
data/raw/gov/street_centerline.geojson.gz. Kept: built streets (rw_type 1 = street, status 2 =
constructed); highways, ramps, bridges, paths and driveways are left out. Streets at least
MAJOR_WIDTH_FT wide (avenues, boulevards) are drawn heavier than side streets.

Output: {"major": [[lon, lat, lon, lat, ...], ...], "minor": [...]}, one flat coordinate list per
segment, rounded to 5 decimals (about a metre). Names stay in the raw cache, not the site.
Run: .venv/bin/python pipeline/export_streets.py
"""
from __future__ import annotations

import gzip

import geopandas as gpd
import requests

from build_lifespans import RAW
from export_site import write

URL = ("https://data.cityofnewyork.us/resource/inkn-q76z.geojson"
       "?$select=the_geom,rw_type,status,streetwidth,full_street_name"
       "&$where=rw_type='1' AND status='2'&$limit=200000")
CACHE = RAW / "gov" / "street_centerline.geojson.gz"
MAJOR_WIDTH_FT = 60
SIMPLIFY_DEG = 0.00002  # about 2 m; most segments are already straight block lengths


def fetch() -> gpd.GeoDataFrame:
    if not CACHE.exists():
        r = requests.get(URL, timeout=600)
        r.raise_for_status()
        CACHE.write_bytes(gzip.compress(r.content))
    g = gpd.read_file(f"/vsigzip/{CACHE}")
    if len(g) < 80_000:  # about 99k constructed streets citywide; fewer means a truncated download
        raise RuntimeError(f"Street centerline has only {len(g)} rows; delete {CACHE} and refetch")
    return g


def paths(g: gpd.GeoDataFrame) -> list[list[float]]:
    out = []
    for geom in g.geometry.simplify(SIMPLIFY_DEG):
        lines = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for line in lines:
            out.append([round(v, 5) for xy in line.coords for v in xy[:2]])
    return out


def main() -> None:
    g = fetch()
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    width = g["streetwidth"].astype(float).fillna(0)
    major = g[width >= MAJOR_WIDTH_FT]
    minor = g[width < MAJOR_WIDTH_FT]
    print(f"  streets: {len(major)} major + {len(minor)} minor segments")
    write("streets.json", {"major": paths(major), "minor": paths(minor)})


if __name__ == "__main__":
    main()
