"""Step 1 of the merge: one row per DOHMH permit (CAMIS) with an estimated life window.

Window terms (see gt_dohmh.py, data/notes/groundtruth.md):
    F = first real inspection, L = last real inspection,
    first_seen = first copy listing the CAMIS at all,
    U = first FULL copy after the last listing (NaT = still listed, i.e. open / right-censored).
Corrections from the ground-truth check:
    opening = min(first_seen, F)                       (first listing beats first inspection)
    L is raised by later named proof of life (PPP, RRF, Open Restaurants, research check-ins)
    when it falls before U. 311 is skipped: about 30% of its matches are another business.
    closure = L + k * (U - L), k = 0.30 when U falls in 2016-2018 and 0.37 otherwise.
Ages: permits already listed in the first copy (left-censored) get the earliest independent
evidence (OATH tickets, liquor licence, DOS formation, first Google review) as `known_open_by`.

Writes data/processed/permits.parquet. Run: .venv/bin/python pipeline/build_lifespans.py
"""
from __future__ import annotations

import pandas as pd

import gt_dohmh
from gt_common import RAW

ROOT = RAW.parent.parent
OUT = ROOT / "data" / "processed"
AI = RAW / "analysis_inputs"
NAMED_SIGNALS = {"sba_ppp", "sba_rrf", "open_restaurants_insp"}
RPOI_LATER = {"later than last snapshot", "after last inspection only"}
FIRST_REAL = pd.Timestamp("2005-01-01")  # copies start 2012-07 and hold ~3 years back


def proof_of_life() -> pd.Series:
    """Latest named evidence a permit was operating, per CAMIS."""
    s = pd.read_parquet(RAW / "signals" / "closure_tightening.parquet",
                        columns=["camis", "new_last_seen", "source"])
    s = s[s["source"].isin(NAMED_SIGNALS)].rename(columns={"new_last_seen": "seen"})
    r = pd.read_parquet(RAW / "research_poi" / "rpoi_closure_evidence.parquet",
                        columns=["camis", "r_last", "verdict"])
    r = r[r["verdict"].isin(RPOI_LATER)].rename(columns={"r_last": "seen"})
    both = pd.concat([s[["camis", "seen"]], r[["camis", "seen"]]])
    both["camis"] = both["camis"].astype(str)
    both["seen"] = pd.to_datetime(both["seen"])
    return both.groupby("camis")["seen"].max()


def real_inspections() -> pd.DataFrame:
    """F/L per CAMIS, ignoring placeholder dates (1900-01-01, and 2000-01-01 in one old copy)."""
    u = pd.read_parquet(RAW / "dohmh" / "union_inspections.parquet", columns=["camis", "inspection_date"])
    u["inspection_date"] = pd.to_datetime(u["inspection_date"])
    u = u[u["inspection_date"] >= FIRST_REAL]
    out = u.groupby("camis")["inspection_date"].agg(F="min", L="max").reset_index()
    out["camis"] = out["camis"].astype(str)
    return out


def build() -> pd.DataFrame:
    c = gt_dohmh.camis_table()
    live = c.attrs["latest_snapshot"]
    c["camis"] = c["camis"].astype(str)
    c = c.drop(columns=["F", "L"]).merge(real_inspections(), on="camis", how="left")

    pol = proof_of_life().reindex(c["camis"]).values
    c["proof_of_life"] = pol
    usable = c["proof_of_life"].notna() & (c["proof_of_life"] > c["L"]) & (
        c["U"].isna() | (c["proof_of_life"] < c["U"]))
    c["L_adj"] = c["L"].where(~usable, c["proof_of_life"])
    c["L_raised"] = usable

    c["open_date"] = c[["first_seen", "F"]].min(axis=1)
    c["closed"] = c["U"].notna()
    k = c["U"].dt.year.between(2016, 2018).map({True: 0.30, False: 0.37})
    base = c["L_adj"].fillna(c["first_seen"])  # never inspected: listed, then gone
    c["close_date"] = (base + (c["U"] - base) * k).where(c["closed"])
    c["close_lo"], c["close_hi"] = base.where(c["closed"]), c["U"]
    c["end_date"] = c["close_date"].fillna(live)
    c["lifespan_days"] = (c["end_date"] - c["open_date"]).dt.days

    age = pd.read_parquet(AI / "camis_age.parquet",
                          columns=["camis", "left_censored", "earliest_evidence"])
    age["camis"] = age["camis"].astype(str)
    c = c.merge(age, on="camis", how="left")
    c["left_censored"] = c["left_censored"].fillna(False).astype(bool)
    c["known_open_by"] = c[["earliest_evidence", "open_date"]].min(axis=1)

    geo = pd.read_parquet(AI / "camis_base.parquet",
                          columns=["camis", "bbl", "bin", "lat", "lon", "nta2020", "ct2020",
                                   "geo_src", "synthetic_camis", "dba_key", "lot_lat", "lot_lon"])
    geo["camis"] = geo["camis"].astype(str)
    # Pre-2019 copies carry no coordinates; fall back to the lot centroid of the geocoded BBL.
    for a in ("lat", "lon"):
        geo[a] = pd.to_numeric(geo[a], errors="coerce").fillna(pd.to_numeric(geo[f"lot_{a}"], errors="coerce"))
    geo = geo.drop(columns=["lot_lat", "lot_lon"])
    c = c.drop(columns=["bbl", "lat", "lon"]).merge(geo, on="camis", how="left")
    c.attrs["latest_snapshot"] = live
    return c


def main() -> None:
    c = build()
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["camis", "dba", "dba_first", "name_key", "dba_key", "boro", "building", "street", "zip",
            "addr_key", "bbl", "bin", "lat", "lon", "nta2020", "ct2020", "geo_src", "synthetic_camis",
            "first_seen", "F", "L", "L_adj", "L_raised", "proof_of_life", "last_snap", "U",
            "open_date", "closed", "close_date", "close_lo", "close_hi", "end_date", "lifespan_days",
            "left_censored", "known_open_by"]
    out = c[cols].copy()
    out.attrs = {}  # pandas would try to JSON-encode the Timestamp in attrs
    out.to_parquet(OUT / "permits.parquet", index=False)
    print(f"permits: {len(c):,}  closed {c['closed'].mean():.1%}  L raised {c['L_raised'].sum():,}  "
          f"left-censored {c['left_censored'].mean():.1%}  no coords {c['lat'].isna().mean():.1%}  "
          f"latest copy {c.attrs['latest_snapshot'].date()}")


if __name__ == "__main__":
    main()
