"""Step 4 of the merge: attach analysis variables to each business.

Per-permit inputs (data/raw/analysis_inputs/camis_*, data/raw/menus/camis_price_tier) join on the
business's latest permit. Acclaim (Michelin, NYT, Eater lists, awards) counts if ANY of the
business's permits was matched. Rent is the neighbourhood's value in the year the business
opened (storefront rent from 2019 on, DOF market value per sq ft for every year). Foot traffic
joins by tract and opening year once data/raw/traffic/traffic_by_tract_year.parquet exists.

Rewrites data/processed/businesses.parquet. Run: .venv/bin/python pipeline/build_attach.py
"""
from __future__ import annotations

import pandas as pd

from build_lifespans import AI, OUT, RAW

PERMIT_INPUTS = {
    "camis_cuisine.parquet": ["family", "cuisine_clean", "limited_service"],
    "camis_chain.parquet": ["brand_key", "is_chain_strict", "is_chain_loose", "nyc_max_concurrent"],
    "camis_operator.parquet": ["operator_id", "multi_unit_operator", "first_time_operator",
                               "operator_n_camis"],
    "camis_size.parquet": ["pluto_retailarea", "retail_area_per_storefront", "or_n_apps"],
    "camis_rrf_design.parquet": ["rrf_recipient", "rrf_amount", "ppp_first_draw", "ppp_second_draw",
                                 "alive_at_window"],
}
ACCLAIM = {"michelin": "michelin_nyc.parquet", "michelin_guide": "michelin_guide_nyc_snapshots.parquet",
           "nyt": "nyt_reviews.parquet", "eater": "eater_lists.parquet", "award": "awards_nyc.parquet"}


def read_camis(path, cols) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["camis"] + cols)
    d["camis"] = d["camis"].astype(str)
    return d.drop_duplicates("camis")


def acclaim(b: pd.DataFrame) -> pd.DataFrame:
    perm = b[["business_id", "camis_list"]].dropna().explode("camis_list")
    perm = perm.rename(columns={"camis_list": "camis"})
    perm["camis"] = perm["camis"].astype(str)
    out = pd.DataFrame(index=b["business_id"])
    for name, f in ACCLAIM.items():
        d = pd.read_parquet(RAW / "ratings" / f, columns=["camis"]).dropna()
        hit = perm[perm["camis"].isin(d["camis"].astype(str))]["business_id"].unique()
        out[f"acclaim_{name}"] = out.index.isin(hit)
    out["acclaimed"] = out.any(axis=1)
    return out.reset_index()


def rent(b: pd.DataFrame) -> pd.DataFrame:
    r = pd.read_parquet(AI / "nta_year_rent.parquet",
                        columns=["nta2020", "year", "ll157_rent_psf_yr", "dof_mv_psf_median", "dof_mv_index_2018"])
    b = b.assign(open_year=b["open_date"].dt.year.clip(lower=2012))
    return b.merge(r.rename(columns={"year": "open_year"}), on=["nta2020", "open_year"], how="left")


def traffic(b: pd.DataFrame) -> pd.DataFrame:
    f = RAW / "traffic" / "traffic_by_tract_year.parquet"
    if not f.exists():
        print("traffic index not built yet; skipping")
        return b
    t = pd.read_parquet(f)
    t = t.rename(columns={"year": "open_year"})
    tract = "boroct2020" if "boroct2020" in t else "ct2020"
    keep = [c for c in t.columns if c not in (tract, "open_year")]
    t = t.rename(columns={c: f"traffic_{c}" for c in keep})
    return b.merge(t, left_on=["ct2020", "open_year"], right_on=[tract, "open_year"], how="left")


def main() -> None:
    b = pd.read_parquet(OUT / "businesses.parquet")
    drop = [c for c in b.columns if c.startswith(("acclaim", "traffic_")) or c in
            {"family", "cuisine_clean", "limited_service", "brand_key", "is_chain_strict", "is_chain_loose",
             "nyc_max_concurrent", "operator_id", "multi_unit_operator", "first_time_operator",
             "operator_n_camis", "pluto_retailarea", "retail_area_per_storefront", "or_n_apps",
             "rrf_recipient", "rrf_amount", "ppp_first_draw", "ppp_second_draw", "alive_at_window",
             "price_tier", "price_tier_source", "open_year", "ll157_rent_psf_yr", "dof_mv_psf_median",
             "dof_mv_index_2018"}]
    b = b.drop(columns=drop)
    for f, cols in PERMIT_INPUTS.items():
        b = b.merge(read_camis(AI / f, cols), on="camis", how="left")
    tier = read_camis(RAW / "menus" / "camis_price_tier.parquet", ["tier", "tier_source"])
    b = b.merge(tier.rename(columns={"tier": "price_tier", "tier_source": "price_tier_source"}),
                on="camis", how="left")
    b = b.merge(acclaim(b), on="business_id", how="left")
    b = traffic(rent(b))
    b.to_parquet(OUT / "businesses.parquet", index=False)
    d = b[b["source"] == "dohmh"]
    print(f"businesses {len(b):,}: cuisine family {d['family'].notna().mean():.0%}, price tier "
          f"{d['price_tier'].notna().mean():.0%} (menu/stated {d['price_tier_source'].isin(['menu', 'menu_level', 'stated', 'guide', 'michelin']).mean():.0%}), "
          f"chain {d['is_chain_loose'].mean():.0%}, multi-unit operator known {d['multi_unit_operator'].notna().mean():.0%}, "
          f"acclaimed {b['acclaimed'].sum():,}, rent (either) {b[['ll157_rent_psf_yr', 'dof_mv_psf_median']].notna().any(axis=1).mean():.0%}")


if __name__ == "__main__":
    main()
