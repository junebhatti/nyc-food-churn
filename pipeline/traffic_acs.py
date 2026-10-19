"""ACS 5-year total population (B01003) by 2020 census tract, NYC, ACS years 2011-2024.

The Census API now requires a key, so this reads the bulk summary files on www2.census.gov:
  - 2011-2020: sequence-based files (B01003 is the first table of sequence 0003) + geo file.
  - 2021+:     table-based file acsdt5y{y}-b01003.dat (all US geographies, 18 MB).
Years tabulated on 2010 tracts are moved to 2020 tracts with the Census 2020<->2010 tract
relationship file, splitting each 2010 tract's population by land-area share.
ACS year y = the 5-year window ending in y (e.g. 2015 = 2011-2015).
Output: data/raw/traffic/acs_pop_tract_year.parquet (geoid, year, pop, pop_density_km2, geo_basis)
"""
from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from traffic_common import NYC_COUNTY_FIPS, get, save, tracts, METRIC_CRS

SEQ = ("https://www2.census.gov/programs-surveys/acs/summary_file/{y}/data/5_year_seq_by_state/"
       "NewYork/Tracts_Block_Groups_Only/")
TBL = ("https://www2.census.gov/programs-surveys/acs/summary_file/{y}/table-based-SF/data/"
       "5YRData/acsdt5y{y}-b01003.dat")
REL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/tract/tab20_tract20_tract10_st36.txt"
YEARS = range(2011, 2025)


def _b01003_col(y: int) -> int:
    """Position of total population in sequence 3 (it moves between years), from the year's template."""
    url = f"https://www2.census.gov/programs-surveys/acs/summary_file/{y}/data/{y}_5yr_Summary_FileTemplates.zip"
    z = zipfile.ZipFile(io.BytesIO(get(url).content))
    name = next(n for n in z.namelist() if re.search(r"seq0*3\.xlsx?$", n, re.I))
    cols = [str(c).strip() for c in pd.read_excel(io.BytesIO(z.read(name)), nrows=0).columns]
    # B01003_001 (total pop) or, where seq 3 lacks it (2019-20), B02001_001 (race universe = total pop)
    hits = [i for i, c in enumerate(cols) if c.upper() == "B01003_001"] or \
        [i for i, c in enumerate(cols) if c.upper() == "B02001_001"]
    if len(hits) != 1:
        raise RuntimeError(f"ACS {y}: B01003_001 not found uniquely in {name}: {cols[:12]}")
    return hits[0]


def _seq_year(y: int) -> pd.Series:
    base = SEQ.format(y=y)
    z = zipfile.ZipFile(io.BytesIO(get(base + f"{y}5ny0003000.zip").content))
    name = next(n for n in z.namelist() if n.lower().startswith("e"))
    est = pd.read_csv(z.open(name), header=None, dtype=str)
    col = _b01003_col(y)
    geo = pd.read_csv(io.BytesIO(get(base + f"g{y}5ny.csv").content), header=None, dtype=str,
                      encoding="latin-1")
    # geo file: col 4 = LOGRECNO; GEOID ('14000US36061000100') is the column that starts '14000US'
    gcol = next(c for c in geo.columns if geo[c].astype(str).str.startswith("14000US").any())
    geo = geo[geo[gcol].str.startswith("14000US", na=False)][[4, gcol]]
    geo.columns = ["logrecno", "geoid"]
    est = est[[5, col]].rename(columns={5: "logrecno", col: "pop"})
    m = geo.merge(est, on="logrecno")
    return m.set_index(m.geoid.str[7:])["pop"].astype(float)


def _tbl_year(y: int) -> pd.Series:
    df = pd.read_csv(io.BytesIO(get(TBL.format(y=y)).content), sep="|", dtype=str)
    df = df[df.GEO_ID.str.startswith("1400000US")]
    return df.set_index(df.GEO_ID.str[9:])["B01003_E001"].astype(float)


def run() -> pd.DataFrame:
    t = tracts().to_crs(METRIC_CRS)
    t["area_km2"] = t.geometry.area * 0.09290304 / 1e6  # ft^2 -> km^2 (incl. water inside tract)
    t20 = set(t.geoid)
    rel = pd.read_csv(io.BytesIO(get(REL).content), sep="|", dtype=str, encoding="utf-8-sig")
    rel = rel[rel.GEOID_TRACT_20.isin(t20)].copy()
    for c in ("AREALAND_PART", "AREALAND_TRACT_10"):
        rel[c] = rel[c].astype(float)
    rel["w"] = (rel.AREALAND_PART / rel.AREALAND_TRACT_10).where(rel.AREALAND_TRACT_10 > 0, 0)

    frames = []
    for y in YEARS:
        s = _seq_year(y) if y <= 2020 else _tbl_year(y)
        s = s[s.index.str[2:5].isin(NYC_COUNTY_FIPS) & s.index.str.startswith("36")]
        overlap = len(set(s.index) & t20) / len(t20)
        if overlap > 0.97:
            basis = "2020"
            df = s.rename("pop").rename_axis("geoid").reset_index()
        else:
            basis = "2010->2020 (land-area split)"
            r = rel.merge(s.rename("pop10"), left_on="GEOID_TRACT_10", right_index=True)
            r["pop"] = r.pop10 * r.w
            df = r.groupby("GEOID_TRACT_20", as_index=False)["pop"].sum().rename(
                columns={"GEOID_TRACT_20": "geoid"})
        df["year"], df["geo_basis"] = y, basis
        frames.append(df)
        print(f"  ACS {y}: NYC pop {df['pop'].sum():,.0f}, basis {basis}", flush=True)
    out = pd.concat(frames, ignore_index=True).merge(t[["geoid", "area_km2"]], on="geoid")
    out["pop_density_km2"] = out["pop"] / out.area_km2
    save(out.drop(columns="area_km2"), "acs_pop_tract_year", source=TBL.format(y="{y}"),
         note="ACS 5-yr B01003 total pop; year = end of 5-yr window; 2010 tracts split by land area")
    return out


if __name__ == "__main__":
    run()
