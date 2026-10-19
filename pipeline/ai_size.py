"""Restaurant size / capacity proxies per CAMIS.

- Open Restaurants applications (2020-23): approved sidewalk / roadway seating area (sq ft),
  linked by BBL + name similarity (>= 0.8) to a CAMIS alive at submission.
- Historical DCWP sidewalk cafe licences: tables, chairs, sq ft (324 rows; same linking).
- PLUTO lot: lot area, building area, commercial and retail floor area, floors, year built,
  building class; retail_area_per_storefront = retailarea / LL157 storefronts at the BBL.
- DOB BIS Place-of-Assembly (job type PA) filed at the BBL: an assembly space of 75+ people.
There is no public per-restaurant indoor seat count.

Output: camis_size.parquet
"""
from __future__ import annotations

import pandas as pd

from ai_common import OUT, RAW, norm_name, write_out
from ai_operators import sim


def link_by_bbl_name(rec: pd.DataFrame, base: pd.DataFrame, date_col: str) -> pd.DataFrame:
    b = base.dropna(subset=["bbl"])
    m = rec.merge(b[["camis", "bbl", "dba_key", "first_insp", "first_snap", "last_insp", "last_snap"]], on="bbl")
    lo = m["first_insp"].fillna(m["first_snap"]) - pd.Timedelta(days=365)
    hi = m[["last_insp", "last_snap"]].max(axis=1) + pd.Timedelta(days=365)
    m = m[(m[date_col] >= lo) & (m[date_col] <= hi)].copy()
    m["s"] = [sim(a, c) for a, c in zip(m["name_key"], m["dba_key"])]
    m = m[m["s"] >= 0.8].sort_values("s", ascending=False)
    return m.drop_duplicates("rid")


def build():
    from signals_common import norm_bbl
    base = pd.read_parquet(OUT / "camis_base.parquet")
    ora = pd.read_parquet(RAW / "gov" / "open_restaurants_apps.parquet",
                          columns=["restaurant_name", "doing_business_as_dba", "bbl", "time_of_submission",
                                   "sidewalk_dimensions_area", "roadway_dimensions_area",
                                   "approved_for_sidewalk_seating", "approved_for_roadway_seating"])
    ora["rid"] = range(len(ora))
    ora["bbl"] = norm_bbl(ora["bbl"])
    ora["date"] = pd.to_datetime(ora["time_of_submission"], errors="coerce")
    ora["name_key"] = ora["restaurant_name"].map(norm_name)
    m = link_by_bbl_name(ora, base, "date")
    for c in ("sidewalk_dimensions_area", "roadway_dimensions_area"):
        m[c] = pd.to_numeric(m[c], errors="coerce")
    o = m.groupby("camis").agg(or_sidewalk_sqft=("sidewalk_dimensions_area", "max"),
                               or_roadway_sqft=("roadway_dimensions_area", "max"),
                               or_n_apps=("rid", "nunique")).reset_index()

    sw = pd.read_parquet(RAW / "gov" / "sidewalk_cafe_hist.parquet")
    sw = sw.assign(rid=range(len(sw)), name_key=sw["business_name2"].fillna(sw["business_name"]).map(norm_name),
                   date=pd.to_datetime(sw["submit_date"], errors="coerce"))
    # sidewalk_cafe_hist has no BBL; match on house + street instead
    from ai_common import norm_addr
    sw["addr"] = [norm_addr(b, s) for b, s in zip(sw["building"], sw["street"])]
    bb = base.assign(addr=base["addr_key"].str.split("|").str[1])
    sm = sw.merge(bb[["camis", "addr", "dba_key"]], on="addr")
    sm["s"] = [sim(a, c) for a, c in zip(sm["name_key"], sm["dba_key"])]
    sm = sm[sm["s"] >= 0.8].sort_values("s", ascending=False).drop_duplicates("rid")
    swa = sm.groupby("camis").agg(swc_tables=("swc_tables", "max"), swc_chairs=("swc_chairs", "max"),
                                  swc_sqft=("swc_sq_ft", "max")).reset_index()

    p = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet",
                        columns=["bbl", "lotarea", "bldgarea", "comarea", "retailarea", "numfloors", "yearbuilt",
                                 "bldgclass", "unitstotal"])
    p["bbl"] = norm_bbl(p["bbl"])
    p = p.dropna(subset=["bbl"]).drop_duplicates("bbl").add_prefix("pluto_").rename(columns={"pluto_bbl": "bbl"})
    reg = pd.read_parquet(RAW / "gov" / "storefronts_registry.parquet", columns=["bbl", "reporting_year"])
    reg["bbl"] = norm_bbl(reg["bbl"])
    nsf = reg.groupby(["bbl", "reporting_year"]).size().groupby("bbl").max().rename("ll157_storefronts_at_bbl")

    dob = pd.read_parquet(RAW / "signals" / "dob_bis_food.parquet", columns=["bbl", "job_type", "event_date"])
    pa = dob[dob["job_type"].eq("PA")]
    pa_bbl = set(norm_bbl(pa["bbl"]).dropna())

    out = base[["camis", "bbl"]].merge(o, on="camis", how="left").merge(swa, on="camis", how="left")
    out = out.merge(p, on="bbl", how="left").merge(nsf, left_on="bbl", right_index=True, how="left")
    ra = pd.to_numeric(out["pluto_retailarea"], errors="coerce")
    out["retail_area_per_storefront"] = (ra / out["ll157_storefronts_at_bbl"]).where(ra > 0)
    out["dob_place_of_assembly_at_bbl"] = out["bbl"].isin(pa_bbl)
    write_out(out.drop(columns="bbl"), "camis_size", "gov/open_restaurants_apps, gov/sidewalk_cafe_hist, PLUTO, "
              "LL157 registry, signals/dob_bis_food", "size proxies; no indoor seat counts exist publicly")


if __name__ == "__main__":
    build()
