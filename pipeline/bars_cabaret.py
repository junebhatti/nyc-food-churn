"""DCA/DCWP cabaret licences (NYC's pre-2017 licence for venues with dancing: clubs, lounges, bars).

Built from files the gov pull already saved (no network):
- data/raw/gov/dcwp_hist_licenses_food.parquet      (one row per licence: created, expires, status + date)
- data/raw/gov/dcwp_hist_license_apps_food.parquet  (one row per new/renewal application, 1999-2013)

Output: data/raw/bars/cabaret_licenses.parquet in the bars licence schema (see bars_schema.py).
The licence status "FAILED TO RENEW" / "OUT OF BUSINESS" / "SURRENDERED" + status date is end evidence.
"""
from __future__ import annotations

import pandas as pd

from bars_common import OUT, ROOT
from bars_schema import finish

GOV = ROOT / "data" / "raw" / "gov"
END_STATUS = {"FAILED TO RENEW", "OUT OF BUSINESS", "SURRENDERED", "DENIED-RENEWAL", "BUSINESS PADLOCKED"}


def run() -> pd.DataFrame:
    lic = pd.read_parquet(GOV / "dcwp_hist_licenses_food.parquet")
    lic = lic[lic["business_code_description"].str.contains("CABARET", na=False)].copy()
    apps = pd.read_parquet(GOV / "dcwp_hist_license_apps_food.parquet")
    apps = apps[apps["license_category"].eq("CABARET")].copy()
    if lic.empty or apps.empty:
        raise RuntimeError("no cabaret rows in the DCWP files (gov pull changed?)")
    apps["activity_date"] = pd.to_datetime(apps["activity_date"])
    ok = apps[apps["activity"].eq("APPROVED")]
    first_app = ok.groupby("license_number")["activity_date"].min()
    last_app = ok.groupby("license_number")["activity_date"].max()

    d = pd.DataFrame({
        "source": "dcwp_cabaret",
        "source_id": lic["dca_license_number"].astype(str),
        "serial": lic["dca_license_number"].astype(str),
        "premise_name": lic["business_name"],
        "dba": lic["business_name2"],
        "house": lic["address_building"],
        "street": lic["address_street_name"].str.replace(r"\s+", " ", regex=True),
        "zip": lic["address_zip"],
        "boro": lic["borough_code"],
        "license_class": "CABARET",
        "license_type": "dcwp_cabaret",
        "original_date": pd.to_datetime(lic["license_creation_date"]),
        "expiration_date": pd.to_datetime(lic["license_expiration_date"]),
        "status": lic["license_status"],
        "status_date": pd.to_datetime(lic["license_status_date"]),
        "lat": lic["latitude"], "lon": lic["longitude"], "bbl": lic["bbl"],
    })
    d["address"] = d["house"].fillna("") + " " + d["street"].fillna("")
    d["first_app"] = d["serial"].map(first_app)
    d["last_app"] = d["serial"].map(last_app)
    d["start_date"] = d[["original_date", "first_app"]].min(axis=1)
    ended = d["status"].isin(END_STATUS)
    d["end_date"] = d["status_date"].where(ended)
    d.loc[ended & d["end_date"].isna(), "end_date"] = d["expiration_date"]
    d["snapshot_date"] = pd.NaT
    d = finish(d)
    path = OUT / "cabaret_licenses.parquet"
    d.to_parquet(path, index=False)
    print(f"cabaret: {len(d)} licences, {d['bbl'].notna().mean():.0%} with BBL, "
          f"{d['end_date'].notna().sum()} with an end date -> {path.name}", flush=True)
    return d


if __name__ == "__main__":
    run()
