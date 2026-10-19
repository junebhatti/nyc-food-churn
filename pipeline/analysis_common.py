"""Shared setup for the first analysis pass (analysis_*.py).

Cohort: businesses that opened on or after the first full copy (2012-07-06), so their start is
observed. That covers both DOHMH food permits and NYSLA-only bars (family "bar").
Duration = years from opening to estimated closure, or to the latest copy if still open.
A relocation is not a failure, so relocated closures count as censored.
Observed price tier = menu, stated or Michelin tier only (proxies can't see upscale).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from build_lifespans import OUT, RAW

ANALYSIS = OUT / "analysis"
FIRST_COPY = pd.Timestamp("2012-07-06")
TOP_FAMILIES = 14
BORO_DIGIT = {"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN", "4": "QUEENS", "5": "STATEN ISLAND"}


def businesses() -> pd.DataFrame:
    """All businesses except SNAP bodegas, whose dates mark SNAP authorization, not opening/closing."""
    b = pd.read_parquet(OUT / "businesses.parquet")
    b = b[b["source"] != "snap"].copy()
    b["family"] = b["family"].where(b["source"] == "dohmh", "bar")
    b["event"] = b["closed"] & ~b["relocated"]
    b["years"] = b["lifespan_days"] / 365.25
    b["price_obs"] = b["price_tier"].where(b["price_tier_source"].isin(["menu", "menu_level", "stated", "michelin"]))
    b["chain"] = b["is_chain_loose"].fillna(False).astype(bool)
    b["acclaimed"] = b["acclaimed"].fillna(False).astype(bool)
    b["prior"] = pd.cut(b["n_prior_tenants"], [-1, 0, 2, np.inf], labels=["fresh", "1-2 prior", "3+ prior"])
    # Raw borough labels are messy ("0", "MISSING", codes); the BBL's first digit is reliable.
    by_bbl = b["bbl"].astype(str).str[0].map(BORO_DIGIT)
    raw = b["boro"].fillna("").str.upper().where(lambda s: s.isin(BORO_DIGIT.values()))
    b["boro"] = by_bbl.fillna(raw).fillna("UNKNOWN")
    return b


def cohort() -> pd.DataFrame:
    b = businesses()
    c = b[(b["open_date"] >= FIRST_COPY) & (b["years"] > 0)].copy()
    top = c["family"].value_counts().head(TOP_FAMILIES).index
    c["family_top"] = c["family"].where(c["family"].isin(top), "other")
    c["cohort"] = pd.cut(c["open_date"].dt.year, [2011, 2014, 2017, 2019, 2021, 2026],
                         labels=["2012-14", "2015-17", "2018-19", "2020-21", "2022-26"])
    return c


STATED_SEEN = pd.Timestamp("2021-09-01")  # UCSD Google Local 2021 crawl
GUIDE_SEEN = pd.Timestamp("2022-07-01")   # first Michelin Guide snapshot


def observed_dates(c: pd.DataFrame) -> pd.DataFrame:
    """When each business's price tier and first acclaim were observed. A place only gets a menu
    page, a Google price level or a critic's mention after it has already survived for a while,
    so survival must count from that date (delayed entry), not from opening."""
    t = pd.read_parquet(RAW / "menus" / "camis_price_tier.parquet", columns=["camis", "tier_source", "menu_snapshot"])
    t["camis"] = t["camis"].astype(str)
    t["price_seen"] = pd.to_datetime(t["menu_snapshot"]).where(
        t["tier_source"].isin(["menu", "menu_level"]),
        t["tier_source"].map({"stated": STATED_SEEN, "michelin": GUIDE_SEEN}))
    c = c.merge(t[["camis", "price_seen"]], on="camis", how="left")

    perm = c[["business_id", "camis_list"]].explode("camis_list").rename(columns={"camis_list": "camis"})
    perm["camis"] = perm["camis"].astype(str)
    dates = []
    r = RAW / "ratings"
    m = pd.read_parquet(r / "michelin_nyc.parquet", columns=["camis", "year"])
    dates.append(m.assign(d=pd.to_datetime(m["year"].astype(int).astype(str) + "-10-01")))
    e = pd.read_parquet(r / "eater_lists.parquet", columns=["camis", "quarter"])
    dates.append(e.assign(d=pd.PeriodIndex(e["quarter"], freq="Q").to_timestamp()))
    n = pd.read_parquet(r / "nyt_reviews.parquet", columns=["camis", "review_date"])
    dates.append(n.assign(d=pd.to_datetime(n["review_date"], errors="coerce")))
    a = pd.read_parquet(r / "awards_nyc.parquet", columns=["camis", "year"])
    dates.append(a.assign(d=pd.to_datetime(a["year"].astype(int).astype(str) + "-05-01")))
    d = pd.concat([x[["camis", "d"]] for x in dates]).dropna()
    d["camis"] = d["camis"].astype(str)
    first = perm.merge(d, on="camis").groupby("business_id")["d"].min().rename("acclaim_seen")
    return c.merge(first, on="business_id", how="left")


def save(df: pd.DataFrame, name: str) -> None:
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    df.to_csv(ANALYSIS / name, index=False)
