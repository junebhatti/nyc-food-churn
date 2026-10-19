"""Step 2b of the merge: bodegas from USDA SNAP retailer history, added as source="snap".

Bodegas and delis are mostly licensed by NY State Ag & Markets, not DOHMH, so the inspection
data misses most of them. SNAP authorizations (convenience stores, small/medium groceries,
2005-2025) are the one continuous dated record. Rules:
- keep stores still authorized on or after 2012-01-01 that have a lot (BBL);
- merge re-authorizations of the same (fuzzily matched) name on the same lot, as for permits;
- drop stores matching a DOHMH business on the same lot by name (a deli with a food permit);
- an ended authorization counts as a closure. It can also mean a store stopped taking SNAP,
  so bodega lifespans are a lower bound (see data/notes/merge.md).

Reads/appends data/processed/businesses.parquet (run after build_businesses.py, before
build_buildings.py). Run: .venv/bin/python pipeline/build_bodegas.py
"""
from __future__ import annotations

import pandas as pd

from build_businesses import cluster_ids, compact, location_key, same_name
from build_lifespans import OUT, RAW
from gt_common import mnorm

SNAP_END = pd.Timestamp("2025-12-31")  # latest SNAP history release in data/raw/coverage
KEEP_FROM = pd.Timestamp("2012-01-01")
# SNAP's convenience-store class also covers pharmacies, dollar stores and gas stations
NOT_BODEGA = r"PHARM|\bRX\b|DRUG|CHEMIST|DUANE READE|WALGREEN|\bCVS\b|RITE AID|DOLLAR|99 CENT|GAS\b|FUEL|\bMOBIL\b|SHELL|EXXON|SUNOCO|\bBP\b|CITGO|SPEEDWAY|VAPE|SMOKE"


def snap_stores() -> pd.DataFrame:
    s = pd.read_parquet(RAW / "coverage" / "snap_retailers_nyc.parquet")
    s = s[(s["category"] == "bodega_deli") & s["bbl"].notna()
          & ~s["name"].fillna("").str.upper().str.contains(NOT_BODEGA)].copy()
    s["open_date"] = pd.to_datetime(s["start_date"])
    s["end_raw"] = pd.to_datetime(s["end_date"])
    s = s[s["open_date"].notna() & (s["end_raw"].isna() | (s["end_raw"] >= KEEP_FROM))]
    s["end_date"] = s["end_raw"].fillna(SNAP_END)
    s["name_key"] = s["name"].fillna("").map(mnorm)
    s["addr_key"] = s["address"].fillna("").map(mnorm)
    s["camis"] = "SNAP" + s["source_id"].astype(str)
    s["loc_key"] = location_key(s)
    return s


def drop_permitted(s: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Remove stores whose lot already holds a DOHMH business with a matching name."""
    d = b[b["source"] == "dohmh"][["loc_key", "dba"]].dropna()
    d["cname"] = d["dba"].map(compact)
    by_lot = d.groupby("loc_key")["cname"].agg(list)
    names = s["name_key"].map(compact)
    lots = s["loc_key"].map(by_lot)
    dup = [isinstance(ls, list) and any(same_name(n, x) for x in ls) for n, ls in zip(names, lots)]
    return s[~pd.Series(dup, index=s.index)]


def main() -> None:
    b = pd.read_parquet(OUT / "businesses.parquet")
    b = b[b["source"] != "snap"]  # idempotent rerun
    s = snap_stores()
    n0 = len(s)
    s = drop_permitted(s, b).sort_values("open_date")
    s["business_id"] = "B" + cluster_ids(s).str[1:]
    g = s.groupby("business_id")
    last = s.loc[g["end_date"].idxmax()].set_index("business_id")
    out = pd.DataFrame({"open_date": g["open_date"].min(), "end_date": g["end_date"].max(),
                        "n_permits": g.size(), "camis_list": g["camis"].agg(list)})
    for col in ["name", "address", "zip", "bbl", "bin", "lat", "lon", "nta2020", "loc_key"]:
        out[col] = last[col]
    out["closed"] = g["end_raw"].apply(lambda e: e.notna().all())
    out["close_date"] = out["end_date"].where(out["closed"])
    out = out.reset_index().rename(columns={"name": "dba", "address": "street"})
    out["lifespan_days"] = (out["end_date"] - out["open_date"]).dt.days
    lots = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet", columns=["bbl", "ct2020"])
    lots["bbl"] = lots["bbl"].astype(str).str.replace(r"\.0$", "", regex=True)
    out["bbl"] = out["bbl"].astype(str).str.replace(r"\.0$", "", regex=True)
    out = out.merge(lots.drop_duplicates("bbl"), on="bbl", how="left")
    out["boro"] = out["bbl"].astype(str).str[0].map(
        {"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN", "4": "QUEENS", "5": "STATEN ISLAND"})
    out["source"], out["category"] = "snap", "bodega"
    out["left_censored"] = False  # SNAP dates are real authorization dates back to the 1930s
    out["relocated"] = out["relocated_from"] = out["has_bar_licence"] = False
    pd.concat([b, out], ignore_index=True).to_parquet(OUT / "businesses.parquet", index=False)
    print(f"SNAP bodega authorizations {n0:,} -> {len(s):,} after dropping DOHMH-permitted delis -> "
          f"{len(out):,} bodegas ({out['closed'].mean():.0%} ended)")


if __name__ == "__main__":
    main()
