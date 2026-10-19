"""Storefront rent panels by tract and NTA (2020 NTAs), all boroughs.

1. LL157 storefront registry stats (dxru-eun8, class 2/4 storefronts): tract median monthly
   asking-free *contract* rent $/sq ft, 2019-2024. Annualised (x12) here. NTA value = mean of tract
   medians weighted by leased storefronts (a median of medians: rough).
2. DOF market value per sq ft of commercial floor area, retail-bearing lots (PLUTO retailarea > 0),
   tax class 4 (valued by the income approach, so MV/sqft tracks capitalised net rent).
   FY2011-2019 and FY2023-2027 (FY2020-22 not published). Denominator is the CURRENT PLUTO comarea,
   so lots rebuilt during the period are noisy; the NTA median damps this.
   Fiscal year FY t is valued as of Jan 5 of t-1, so year = fy - 1.
3. REBNY Manhattan corridor asking rents are kept as-is in gov/; outer-borough corridor rents (if
   found) are in rent/.

Outputs: tract_year_rent.parquet, nta_year_rent.parquet
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai_common import RAW, log, write_out


def ll157_tract() -> pd.DataFrame:
    s = pd.read_parquet(RAW / "gov" / "storefront_stats_class24.parquet")
    s = s[s["aggregate_level_citywide"].str.upper() == "CENSUS TRACT"].copy()
    parts = s["aggregate_level_id"].str.extract(r"^(\d)\.(\d{4})\.(\d{2})$")
    s["boroct2020"] = (parts[0] + parts[1] + parts[2]).where(parts[0].notna(),
                                                             s["aggregate_level_id"].where(
                                                                 s["aggregate_level_id"].str.fullmatch(r"\d{7}")))
    bad = s["boroct2020"].isna()
    if bad.any():
        log.warning("LL157 tract ids not parsed: %d e.g. %s", bad.sum(), s.loc[bad, "aggregate_level_id"].head(3).tolist())
    s["year"] = s["reporting_year"].astype(int)
    out = pd.DataFrame({
        "boroct2020": s["boroct2020"], "year": s["year"],
        "ll157_median_rent_psf_yr": pd.to_numeric(s["median_monthly_rent_per_square"], errors="coerce") * 12,
        "ll157_mean_rent_psf_yr": pd.to_numeric(s["average_monthly_rent_per"], errors="coerce") * 12,
        "ll157_n_leased": pd.to_numeric(s["storefront_leased_to_tenants"], errors="coerce"),
        "ll157_n_storefronts": pd.to_numeric(s["total_storefronts"], errors="coerce"),
        "ll157_n_not_leased": pd.to_numeric(s["storefront_reported_not_leased"], errors="coerce"),
        "ll157_median_sqft": pd.to_numeric(s["median_square_feet"], errors="coerce"),
    }).dropna(subset=["boroct2020"])
    out["ll157_vacancy_rate"] = out["ll157_n_not_leased"] / out["ll157_n_storefronts"]
    return out


def dof_lots() -> pd.DataFrame:
    from signals_common import norm_bbl
    d = pd.read_parquet(RAW / "gov" / "dof_commercial_values.parquet",
                        columns=["bbl", "taxclass", "market_value", "fy"])
    d = d[d["taxclass"].astype(str).eq("4")]
    d["bbl"] = norm_bbl(d["bbl"])
    p = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet",
                        columns=["bbl", "comarea", "retailarea", "bct2020", "nta2020"])
    p["bbl"] = norm_bbl(p["bbl"])
    p = p[(pd.to_numeric(p["retailarea"], errors="coerce") > 0) & (pd.to_numeric(p["comarea"], errors="coerce") > 0)]
    d = d.merge(p.drop_duplicates("bbl"), on="bbl")
    d["mv_psf"] = pd.to_numeric(d["market_value"], errors="coerce") / pd.to_numeric(d["comarea"], errors="coerce")
    d = d[(d["mv_psf"] > 1) & (d["mv_psf"] < 20000)]
    d["year"] = d["fy"].astype(int) - 1
    d["boroct2020"] = d["bct2020"].astype(str).str.replace(r"\.0$", "", regex=True)
    return d


def build():
    t = ll157_tract()
    eq = pd.read_parquet(RAW / "gov" / "ct2020_nta2020_equiv.parquet", columns=["boroct2020", "ntacode"])
    d = dof_lots()
    dt = d.groupby(["boroct2020", "year"]).agg(dof_mv_psf_median=("mv_psf", "median"),
                                               dof_n_lots=("bbl", "nunique")).reset_index()
    tract = t.merge(dt, on=["boroct2020", "year"], how="outer").merge(eq, on="boroct2020", how="left")
    tract = tract.rename(columns={"ntacode": "nta2020"})
    write_out(tract, "tract_year_rent", "gov/storefront_stats_class24 (dxru-eun8) + gov/dof_commercial_values + PLUTO",
              "LL157 rent annualised $/sqft/yr (2019-2024); DOF tax-class-4 retail-lot market value $/sqft comarea "
              "(year = FY-1; 2010-2018, 2022-2026)")
    w = t.merge(eq, on="boroct2020", how="left").dropna(subset=["ll157_median_rent_psf_yr", "ntacode"])
    w["wt"] = w["ll157_n_leased"].fillna(1).clip(lower=1)
    ll = (w.assign(x=w["ll157_median_rent_psf_yr"] * w["wt"]).groupby(["ntacode", "year"])
          .agg(x=("x", "sum"), wt=("wt", "sum"), ll157_n_tracts=("boroct2020", "nunique")).reset_index())
    ll["ll157_rent_psf_yr"] = ll["x"] / ll["wt"]
    ll = ll.rename(columns={"ntacode": "nta2020", "wt": "ll157_n_leased"}).drop(columns="x")
    dn = d.groupby(["nta2020", "year"]).agg(dof_mv_psf_median=("mv_psf", "median"),
                                            dof_n_lots=("bbl", "nunique")).reset_index()
    # index each NTA's DOF series to its own 2018 level (relative change is what a proxy supports)
    base = dn[dn["year"] == 2018].set_index("nta2020")["dof_mv_psf_median"]
    dn["dof_mv_index_2018"] = dn["dof_mv_psf_median"] / dn["nta2020"].map(base)
    nta = dn.merge(ll, on=["nta2020", "year"], how="outer").sort_values(["nta2020", "year"])
    # calibration: correlation of the two measures where both exist
    both = nta.dropna(subset=["ll157_rent_psf_yr", "dof_mv_psf_median"])
    if len(both):
        r = np.corrcoef(np.log(both["ll157_rent_psf_yr"]), np.log(both["dof_mv_psf_median"]))[0, 1]
        log.info("log corr LL157 rent vs DOF MV/sqft across NTA-years (n=%d): %.2f", len(both), r)
    write_out(nta, "nta_year_rent", "tract_year_rent aggregated to NTA 2020",
              "ll157_rent_psf_yr = leased-weighted mean of tract medians; dof_mv_* = median over retail lots")


if __name__ == "__main__":
    build()
