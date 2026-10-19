"""Readiness table: per planned analysis and variable, share of CAMIS (or CAMIS-years / NTA-years)
with a value. Reads analysis_inputs outputs plus other areas' finished files (read-only).

Output: readiness_coverage.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai_common import OUT, RAW, write_out


def pct(x) -> float:
    return round(100 * float(np.mean(x)), 1)


def build():
    b = pd.read_parquet(OUT / "camis_base.parquet")
    b = b[~b["synthetic_camis"]].reset_index(drop=True)
    n = len(b)
    rows = []

    def add(analysis, var, cov, denom, source, note=""):
        rows.append({"analysis": analysis, "variable": var, "coverage_pct": cov, "denominator": denom,
                     "source": source, "note": note})

    J = lambda name, cols=None: b[["camis"]].merge(pd.read_parquet(OUT / f"{name}.parquet", columns=cols),
                                                  on="camis", how="left")
    alln = f"all CAMIS (n={n:,})"
    add("all", "survival outcome (closed / last seen)", pct(b["last_snap"].notna()), alln, "dohmh union")
    add("all", "opening date (first inspection)", pct(b["first_insp"].notna()), alln, "dohmh union",
        f"{pct(b['left_censored'])}% left-censored (first insp < 2011-07)")
    add("all", "BBL / NTA", pct(b["nta2020"].notna()), alln, "dohmh + PAD geocoder")

    cu = J("camis_cuisine", ["camis", "family"])
    add("A", "cuisine family (~22)", pct(cu["family"].notna() & cu["family"].ne("other_unknown")), alln,
        "camis_cuisine", f"any value incl. Other: {pct(cu['family'].notna())}%")
    pt = b[["camis"]].merge(pd.read_parquet(RAW / "menus" / "camis_price_tier.parquet",
                                            columns=["camis", "tier", "tier_source"]), on="camis", how="left")
    add("A", "price tier (any source)", pct(pt["tier"].notna()), alln, "menus/camis_price_tier (other agent)",
        "; ".join(f"{k}:{pct(pt['tier_source'].eq(k))}%" for k in pt["tier_source"].dropna().unique()))
    add("A", "price tier, observed (not proxy)", pct(pt["tier"].notna() & pt["tier_source"].ne("proxy")), alln,
        "menus + google price + michelin")
    ch = J("camis_chain", ["camis", "is_chain_strict", "brand_key"])
    add("A", "chain vs independent", pct(ch["brand_key"].notna()), alln, "camis_chain",
        f"strict chain share {pct(ch['is_chain_strict'].fillna(False).astype(bool))}%")
    op = J("camis_operator", ["camis", "has_entity_link", "has_local_brand", "first_time_operator"])
    add("A", "legal entity link", pct(op["has_entity_link"]), alln, "SLA/OR/PPP/RRF/DiningOut/DCWP")
    add("A", "first-time vs multi-unit operator", pct(op["first_time_operator"].notna()), alln,
        "camis_operator", "defined where entity or local-brand link exists")
    sh = J("camis_storefront_history", ["camis", "n_prior_tenants", "prev_camis", "reg_years_before_open"])
    add("A", "prior tenants at address (count)", pct(sh["n_prior_tenants"].notna()), alln, "dohmh succession",
        "left-truncated ~2011")
    add("A", "predecessor lifespan + gap (vacancy proxy)", pct(sh["prev_camis"].notna()), alln, "dohmh succession")
    op20 = b["first_insp"] >= "2020-01-01"
    add("A", "LL157 vacancy before opening", pct(sh.loc[op20, "reg_years_before_open"].notna()),
        f"CAMIS opened 2020+ (n={op20.sum():,})", "storefront registry")
    ag = J("camis_age", ["camis", "earlier_bound_found"])
    lc = b["left_censored"]
    add("A", "age (Lindy): exact opening", pct(~lc & b["first_insp"].notna()), alln, "dohmh")
    add("A", "age: earlier-start bound for left-censored", pct(ag.loc[lc, "earlier_bound_found"]),
        f"left-censored CAMIS (n={lc.sum():,})", "SLA/DOS/Google")
    sz = J("camis_size", ["camis", "pluto_retailarea", "or_sidewalk_sqft", "or_roadway_sqft",
                          "retail_area_per_storefront"])
    add("A/B", "building retail area (PLUTO)", pct(sz["pluto_retailarea"].notna()), alln, "PLUTO (current)")
    add("A/B", "retail area per storefront", pct(sz["retail_area_per_storefront"].notna()), alln, "PLUTO / LL157")
    alive2021 = (b["first_insp"] < "2021-06-01") & (b["last_snap"] >= "2021-05-29")
    orx = sz[["or_sidewalk_sqft", "or_roadway_sqft"]].notna().any(axis=1)
    add("A/B", "outdoor seating area (Open Restaurants)", pct(orx[alive2021]),
        f"CAMIS alive mid-2021 (n={alive2021.sum():,})", "open_restaurants_apps")

    nr = pd.read_parquet(OUT / "nta_year_rent.parquet")
    years = range(2011, 2026)
    grid = pd.MultiIndex.from_product([b["nta2020"].dropna().unique(), years], names=["nta2020", "year"])
    g = pd.DataFrame(index=grid).reset_index().merge(nr, on=["nta2020", "year"], how="left")
    add("B", "NTA rent: LL157 $/sqft (2019-24)", pct(g.loc[g.year.between(2019, 2024), "ll157_rent_psf_yr"].notna()),
        "NTA-years 2019-24 with CAMIS", "LL157 dxru-eun8")
    add("B", "NTA rent proxy: DOF MV/sqft", pct(g["dof_mv_psf_median"].notna()), "NTA-years 2011-25",
        "DOF + PLUTO", "gap 2019-2021 (FY2020-22 unpublished)")
    add("B", "NTA rent: either measure", pct(g[["ll157_rent_psf_yr", "dof_mv_psf_median"]].notna().any(axis=1)),
        "NTA-years 2011-25", "")
    cr = pd.read_csv(OUT / "rent" / "outer_borough_corridor_rents.csv")
    rb = pd.read_csv(RAW / "gov" / "rebny_manhattan_corridor_rents.csv")
    add("B", "corridor asking rents", np.nan, "corridors", "REBNY",
        f"Manhattan {rb['corridor'].nunique()} corridors 2010-25; Brooklyn {cr['corridor'].nunique()} corridors "
        f"2015-25; none Queens/Bronx/SI")

    # C: foot traffic covariates (other agent; partial)
    tract = b["bct2020"].astype("string") if "bct2020" in b else None
    lodes = pd.read_parquet(RAW / "traffic" / "lodes_wac_tract_year.parquet", columns=["geoid"])
    cty = {"1": "061", "2": "005", "3": "047", "4": "081", "5": "085"}
    geoid = ["36" + cty[c[0]] + c[1:] if isinstance(c, str) and len(c) == 7 and c[0] in cty else None
             for c in b["ct2020"].astype("string").radd(b["bbl"].astype("string").str[0].fillna(""))]
    add("C", "tract jobs (LODES)", pct(pd.Series(geoid).isin(set(lodes["geoid"].astype(str)))), alln,
        "traffic/lodes (other agent)")
    st = pd.read_parquet(RAW / "traffic" / "subway_station_year.parquet", columns=["complex_id", "lat", "lon"])
    st = st.dropna().drop_duplicates("complex_id")
    lat = b["lat"].fillna(b["lot_lat"]).to_numpy(float)
    lon = b["lon"].fillna(b["lot_lon"]).to_numpy(float)
    ok = ~np.isnan(lat)
    dmin = np.full(n, np.nan)
    for i in range(0, n, 5000):
        la, lo = lat[i:i + 5000, None], lon[i:i + 5000, None]
        dy = (la - st["lat"].to_numpy()[None]) * 111_000
        dx = (lo - st["lon"].to_numpy()[None]) * 84_000
        dmin[i:i + 5000] = np.sqrt(dx ** 2 + dy ** 2).min(axis=1)
    add("C", "subway ridership within 800 m", pct(ok & (dmin <= 800)), alln, "traffic/subway (other agent)",
        "coordinate available: " + str(pct(ok)) + "%")

    rr = pd.read_parquet(OUT / "camis_rrf_design.parquet")
    rs = rr["alive_at_window"] & ~rr["rrf_ineligible_chain"]
    add("D", "RRF recipient flag", pct(rr.loc[rs, "rrf_recipient"]), f"risk set alive 2021-05 (n={rs.sum():,})",
        "SBA RRF recipients", "share treated; 3,329 of 5,553 NYC recipients linked")
    add("D", "unfunded-applicant flag", 0.0, "risk set", "none public", "proxy: PPP 2nd draw non-recipients")
    add("D", "PPP applicant proxy", pct(rr.loc[rs, ["ppp_first_draw", "ppp_second_draw"]].any(axis=1)), "risk set",
        "SBA PPP")

    acc = set()
    for f in ("michelin_nyc", "nyt_reviews", "eater_lists", "awards_nyc"):
        acc |= set(pd.read_parquet(RAW / "ratings" / f"{f}.parquet", columns=["camis"])["camis"].dropna().astype(str))
    add("E", "critic acclaim (Michelin/NYT/Eater/JBF/50Best)", pct(b["camis"].astype(str).isin(acc)), alln,
        "ratings", f"{len(acc & set(b['camis'].astype(str))):,} acclaimed CAMIS; the rest are 'not acclaimed'")
    gl = set(pd.read_parquet(RAW / "ratings" / "google_local_nyc.parquet", columns=["camis"])["camis"].dropna().astype(str))
    add("E", "Google rating (2021 crawl)", pct(b["camis"].astype(str).isin(gl)), alln, "UCSD Google Local")
    out = pd.DataFrame(rows)
    write_out(out, "readiness_coverage", "analysis_inputs + other areas", "coverage % per variable", fmt="csv")
    print(out.to_string())


if __name__ == "__main__":
    build()
