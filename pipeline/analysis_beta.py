"""Beta: how hard each neighbourhood or kind of place swings with the city's bad years.

Annual exit rate per group = closures in year / businesses open on Jan 1 (all businesses,
including those opened before 2012; relocations are not exits), 2013-2025.
  beta        slope of the group's annual exit rate on the citywide rate (OLS). 1 = moves with the
              city, above 1 = amplifies shocks, below 1 = defensive.
  covid_excess mean exit rate 2019-21 minus the 2013-17 baseline, in points. Pooled over three
              years because COVID-era closure dates are smeared across long windows (merge.md).
  baseline    mean 2013-17 exit rate (the "spread" input).
  spread_bp   baseline minus the citywide baseline, in basis points.
Neighbourhoods need MIN_AT_RISK businesses open on an average Jan 1.
Caveat: closure dates are good to about a quarter, and the 2018-19 and 2022-25 rates are biased
low (see merge.md), so read beta as a ranking, not a precise number.

Writes data/processed/analysis/beta_by_group.csv. Run: .venv/bin/python pipeline/analysis_beta.py
"""
from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from analysis_common import TOP_FAMILIES, businesses, save
from build_lifespans import RAW

YEARS = range(2013, 2026)
MIN_AT_RISK = 150


def nta_names() -> dict:
    g = json.load(gzip.open(RAW / "gov" / "geo_nta2020.geojson.gz"))
    return {f["properties"]["nta2020"]: f["properties"]["ntaname"] for f in g["features"]}


def annual_rates(b: pd.DataFrame, key: str) -> pd.DataFrame:
    rows = []
    for y in YEARS:
        jan1, next1 = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y + 1}-01-01")
        alive = b[(b["open_date"] < jan1) & (b["end_date"] >= jan1)]
        exits = alive["event"] & (alive["close_date"] < next1)
        g = alive.assign(exit=exits).groupby(key, observed=True)["exit"].agg(["size", "sum"])
        g["year"] = y
        rows.append(g.reset_index())
    r = pd.concat(rows).rename(columns={"size": "at_risk", "sum": "exits"})
    r["rate"] = 100 * r["exits"] / r["at_risk"]
    return r


def summarize(r: pd.DataFrame, key: str, city: pd.Series) -> pd.DataFrame:
    out = []
    city_base = city.loc[2013:2017].mean()
    for level, g in r.groupby(key, observed=True):
        g = g.set_index("year")
        if g["at_risk"].mean() < MIN_AT_RISK or len(g) < len(YEARS):
            continue
        x, y = city.loc[g.index].values, g["rate"].values
        beta = np.polyfit(x, y, 1)[0]
        base = g.loc[2013:2017, "rate"].mean()
        out.append({"group": key, "level": str(level), "avg_at_risk": round(g["at_risk"].mean()),
                    "baseline_exit_pct": round(base, 2), "spread_bp": round(100 * (base - city_base)),
                    "covid_excess_pts": round(g.loc[2019:2021, "rate"].mean() - base, 2),
                    "beta": round(beta, 2)})
    return pd.DataFrame(out)


def main() -> None:
    b = businesses()
    top = b["family"].value_counts().head(TOP_FAMILIES).index
    b["family_top"] = b["family"].where(b["family"].isin(top), "other")
    b["city"] = "NYC"
    city = annual_rates(b, "city").set_index("year")["rate"]
    parts = [summarize(annual_rates(b, k), k, city) for k in ["city", "boro", "family_top", "chain", "nta2020"]]
    out = pd.concat(parts, ignore_index=True)
    nta = out["group"] == "nta2020"
    out.loc[nta, "name"] = out.loc[nta, "level"].map(nta_names())
    save(out, "beta_by_group.csv")
    save(pd.DataFrame({"year": city.index, "city_exit_pct": city.round(2).values}), "city_exit_rate.csv")
    pd.set_option("display.width", 200)
    print("citywide exit rate by year:", city.round(1).to_dict())
    for g in ["boro", "family_top", "chain"]:
        print(out[out["group"] == g].sort_values("beta").to_string(index=False))
    nta = out[out["group"] == "nta2020"].sort_values("beta")
    print(f"\nneighbourhoods: {len(nta)}; lowest beta:\n{nta.head(8).to_string(index=False)}"
          f"\nhighest beta:\n{nta.tail(8).to_string(index=False)}")


if __name__ == "__main__":
    main()
