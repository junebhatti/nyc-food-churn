"""Export the analysis sections' data for the site (web/public/data/), after analysis_*.py.

  halflife.json  KM survival curves (0-10 years, quarterly) and 1/3/5-year survival by group
  cursed.test.json  curves by prior tenants + closure hazard by age band (analysis 'cursed spot x age')
  beta.json      beta / spread / COVID excess by neighbourhood, cuisine, borough, chain + city exit rate
  covid.json     half-yearly openings and closings, 2017-2023
Run: .venv/bin/python pipeline/export_analysis.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis_common import ANALYSIS, businesses
from export_site import FAMILY_LABEL, clean, write

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
    """Half-yearly openings and closings, 2017-2023, plus a candlestick of places open per half-year:
    open/close = places open at the start/end, high/low = the most/fewest at any month-end in it.
    Opening dates cluster at archive-copy dates (copies are months apart), so quarters are too lumpy;
    half-years are honest."""
    b = businesses()
    half = lambda d: d.dt.year.astype(str) + "H" + ((d.dt.month > 6) + 1).astype(str)  # noqa: E731
    opened = half(b["open_date"]).value_counts()
    closed = half(b.loc[b["event"], "close_date"]).value_counts()
    periods = [f"{y}H{h}" for y in range(2017, 2024) for h in (1, 2)]

    starts = np.sort(b["open_date"].dropna().values)
    ends = np.sort(b.loc[b["event"], "close_date"].dropna().values)
    alive = lambda t: int(np.searchsorted(starts, t, "right") - np.searchsorted(ends, t, "right"))  # noqa: E731
    candles = []
    for p in periods:
        y, h = int(p[:4]), int(p[-1])
        first = pd.Timestamp(year=y, month=1 if h == 1 else 7, day=1)
        months = [first - pd.Timedelta(days=1)] + [first + pd.offsets.MonthEnd(k) for k in range(1, 7)]
        counts = [alive(np.datetime64(t)) for t in months]
        candles.append({"o": counts[0], "c": counts[-1], "h": max(counts), "l": min(counts)})
    return {"periods": periods, "open": [int(opened.get(p, 0)) for p in periods],
            "close": [int(closed.get(p, 0)) for p in periods], "candles": candles}


def main() -> None:
    write("halflife.json", halflife())
    write("cursedtest.json", cursed_test())
    write("beta.json", beta())
    write("covid.json", covid())


if __name__ == "__main__":
    main()
