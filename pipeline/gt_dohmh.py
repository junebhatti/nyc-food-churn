"""DOHMH side of the ground-truth check: one row per CAMIS and per *business*.

CAMIS window (same definition as signals_eval.py):
    F = first real inspection, L = last real inspection,
    first_seen = first copy listing the CAMIS at all (often with a 1900-01-01 "not yet inspected" row),
    U = first FULL copy after the CAMIS's last snapshot (NaT = still in the latest copy).
Business = CAMIS with the same normalised name at the same building + street (a new permit
for the same place, e.g. an ownership change). Business L/U come from its last CAMIS and
F from its first, so a permit change is not counted as a closure.

The union and manifest are re-read on every call (they may be rebuilt by another agent).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from gt_common import RAW, mnorm, norm

DOH = RAW / "dohmh"
# copies holding only part of the restaurants: absence there does not mean closed
PARTIAL_IDS = ("akkaluzny", "vsm1013", "miguel75an", "kylewbrown", "lehman_", "residentmario", "tzstatsads")
BORO = {"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN", "4": "QUEENS", "5": "STATEN ISLAND"}
SUFFIX = {"RESTAURANT", "RESTAURANTS", "REST", "INC", "LLC", "CORP", "NYC", "NY", "BAR", "CAFE",
          "PIZZERIA", "KITCHEN", "GRILL", "LOUNGE", "THE", "AND", "CO", "BAKERY", "DELI", "SHOP",
          "TAVERN", "PUB", "EATERY", "BISTRO", "TRATTORIA", "RISTORANTE", "CORPORATION", "LTD"}


def full_snapshots() -> np.ndarray:
    m = pd.read_csv(DOH / "manifest.csv")
    notes = m["notes"].fillna("").str.upper()
    full = (m["snapshot_date"].notna() & ~m["id"].str.contains("|".join(PARTIAL_IDS))
            & ~notes.str.contains("PARTIAL|DERIVED"))
    return np.sort(pd.to_datetime(m.loc[full, "snapshot_date"]).unique())


def variants(dba: str) -> set[str]:
    """Normalised name and its core without generic suffix/prefix words."""
    n = mnorm(dba)
    out = {n}
    toks = n.split()
    if toks and toks[0] == "THE":
        toks = toks[1:]
        out.add(" ".join(toks))
    core = list(toks)
    while core and core[-1] in SUFFIX:
        core.pop()
    if core:
        out.add(" ".join(core))
    return {v for v in out if v}


def camis_table() -> pd.DataFrame:
    u = pd.read_parquet(DOH / "union_inspections.parquet",
                        columns=["camis", "inspection_date", "dba", "boro", "building", "street",
                                 "zipcode", "latitude", "longitude", "bbl", "first_snapshot", "last_snapshot"])
    u["inspection_date"] = pd.to_datetime(u["inspection_date"])
    u["last_snapshot"] = pd.to_datetime(u["last_snapshot"])
    u["first_snapshot"] = pd.to_datetime(u["first_snapshot"])
    real = u[u["inspection_date"] > pd.Timestamp("1901-01-01")]
    # some copies hold streets like "3 avenue 157 , NY, US": drop the trailing house number / city
    u["street"] = u["street"].str.replace(r"\s+\d+[A-Za-z]?\s*,.*$", "", regex=True).str.replace(r",.*$", "", regex=True).str.strip()
    u = u.sort_values("inspection_date")
    lat = pd.to_numeric(u["latitude"], errors="coerce")
    lon = pd.to_numeric(u["longitude"], errors="coerce")
    u["lat"], u["lon"] = lat.where(lat.between(40.4, 41.0)), lon.where(lat.between(40.4, 41.0))
    c = u.groupby("camis").agg(dba=("dba", "last"), dba_first=("dba", "first"), boro=("boro", "last"),
                               building=("building", "last"), street=("street", "last"),
                               zip=("zipcode", "last"), lat=("lat", "last"), lon=("lon", "last"),
                               bbl=("bbl", "last"), first_seen=("first_snapshot", "min"),
                               last_snap=("last_snapshot", "max"))
    rr = real.groupby("camis")["inspection_date"].agg(F="min", L="max")
    c = c.join(rr).reset_index()
    snaps = full_snapshots()
    latest = pd.Timestamp(snaps.max())
    nxt = np.searchsorted(snaps, c["last_snap"].values.astype("datetime64[ns]"), side="right")
    closed = (c["last_snap"] < latest) & (nxt < len(snaps))
    c["U"] = pd.NaT
    c.loc[closed, "U"] = snaps[nxt[closed.values]]
    c["boro"] = c["boro"].astype(str).str.upper().map(lambda b: BORO.get(b, b))
    c["zip"] = c["zip"].astype(str).str[:5]
    c["addr_key"] = (c["building"].fillna("").map(norm).str.replace(" ", "") + "|"
                     + c["street"].fillna("").map(norm))
    c["name_key"] = c["dba"].map(lambda s: min(variants(s) or {""}, key=len) if isinstance(s, str) else "")
    c.attrs["latest_snapshot"] = latest
    return c


def business_table(c: pd.DataFrame) -> pd.DataFrame:
    """Collapse CAMIS -> business (same name core at the same address)."""
    c = c.sort_values("F")
    key = c["name_key"].where(c["name_key"] != "", "CAMIS:" + c["camis"].astype(str))
    c["biz"] = c.assign(k=key).groupby(["k", "addr_key"]).ngroup()
    g = c.groupby("biz")
    b = g.agg(camis_list=("camis", list), n_camis=("camis", "size"), F=("F", "min"), L=("L", "max"),
              first_seen=("first_seen", "min"),
              last_snap=("last_snap", "max"), dba=("dba", "last"), zip=("zip", "last"),
              boro=("boro", "last"), lat=("lat", "last"), lon=("lon", "last"), bbl=("bbl", "last"),
              building=("building", "last"), street=("street", "last"))
    # U of the business = U of the CAMIS seen last (NaT if that one is still listed)
    last = c.loc[g["last_snap"].idxmax()].set_index("biz")["U"]
    b["U"] = last
    return b.reset_index()
