"""Export the analysis sections' data for the site (web/public/data/), after analysis_*.py.

  halflife.json  KM survival curves (0-10 years, quarterly) and 1/3/5-year survival by group
  cursed.test.json  curves by prior tenants + closure hazard by age band (analysis 'cursed spot x age')
  beta.json      beta / spread / COVID excess by neighbourhood, cuisine, borough, chain + city exit rate
  covid.json     half-yearly openings and closings, 2017-2023
  pitch.json     Cox model for the "pitch your restaurant" tool: coefficients, covariate means,
                 baseline survival, plus per-neighbourhood inputs (value, foot traffic, beta, rent)
The pitch model is fit on places opened 2015-2021, so every place has ~5 years of follow-up and
the delayed DOHMH purge of recent closures doesn't flatter the curve.
Run: .venv/bin/python pipeline/export_analysis.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter

from analysis_common import ANALYSIS, businesses, cohort
from export_site import FAMILY_LABEL, WEB, clean, write

PITCH_FROM, PITCH_TO = pd.Timestamp("2015-01-01"), pd.Timestamp("2021-12-31")
GROUP_LABEL = {"all": "All places", "boro": "Borough", "family_top": "Cuisine", "chain": "Chain",
               "cohort": "Year opened", "prior": "Storefront history"}
BORO_TITLE = {"MANHATTAN": "Manhattan", "BROOKLYN": "Brooklyn", "QUEENS": "Queens", "BRONX": "Bronx",
              "STATEN ISLAND": "Staten Island"}


def level_label(group: str, level: str) -> str:
    if group == "family_top":
        return FAMILY_LABEL.get(level, level.replace("_", " ").title())
    if group == "chain":
        return "Chain" if level == "True" else "Independent"
    if group == "boro":
        return BORO_TITLE.get(level, level.title())
    return level


def halflife() -> dict:
    t = pd.read_csv(ANALYSIS / "survival_by_group.csv")
    c = pd.read_csv(ANALYSIS / "survival_curves.csv")
    t = t[t["level"] != "UNKNOWN"]
    out = {}
    for g, d in t.groupby("group"):
        rows = []
        for _, r in d.iterrows():
            curve = c[(c["group"] == g) & (c["level"].astype(str) == str(r["level"]))].sort_values("t")["S"]
            rows.append({"level": level_label(g, str(r["level"])), "n": int(r["n"]),
                         "median": clean(float(r["median_years"])), "s1": r["S1"], "s3": r["S3"], "s5": r["S5"],
                         "curve": [clean(round(float(v), 4)) for v in curve]})
        out[g] = {"label": GROUP_LABEL.get(g, g), "rows": sorted(rows, key=lambda x: -x["n"])}
    return {"grid": [round(x, 2) for x in np.arange(0, 10.01, 0.25)], "groups": out}


def cursed_test() -> dict:
    h = pd.read_csv(ANALYSIS / "cursed_by_age.csv")
    hal = halflife()["groups"]["prior"]["rows"]
    return {"curves": hal, "byAge": h.to_dict("records")}


def beta() -> dict:
    b = pd.read_csv(ANALYSIS / "beta_by_group.csv")
    city = pd.read_csv(ANALYSIS / "city_exit_rate.csv")
    b = b[b["level"] != "UNKNOWN"].copy()
    b["label"] = [r["name"] if isinstance(r.get("name"), str) else level_label(r["group"], str(r["level"]))
                  for _, r in b.iterrows()]
    rows = b[["group", "level", "label", "avg_at_risk", "baseline_exit_pct", "spread_bp", "covid_excess_pts", "beta"]]
    return {"city": city.to_dict("records"), "rows": rows.to_dict("records")}


def covid() -> dict:
    """Half-yearly openings and closings, 2017-2023. Opening dates cluster at archive-copy dates
    (copies are months apart), so quarters are too lumpy; half-years are honest."""
    b = businesses()
    half = lambda d: d.dt.year.astype(str) + "H" + ((d.dt.month > 6) + 1).astype(str)  # noqa: E731
    opened = half(b["open_date"]).value_counts()
    closed = half(b.loc[b["event"], "close_date"]).value_counts()
    periods = [f"{y}H{h}" for y in range(2017, 2024) for h in (1, 2)]
    return {"periods": periods, "open": [int(opened.get(p, 0)) for p in periods],
            "close": [int(closed.get(p, 0)) for p in periods]}


PITCH_FAMILIES = ["american", "chinese", "latin_caribbean", "pizza", "cafe_coffee_tea", "bakery_desserts",
                  "japanese_korean", "mexican_texmex", "italian", "mideast_mediterranean", "deli_sandwich_salad",
                  "southeast_asian_other_asian", "juice_beverages", "chicken", "south_asian", "european", "bar"]


def pitch() -> dict:
    c = cohort()
    c = c[c["open_date"].between(PITCH_FROM, PITCH_TO) & (c["boro"] != "UNKNOWN")].copy()
    fam = c["family"].where(c["family"].isin(PITCH_FAMILIES), "other")
    x = pd.DataFrame({"years": c["years"].clip(upper=10), "event": (c["event"] & (c["years"] <= 10)).astype(int)})
    for f in PITCH_FAMILIES[1:] + ["other"]:
        x[f"cuisine_{f}"] = (fam == f).astype(int)
    for bo in ["BROOKLYN", "QUEENS", "BRONX", "STATEN ISLAND"]:
        x[f"boro_{bo}"] = (c["boro"] == bo).astype(int)
    x["chain"] = c["chain"].astype(int)
    x["limited_service"] = c["limited_service"].fillna(False).astype(int)
    x["prior_1_2"] = (c["prior"] == "1-2 prior").astype(int)
    x["prior_3plus"] = (c["prior"] == "3+ prior").astype(int)
    v = np.log(c["dof_mv_psf_median"].where(c["dof_mv_psf_median"] > 0))
    v_mu, v_sd = float(v.mean()), float(v.std())
    x["nbhd_value_z"] = ((v - v_mu) / v_sd).fillna(0)
    f = c["traffic_fti_within_year"]
    f_mu, f_sd = float(f.mean()), float(f.std())
    x["foot_traffic_z"] = ((f - f_mu) / f_sd).fillna(0)
    cph = CoxPHFitter(penalizer=0.001).fit(x, duration_col="years", event_col="event")
    grid = np.arange(0, 10.01, 0.25)
    # Baseline survival is at the covariate means (lifelines centers X); read the step function on the grid.
    bs = cph.baseline_survival_.iloc[:, 0]
    base = np.array([bs[bs.index <= t].iloc[-1] if (bs.index <= t).any() else 1.0 for t in grid])
    means = cph._norm_mean.to_dict()  # noqa: SLF001 - the centring lifelines applies before exp(xb)

    # Neighbourhood inputs: the model's standardized value and foot traffic, typical for places there.
    c["v_z"], c["f_z"] = x["nbhd_value_z"], x["foot_traffic_z"]
    nb = c.groupby("nta2020").agg(n=("v_z", "size"), value_z=("v_z", "median"), traffic_z=("f_z", "median"),
                                  boro=("boro", "first"))
    nb = nb[nb["n"] >= 30]
    betas = pd.read_csv(ANALYSIS / "beta_by_group.csv")
    betas = betas[betas["group"] == "nta2020"].set_index("level")["beta"]
    hoods = {h["id"]: h for h in json.loads((WEB / "neighborhoods.json").read_text())}
    nbhd = [{"id": k, "name": hoods[k]["name"] if k in hoods else k, "boro": BORO_TITLE.get(r["boro"], r["boro"]),
             "valueZ": round(float(r["value_z"]), 3), "trafficZ": round(float(r["traffic_z"]), 3),
             "beta": clean(float(betas[k])) if k in betas else None,
             "rent": hoods.get(k, {}).get("rent"), "closure3y": hoods.get(k, {}).get("closure3y")}
            for k, r in nb.iterrows()]
    print(f"pitch model: n={len(x):,}, events={int(x['event'].sum()):,}, concordance={cph.concordance_index_:.3f}")
    return {"grid": [round(t, 2) for t in grid], "baseline": [round(float(s), 4) for s in base],
            "coef": {k: round(float(vv), 4) for k, vv in cph.params_.items()},
            "means": {k: round(float(vv), 4) for k, vv in means.items()},
            "cuisines": [{"id": f, "label": FAMILY_LABEL.get(f, f)} for f in PITCH_FAMILIES] + [{"id": "other", "label": "Other"}],
            "neighborhoods": sorted(nbhd, key=lambda d: d["name"]),
            "fit": {"n": int(len(x)), "events": int(x["event"].sum()), "concordance": round(cph.concordance_index_, 3),
                    "opened": "2015-2021"}}


def main() -> None:
    write("halflife.json", halflife())
    write("cursedtest.json", cursed_test())
    write("beta.json", beta())
    write("covid.json", covid())
    write("pitch.json", pitch())


if __name__ == "__main__":
    main()
