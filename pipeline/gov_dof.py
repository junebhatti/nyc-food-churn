"""DOF property assessment (market value) for commercial / mixed-use lots: a rent proxy back to
FY2010/11. Class 4 lots are valued by income capitalisation, so market value per sq ft tracks
net commercial rent. Subset: tax class 4 or building class K* (stores) / S* (mixed res+store).

- yjxr-fw8i  FY2010/11 .. FY2018/19 (fullval = DOF market value)
- 8y4t-faws  FY2023 .. FY2027 (period 3 = final roll; finmkttot = final market value)
FY2019/20 - FY2022 are not on the open data portal (gap).
"""
from __future__ import annotations

import pandas as pd

from gov_common import save, socrata

NYC = "data.cityofnewyork.us"
COMM = "(taxclass='4' or starts_with(bldgcl,'K') or starts_with(bldgcl,'S'))"
COMM_NEW = "(curtaxclass='4' or starts_with(bldg_class,'K') or starts_with(bldg_class,'S'))"


def run():
    print("== DOF assessment (rent proxy)")
    old = socrata(NYC, "yjxr-fw8i", where=COMM, select=(
        "bble,year,taxclass,bldgcl,fullval,avtot,ltfront,ltdepth,stories,bldfront,blddepth,"
        "staddr,zip,latitude,longitude,census_tract,nta"))
    old["fy"] = old["year"].str[:4].astype(int) + 1  # '2010/11' -> FY2011
    old = old.rename(columns={"bble": "bbl", "bldgcl": "bldg_class", "fullval": "market_value",
                              "avtot": "assessed_value"})
    new = socrata(NYC, "8y4t-faws", where=f"period='3' and {COMM_NEW}", select=(
        "parid,year,curtaxclass,bldg_class,finmkttot,fintxbtot,gross_sqft,retail_area_gross,"
        "office_area_gross,housenum_lo,street_name,zip_code,bld_story"))
    new["fy"] = new["year"].astype(int)
    new = new.rename(columns={"parid": "bbl", "curtaxclass": "taxclass",
                              "finmkttot": "market_value", "fintxbtot": "taxable_value",
                              "zip_code": "zip"})
    new["staddr"] = (new.pop("housenum_lo").fillna("") + " " + new.pop("street_name").fillna("")).str.strip()
    df = pd.concat([old.drop(columns="year"), new.drop(columns="year")], ignore_index=True)
    # 8y4t parid can carry an easement suffix; keep the 10-digit BBL
    df["bbl"] = df["bbl"].str[:10]
    for c in ("market_value", "assessed_value", "taxable_value", "gross_sqft",
              "retail_area_gross", "office_area_gross", "latitude", "longitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    save(df, "dof_commercial_values", source=NYC, dataset_id="yjxr-fw8i+8y4t-faws",
         note="Commercial/mixed-use lots market value by fiscal year (FY2011-2019, FY2023-2027).")


if __name__ == "__main__":
    run()
