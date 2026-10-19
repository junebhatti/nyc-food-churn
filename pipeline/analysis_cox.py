"""Cox proportional-hazards model: what raises or lowers closure risk, all else equal.

Cohort as in analysis_common, limited to businesses opened from 2015 on, so every business has
at least 2.5 years of visible building history (earlier openings can't see their predecessors,
which would bias the storefront-history terms). Relocations count as censored.
Stratified by opening cohort, so each cohort keeps its own baseline (COVID-era and recent
cohorts behave differently and recent closures are under-detected).
Covariates, each against a reference level:
  cuisine family (ref american), borough (ref Manhattan), chain, limited service,
  storefront history (ref fresh: 1-2 / 3+ prior tenants), multi-tenant building,
  neighbourhood value per sq ft in the opening year (DOF, standardized log; missing flagged).
Price tier and acclaim are left out here: both are observed only after a place has survived,
which biases a fixed covariate (see observed_since.csv for the fair comparison).
A hazard ratio of 1.40 means 40% more likely to close at any given age.

Writes data/processed/analysis/cox_hazard_ratios.csv. Run: .venv/bin/python pipeline/analysis_cox.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

from analysis_common import cohort, save

HISTORY_FROM = pd.Timestamp("2015-01-01")


def design(c: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame({"years": c["years"], "event": c["event"].astype(int), "cohort": c["cohort"].astype(str)})
    fam = pd.get_dummies(c["family_top"], prefix="cuisine").drop(columns=["cuisine_american"])
    boro = c["boro"].where(c["boro"] != "UNKNOWN")
    bor = pd.get_dummies(boro, prefix="boro").drop(columns=["boro_MANHATTAN"])
    x["chain"] = c["chain"].astype(int)
    x["limited_service"] = c["limited_service"].fillna(False).astype(int)
    x["prior_1_2"] = (c["prior"] == "1-2 prior").astype(int)
    x["prior_3plus"] = (c["prior"] == "3+ prior").astype(int)
    x["multi_tenant_building"] = c["multi_tenant_building"].fillna(False).astype(int)
    v = np.log(c["dof_mv_psf_median"].where(c["dof_mv_psf_median"] > 0))
    x["nbhd_value_missing"] = v.isna().astype(int)
    x["nbhd_value_z"] = ((v - v.mean()) / v.std()).fillna(0)
    return pd.concat([x, fam.astype(int), bor.astype(int)], axis=1)


def main() -> None:
    c = cohort()
    c = c[c["open_date"] >= HISTORY_FROM]
    x = design(c)
    cph = CoxPHFitter(penalizer=0.001).fit(x, duration_col="years", event_col="event", strata=["cohort"])
    s = cph.summary
    out = pd.DataFrame({"covariate": s.index, "hazard_ratio": s["exp(coef)"].round(3),
                        "ci_low": s["exp(coef) lower 95%"].round(3), "ci_high": s["exp(coef) upper 95%"].round(3),
                        "p": s["p"].map(lambda p: float(f"{p:.2g}"))}).sort_values("hazard_ratio")
    save(out, "cox_hazard_ratios.csv")
    pd.set_option("display.width", 200)
    print(f"n={len(x):,} events={int(x['event'].sum()):,} concordance={cph.concordance_index_:.3f}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
