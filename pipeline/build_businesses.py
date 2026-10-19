"""Step 2 of the merge: permits -> businesses, plus bars that hold no DOHMH permit.

1. Permits listed and dropped without ever being inspected are flagged `likely_never_opened`
   and left out of businesses (7k abandoned build-outs would otherwise inflate churn).
2. Permits with the same or a fuzzily similar name on the same tax lot merge into one business
   (a new permit after an ownership change is not a closure). The business opens with its
   first permit and ends with the permit listed last.
3. A closed, non-chain business whose name reappears at another address within 365 days of its
   closure is flagged `relocated` (and the new one `relocated_from`).
4. NYSLA bar/tavern and club premises with no DOHMH business within 60 m by name are added as
   source="sla" businesses, with licence start/end dates (ends known from 2015 on).

Reads data/processed/permits.parquet; writes data/processed/businesses.parquet.
Run: .venv/bin/python pipeline/build_businesses.py
"""
from __future__ import annotations

import os
import re
from difflib import SequenceMatcher

import duckdb
import pandas as pd

from build_lifespans import AI, OUT, RAW
from gt_common import mnorm

BAR_CATEGORIES = ("bar_tavern", "club")
MATCH_M = 60
NAME_SIM = 0.85
RELOCATE_DAYS = 365
FUZZY_RATIO = 0.85
MERGE_GAP_DAYS = 365


def permits() -> pd.DataFrame:
    p = pd.read_parquet(OUT / "permits.parquet")
    p["likely_never_opened"] = p["F"].isna() & p["closed"]
    return p


def location_key(p: pd.DataFrame) -> pd.Series:
    """Tax lot (BBL) when valid, else the street text. Street spellings differ between copy eras
    ("W 14TH ST" vs "WEST 14 STREET"), so text keys alone split one place into two."""
    bbl = p["bbl"].astype(str).str.replace(r"\.0$", "", regex=True)
    ok = bbl.str.fullmatch(r"[1-5]\d{9}") & ~bbl.str[1:].str.fullmatch(r"0+")
    return ("BBL:" + bbl).where(ok, "ADDR:" + p["addr_key"].fillna(""))


def compact(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(name).upper())


def same_name(a: str, b: str) -> bool:
    """Spelling variants of one name: "T BAAR"/"TBAAR", "PokeZone 1"/"POKEZONE ONE", "LOZA"/"FALAFEL LOZA"."""
    if not a or not b:
        return False
    if a == b or SequenceMatcher(None, a, b).ratio() >= FUZZY_RATIO:
        return True
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 4 and short in long_:  # "LOZA" / "FALAFEL LOZA"
        return True
    pre = len(os.path.commonprefix([a, b]))
    return pre >= 6 and pre >= 0.7 * min(len(a), len(b))


def cluster_ids(p: pd.DataFrame) -> pd.Series:
    """Greedy per location, in opening order: join the cluster whose latest name matches and
    whose last permit ended at most MERGE_GAP_DAYS before this one opened."""
    ids = pd.Series(index=p.index, dtype=object)
    n = 0
    for _, g in p.groupby("loc_key", sort=False):
        clusters: list[list] = []  # [id, compact name, end_date]
        for i, r in g.iterrows():
            nm = compact(r["name_key"]) or f"CAMIS{r['camis']}"
            for cl in clusters:
                if same_name(nm, cl[1]) and (r["open_date"] - cl[2]).days <= MERGE_GAP_DAYS:
                    ids[i] = cl[0]
                    cl[1], cl[2] = nm, max(cl[2], r["end_date"])
                    break
            else:
                ids[i] = f"D{n}"
                n += 1
                clusters.append([ids[i], nm, r["end_date"]])
    return ids


def merge_permits(p: pd.DataFrame) -> pd.DataFrame:
    p = p[~p["likely_never_opened"]].sort_values("open_date").copy()
    p["loc_key"] = location_key(p)
    p["business_id"] = cluster_ids(p)
    g = p.groupby("business_id")
    first = p.loc[g["open_date"].idxmin()].set_index("business_id")
    last = p.loc[g["last_snap"].idxmax()].set_index("business_id")
    b = pd.DataFrame({
        "camis_list": g["camis"].agg(list), "n_permits": g.size(),
        "open_date": g["open_date"].min(), "known_open_by": g["known_open_by"].min(),
        "left_censored": first["left_censored"],
    })
    for col in ["dba", "name_key", "dba_key", "boro", "building", "street", "zip", "addr_key", "bbl",
                "bin", "loc_key", "lat", "lon", "nta2020", "ct2020", "closed", "close_date", "close_lo",
                "close_hi", "end_date", "L_raised"]:
        b[col] = last[col]
    b["camis"] = last["camis"]  # latest permit: key for joining the camis_* inputs
    b["lifespan_days"] = (b["end_date"] - b["open_date"]).dt.days
    b["source"] = "dohmh"
    return b.reset_index()


def flag_relocations(b: pd.DataFrame) -> pd.DataFrame:
    chain = pd.read_parquet(AI / "camis_chain.parquet", columns=["camis", "is_chain_loose"])
    chain["camis"] = chain["camis"].astype(str)
    b = b.merge(chain, on="camis", how="left")
    cand = b[(b["name_key"].fillna("") != "") & ~b["is_chain_loose"].fillna(False).astype(bool)]
    closed = cand[cand["closed"]][["business_id", "name_key", "loc_key", "close_date"]]
    opened = cand[["business_id", "name_key", "loc_key", "open_date"]]
    m = closed.merge(opened, on="name_key", suffixes=("", "_new"))
    gap = (m["open_date"] - m["close_date"]).dt.days
    m = m[(m["loc_key"] != m["loc_key_new"]) & gap.between(-90, RELOCATE_DAYS)]
    b["relocated"] = b["business_id"].isin(m["business_id"])
    b["relocated_from"] = b["business_id"].isin(m["business_id_new"])
    return b.drop(columns=["is_chain_loose"])


def bar_premises() -> pd.DataFrame:
    s = pd.read_parquet(RAW / "gov" / "sla_licenses_nyc.parquet")
    s = s[s["category"].isin(BAR_CATEGORIES) & s["lat"].notna()].copy()
    s["open_now"] = s["in_current_lists"].fillna(False) & s["end_date"].isna()
    s["start"] = s[["premise_first_start", "start_date"]].min(axis=1)
    g = s.sort_values("effective_date").groupby("premise_key")
    out = g.agg(dba=("dba", "last"), legal_name=("legal_name", "last"), address=("address", "last"),
                zip=("zip", "last"), lat=("lat", "last"), lon=("lon", "last"),
                category=("category", "last"), open_date=("start", "min"), last_end=("end_date", "max"),
                open_now=("open_now", "any")).reset_index()
    out["name"] = out["dba"].fillna(out["legal_name"])
    return out


def match_bars(bars: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """(premise_key, business_id) pairs: bar premises matching a DOHMH business within MATCH_M m by name."""
    c = duckdb.connect()
    c.register("bars", bars.assign(n1=bars["dba"].fillna("").map(mnorm),
                                   n2=bars["legal_name"].fillna("").map(mnorm)))
    c.register("biz", b[b["lat"].notna()].assign(n=b["dba"].fillna("").map(mnorm))[["business_id", "n", "lat", "lon"]])
    return c.execute(f"""
      select distinct s.premise_key, d.business_id from bars s join biz d
        on abs(d.lat - s.lat) < 0.0008 and abs(d.lon - s.lon) < 0.0011
      where 111320 * sqrt(power(d.lat - s.lat, 2) + power((d.lon - s.lon) * cos(radians(s.lat)), 2)) <= {MATCH_M}
        and greatest(jaro_winkler_similarity(d.n, s.n1), jaro_winkler_similarity(d.n, s.n2)) >= {NAME_SIM}
    """).df()


def bar_businesses(b: pd.DataFrame, live: pd.Timestamp) -> tuple[pd.DataFrame, pd.Series]:
    """New bar-only businesses, and the DOHMH business_ids that hold a bar/club licence."""
    bars = bar_premises()
    pairs = match_bars(bars, b)
    matched = pairs["premise_key"].unique()
    new = bars[~bars["premise_key"].isin(matched) & bars["open_date"].notna()].copy()
    new["closed"] = ~new["open_now"] & new["last_end"].notna()
    new["close_date"] = new["last_end"].where(new["closed"])
    new["end_date"] = new["close_date"].fillna(live)
    new["lifespan_days"] = (new["end_date"] - new["open_date"]).dt.days
    new = new[new["lifespan_days"] >= 0]
    new["business_id"] = "S" + new["premise_key"].astype(str)
    new["source"] = "sla"
    new["left_censored"] = new["open_date"] < pd.Timestamp("2012-07-06")
    print(f"bars: {len(bars):,} premises, {len(matched):,} match a DOHMH business, {len(new):,} added")
    out = new.drop(columns=["dba"]).rename(columns={"name": "dba", "address": "street"})[
        ["business_id", "dba", "street", "zip", "lat", "lon", "category", "open_date", "closed",
         "close_date", "end_date", "lifespan_days", "left_censored", "source"]]
    return out, pairs["business_id"]


def main() -> None:
    p = permits()
    live = p["end_date"].max()
    b = flag_relocations(merge_permits(p))
    b["category"] = "food_permit"
    bars, bar_ids = bar_businesses(b, live)
    b["has_bar_licence"] = b["business_id"].isin(bar_ids)
    out = pd.concat([b, bars], ignore_index=True)
    out["has_bar_licence"] = out["has_bar_licence"].fillna(out["source"] == "sla").astype(bool)
    out["relocated"] = out["relocated"].fillna(False).astype(bool)
    out["relocated_from"] = out["relocated_from"].fillna(False).astype(bool)
    out.to_parquet(OUT / "businesses.parquet", index=False)
    d = out[out["source"] == "dohmh"]
    print(f"permits {len(p):,} (never opened {p['likely_never_opened'].sum():,}) -> DOHMH businesses "
          f"{len(d):,} (multi-permit {(d['n_permits'] > 1).sum():,}); closed {d['closed'].mean():.1%}; "
          f"relocated {d['relocated'].sum():,}; total with bars {len(out):,}")


if __name__ == "__main__":
    main()
