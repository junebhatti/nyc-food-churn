"""Kaplan-Meier survival by group, and the cursed-spot x age test.

Writes data/processed/analysis/:
  survival_by_group.csv  group, level, n, closures, median years, S at 1/3/5 years
  survival_curves.csv    S(t) on a quarter-year grid for every group level (feeds the site)
  cursed_by_age.csv      yearly closure hazard by age band for fresh vs previously-churned spots
  observed_since.csv     survival counted from when price tier / acclaim was first observed,
                         vs ordinary places alive at the same date and age (no survivorship bias)
Run: .venv/bin/python pipeline/analysis_survival.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter

from analysis_common import businesses, cohort, observed_dates, save

# price tier and acclaim are only observed after a place has survived a while: see observed_since()
GROUPS = ["all", "boro", "family_top", "chain", "limited_service", "cohort", "prior"]
MIN_N = 200
GRID = np.arange(0, 10.01, 0.25)
AGE_BANDS = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 10)]
CURSED_FROM = pd.Timestamp("2015-01-01")  # leaves 2.5+ years of building history before opening


def km_table(c: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, curves = [], []
    c = c.assign(all="all")
    for g in GROUPS:
        for level, d in c.groupby(g, observed=True):
            if len(d) < MIN_N:
                continue
            km = KaplanMeierFitter().fit(d["years"], d["event"])
            s = km.survival_function_at_times([1, 3, 5]).values
            rows.append({"group": g, "level": str(level), "n": len(d), "closures": int(d["event"].sum()),
                         "median_years": round(float(km.median_survival_time_), 2),
                         "S1": round(s[0], 3), "S3": round(s[1], 3), "S5": round(s[2], 3)})
            sf = km.survival_function_at_times(GRID).values
            curves.append(pd.DataFrame({"group": g, "level": str(level), "t": GRID, "S": sf.round(4)}))
    return pd.DataFrame(rows), pd.concat(curves)


def hazard_by_age(d: pd.DataFrame) -> list[dict]:
    """Closures per business-year within each age band (a life table)."""
    out = []
    for lo, hi in AGE_BANDS:
        exposure = (d["years"].clip(upper=hi) - lo).clip(lower=0)
        events = d["event"] & (d["years"] >= lo) & (d["years"] < hi)
        at_start = int((d["years"] > lo).sum())
        out.append({"age_band": f"{lo}-{hi}y", "at_risk_start": at_start, "closures": int(events.sum()),
                    "business_years": round(float(exposure.sum()), 1),
                    "hazard": round(float(events.sum() / exposure.sum()), 4) if exposure.sum() else np.nan})
    return out


def cursed_by_age(c: pd.DataFrame) -> pd.DataFrame:
    d = c[(c["open_date"] >= CURSED_FROM) & ~c["multi_tenant_building"].fillna(False).astype(bool)]
    rows = []
    for level, g in d.groupby("prior", observed=True):
        for r in hazard_by_age(g):
            rows.append({"prior": str(level), "n": len(g), **r})
    t = pd.DataFrame(rows)
    fresh = t[t["prior"] == "fresh"].set_index("age_band")["hazard"]
    t["hazard_ratio_vs_fresh"] = (t["hazard"] / t["age_band"].map(fresh)).round(2)
    return t


def since(d: pd.DataFrame, start: pd.Series) -> pd.DataFrame:
    """Years from `start` to the business's end, for businesses still open at `start`."""
    keep = start.notna() & (start >= d["open_date"]) & (start < d["end_date"])
    d = d[keep].copy()
    d["t"] = (d["end_date"] - start[keep]).dt.days / 365.25
    return d[d["t"] > 0]


def matched_controls(b: pd.DataFrame, treated: pd.DataFrame, seen_col: str, k: int = 5) -> pd.DataFrame:
    """Up to k unacclaimed businesses alive on each treated business's observation date,
    of similar age (within 1 year), timed from that same date."""
    rng = np.random.default_rng(7)
    pool = b[b[seen_col].isna()]
    out = []
    for _, r in treated.iterrows():
        s, age = r[seen_col], (r[seen_col] - r["open_date"]).days / 365.25
        alive = pool[(pool["open_date"] <= s) & (pool["end_date"] > s)]
        alive_age = (s - alive["open_date"]).dt.days / 365.25
        cand = alive[(alive_age - age).abs() <= 1]
        if len(cand):
            pick = cand.iloc[rng.choice(len(cand), min(k, len(cand)), replace=False)]
            out.append(pick.assign(t=(pick["end_date"] - s).dt.days / 365.25))
    return pd.concat(out) if out else pd.DataFrame()


def observed_since() -> pd.DataFrame:
    b = observed_dates(businesses())
    rows = []

    def add(group, level, d):
        if len(d) < 50:
            return
        km = KaplanMeierFitter().fit(d["t"], d["event"])
        s = km.survival_function_at_times([1, 3, 5]).values
        rows.append({"group": group, "level": level, "n": len(d), "closures": int(d["event"].sum()),
                     "S1_after": round(s[0], 3), "S3_after": round(s[1], 3), "S5_after": round(s[2], 3)})

    p = since(b, b["price_seen"])
    for tier, d in p[p["price_obs"].notna()].groupby("price_obs"):
        add("price_tier_since_observed", tier, d)
    acc = since(b, b["acclaim_seen"])
    add("acclaim_since_first_mention", "acclaimed", acc)
    add("acclaim_since_first_mention", "matched unacclaimed (same date, age +/-1y)",
        matched_controls(b, acc, "acclaim_seen"))
    return pd.DataFrame(rows)


def main() -> None:
    c = cohort()
    table, curves = km_table(c)
    save(table, "survival_by_group.csv")
    save(curves, "survival_curves.csv")
    cursed = cursed_by_age(c)
    save(cursed, "cursed_by_age.csv")
    pd.set_option("display.width", 200)
    print(f"cohort {len(c):,} businesses opened since 2012-07-06, {int(c['event'].sum()):,} closures\n")
    print(table.to_string(index=False))
    obs = observed_since()
    save(obs, "observed_since.csv")
    print("\nsurvival from first observation (delayed entry):")
    print(obs.to_string(index=False))
    print("\ncursed spot x age (single-storefront buildings, opened 2015+):")
    print(cursed.to_string(index=False))


if __name__ == "__main__":
    main()
