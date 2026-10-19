"""LEHD LODES8 workplace area characteristics (WAC) -> jobs per 2020 tract per year (NYC).

LODES8 is tabulated on 2020 census blocks for every year, so no tract crosswalk is needed.
Output: data/raw/traffic/lodes_wac_tract_year.parquet
  geoid (11-digit 2020 tract), year, jobs (C000), jobs_food_accom (CNS18), jobs_retail (CNS07),
  jobs_arts (CNS17).
"""
from __future__ import annotations

import io

import pandas as pd

from traffic_common import NYC_COUNTY_FIPS, get, save

BASE = "https://lehd.ces.census.gov/data/lodes/LODES8/ny/wac/ny_wac_S000_JT00_{y}.csv.gz"
YEARS = range(2010, 2024)  # 2023 is the latest published (checked 2026-10)
COLS = {"C000": "jobs", "CNS18": "jobs_food_accom", "CNS07": "jobs_retail", "CNS17": "jobs_arts"}


def run() -> pd.DataFrame:
    frames = []
    for y in YEARS:
        r = get(BASE.format(y=y))
        df = pd.read_csv(io.BytesIO(r.content), compression="gzip",
                         usecols=["w_geocode", *COLS], dtype={"w_geocode": str})
        df = df[df.w_geocode.str[2:5].isin(NYC_COUNTY_FIPS)]
        df["geoid"] = df.w_geocode.str[:11]
        t = df.groupby("geoid", as_index=False)[list(COLS)].sum().rename(columns=COLS)
        t["year"] = y
        frames.append(t)
        print(f"  LODES {y}: {len(t)} tracts, {t.jobs.sum():,} jobs", flush=True)
    out = pd.concat(frames, ignore_index=True)
    save(out, "lodes_wac_tract_year", source=BASE.format(y="{year}"),
         note="LODES8 WAC S000 JT00 (all primary+secondary jobs), summed from 2020 blocks to tracts")
    return out


if __name__ == "__main__":
    run()
