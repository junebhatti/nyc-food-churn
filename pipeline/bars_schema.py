"""Common column set for bars licence files in data/raw/bars/ (cabaret, SLA snapshots).

Community-board agenda items use the coverage cb3_sla_items schema instead (see bars_cb.py).
"""
from __future__ import annotations

import re

import pandas as pd

COLS = ["source", "source_id", "serial", "premise_name", "dba", "address", "house", "street", "zip", "boro",
        "license_class", "license_type", "original_date", "effective_date", "expiration_date", "status",
        "status_date", "start_date", "end_date", "snapshot_date", "lat", "lon", "bbl", "premise_key"]
DATES = ["original_date", "effective_date", "expiration_date", "status_date", "start_date", "end_date",
         "snapshot_date"]


def _norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def premise_key(name, address, zip_) -> str:
    """Same construction as sla_licenses_nyc.premise_key: NAME|ADDRESS|ZIP with non-alnum removed."""
    return f"{_norm(name)}|{_norm(address)}|{str(zip_ or '')[:5]}"


def finish(d: pd.DataFrame) -> pd.DataFrame:
    for c in COLS:
        if c not in d:
            d[c] = None
    for c in DATES:
        d[c] = pd.to_datetime(d[c], errors="coerce")
    d["bbl"] = d["bbl"].map(lambda x: str(int(float(x))) if pd.notna(x) and str(x).strip() else None)
    d["boro"] = pd.to_numeric(d["boro"], errors="coerce").astype("Int64")
    d["lat"] = pd.to_numeric(d["lat"], errors="coerce")
    d["lon"] = pd.to_numeric(d["lon"], errors="coerce")
    if d["premise_key"].isna().all():
        d["premise_key"] = [premise_key(n, a, z) for n, a, z in zip(d["premise_name"], d["address"], d["zip"])]
    rest = [c for c in d.columns if c not in COLS]
    return d[COLS + rest]
