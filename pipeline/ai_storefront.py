"""Storefront history before each CAMIS opened.

1. DOHMH succession at the same address (addr_key = house + street + borough):
   prior food tenants, the immediately preceding tenant's lifespan, and the gap between its last
   sighting and this CAMIS's first inspection (a vacancy upper bound; it includes the closure-date
   uncertainty of the predecessor). Predecessor = the prior tenant that ended last but no later
   than 60 d after this opening; tenants that kept going are counted in n_concurrent_at_address. prev_same_name flags permit re-issues/ownership changes that
   kept the name (not a new business).
   History is only observed from ~2011 (earliest copies 2013-14 keep ~3 y), so counts of prior
   tenants are left-truncated: history_years_observed says how much address history we see.
2. LL157 storefront registry (2019-2025): the matched storefront's reported vacancy at 12/31 of
   each year before opening, consecutive vacant years before opening, and prior primary activity.

Outputs: camis_storefront_history.parquet
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai_common import OUT, RAW, log, norm_addr, write_out

DATA_START = pd.Timestamp("2011-01-01")
BORO = {"MANHATTAN": "Manhattan", "BRONX": "Bronx", "BROOKLYN": "Brooklyn", "QUEENS": "Queens",
        "STATEN ISLAND": "Staten Island", "STATEN IS": "Staten Island"}


def succession(b: pd.DataFrame) -> pd.DataFrame:
    b = b.dropna(subset=["addr_key"]).copy()
    b["start"] = b["first_insp"].fillna(b["first_snap"])
    b["end"] = b[["last_insp", "last_snap"]].max(axis=1)
    b = b.sort_values(["addr_key", "start", "camis"])
    rows = []
    for ak, g in b.groupby("addr_key", sort=False):
        s, e, c, n = g["start"].values, g["end"].values, g["camis"].values, g["dba_key"].values
        for i in range(len(g)):
            prior = np.where(s < s[i])[0]
            rec = {"camis": c[i], "n_prior_tenants": len(prior),
                   "n_prior_tenants_diff_name": int(sum(n[j] != n[i] for j in prior))}
            # tenants still open well after we opened = other units at a multi-tenant address
            conc = prior[e[prior] > s[i] + np.timedelta64(60, "D")]
            rec["n_concurrent_at_address"] = len(conc)
            ended = prior[e[prior] <= s[i] + np.timedelta64(60, "D")]
            if len(ended):
                j = ended[np.argmax(e[ended])]  # predecessor = the one that ended last before we opened
                rec.update(prev_camis=c[j], prev_same_name=bool(n[j] == n[i]),
                           prev_lifespan_days=float((e[j] - s[j]) / np.timedelta64(1, "D")),
                           prev_left_censored=bool(s[j] < np.datetime64("2011-07-01")),
                           gap_days=float((s[i] - e[j]) / np.timedelta64(1, "D")))
            rows.append(rec)
    out = pd.DataFrame(rows)
    out = out.merge(b[["camis", "start"]], on="camis")
    out["history_years_observed"] = ((out["start"] - DATA_START).dt.days / 365.25).clip(lower=0).round(1)
    out["multi_tenant_address"] = out["n_concurrent_at_address"] > 0
    return out.drop(columns="start")


def registry(b: pd.DataFrame) -> pd.DataFrame:
    r = pd.read_parquet(RAW / "gov" / "storefronts_registry.parquet",
                        columns=["reporting_year", "property_number", "property_street", "borough",
                                 "vacant_on_12_31", "primary_business_activity", "bbl"])
    r["year"] = r["reporting_year"].str[:4].astype(int)
    r = r[r["year"] <= 2025]
    r["boro"] = r["borough"].str.upper().map(BORO)
    r["addr_key"] = [f"{bo}|{a}" if a and bo else None
                     for a, bo in zip(map(norm_addr, r["property_number"], r["property_street"]), r["boro"])]
    r["vacant"] = r["vacant_on_12_31"].isin(["YES", "Y"])
    r = r.dropna(subset=["addr_key"])
    # one status per storefront-address-year (several units at one address: vacant if any vacant)
    ry = r.groupby(["addr_key", "year"]).agg(vacant=("vacant", "max"),
                                             activity=("primary_business_activity", "first")).reset_index()
    b = b.dropna(subset=["addr_key"]).copy()
    b["open_year"] = b["first_insp"].fillna(b["first_snap"]).dt.year
    m = b[["camis", "addr_key", "open_year"]].merge(ry, on="addr_key")
    m = m[m["year"] < m["open_year"]].sort_values(["camis", "year"])
    rows = []
    for c, g in m.groupby("camis"):
        v = g["vacant"].values
        run = 0
        for x in v[::-1]:
            if not x:
                break
            run += 1
        last = g.iloc[-1]
        rows.append({"camis": c, "reg_years_before_open": len(g), "reg_last_year": int(last["year"]),
                     "reg_vacant_year_before": bool(last["vacant"]) if last["year"] == last["open_year"] - 1 else None,
                     "reg_consec_vacant_years_before": run, "reg_prev_activity": last["activity"]})
    out = pd.DataFrame(rows)
    matched = b["addr_key"].isin(set(ry["addr_key"]))
    log.info("registry address match: %.1f%% of CAMIS (%.1f%% of those opened 2020+)", 100 * matched.mean(),
             100 * matched[b["open_year"] >= 2020].mean())
    return out


def build():
    b = pd.read_parquet(OUT / "camis_base.parquet",
                        columns=["camis", "addr_key", "dba_key", "first_insp", "first_snap", "last_insp", "last_snap"])
    s = succession(b)
    r = registry(b)
    out = b[["camis"]].merge(s, on="camis", how="left").merge(r, on="camis", how="left")
    write_out(out, "camis_storefront_history", "camis_base + gov/storefronts_registry",
              "address succession from DOHMH (left-truncated ~2011) + LL157 vacancy before opening (2019-2025)")


if __name__ == "__main__":
    build()
