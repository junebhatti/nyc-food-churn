"""Combine bars evidence and measure pre-2015 start/end coverage.

Inputs
- data/raw/gov/extra/sla_bars_nyc_20160219.csv.gz   (hrvs-fxs2 NYC on-premises liquor, ~2016-02)
- data/raw/bars/cabaret_licenses.parquet            (bars_cabaret.py)
- data/raw/bars/cb_sla_items.parquet                (bars_cb.py) + data/raw/coverage/cb3_sla_items.parquet
- data/raw/gov/sla_licenses_nyc.parquet             (premise_key, BBL via geocode)

Outputs (data/raw/bars/)
- sla_snapshot_20160219.parquet  normalized + geocoded, matched to sla_licenses_nyc premise_key
- bars_pre2015_evidence.parquet  one row per (BBL, source) with the earliest/latest pre-2015 date
"""
from __future__ import annotations

import sys

import pandas as pd

from bars_common import OUT, ROOT
from bars_schema import finish

GOV = ROOT / "data" / "raw" / "gov"
BORO = {"NEW YORK": 1, "BRONX": 2, "KINGS": 3, "QUEENS": 4, "RICHMOND": 5}
CUT = pd.Timestamp("2015-01-01")


def geocode_df(d: pd.DataFrame) -> pd.DataFrame:
    from gov_geocode import PadGeocoder
    g = PadGeocoder()
    bname = d["boro"].map({1: "MANHATTAN", 2: "BRONX", 3: "BROOKLYN", 4: "QUEENS", 5: "STATEN ISLAND"})
    tmp = pd.DataFrame({"h": d["house"].fillna("").astype(str), "s": d["street"].fillna("").astype(str),
                        "z": d["zip"].fillna("").astype(str).str[:5], "b": bname})
    res = g.geocode_df(tmp.reset_index(drop=True), house="h", street="s", zip="z", boro="b")
    res.index = d.index
    return res


def snapshot_2016() -> pd.DataFrame:
    s = pd.read_csv(GOV / "extra" / "sla_bars_nyc_20160219.csv.gz", dtype=str)
    addr = s["Actual.Address.of.Premises..Address1."].fillna("").str.strip()
    hs = addr.str.extract(r"^(\d[\d\-]*[A-Z]?(?:\s1/2)?)\s+(.+)$")
    d = pd.DataFrame({
        "source": "sla_hrvs_20160219", "source_id": s["License.Serial.Number"], "serial": s["License.Serial.Number"],
        "premise_name": s["Premises.Name"], "dba": s["Doing.Business.As..DBA."], "address": addr,
        "house": hs[0], "street": hs[1], "zip": s["Zip"].str[:5], "boro": s["County.Name..Licensee."].map(BORO),
        "license_class": s["License.Class.Code"], "license_type": s["License.Type.Name"],
        "original_date": pd.to_datetime(s["License.Original.Issue.Date"], format="%m/%d/%Y", errors="coerce"),
        "effective_date": pd.to_datetime(s["License.Effective.Date"], format="%m/%d/%Y", errors="coerce"),
        "expiration_date": pd.to_datetime(s["License.Expiration.Date"], format="%m/%d/%Y", errors="coerce"),
        "snapshot_date": pd.Timestamp("2016-02-19"),
        "lat": pd.to_numeric(s["Latitude"], errors="coerce"), "lon": pd.to_numeric(s["Longitude"], errors="coerce"),
    })
    d["start_date"] = d["original_date"]
    geo = geocode_df(d)
    d["bbl"] = geo["bbl"].where(geo["status"].eq("ok"))
    d = finish(d)
    lic = pd.read_parquet(GOV / "sla_licenses_nyc.parquet", columns=["serial", "premise_key", "start_date"])
    lic["serial"] = lic["serial"].astype(str)
    d["in_sla_licenses"] = d["serial"].isin(lic["serial"])
    d["sla_premise_key"] = d["serial"].map(lic.drop_duplicates("serial").set_index("serial")["premise_key"])
    d.loc[d["sla_premise_key"].isna() & d["premise_key"].isin(lic["premise_key"]), "sla_premise_key"] = d["premise_key"]
    d.to_parquet(OUT / "sla_snapshot_20160219.parquet", index=False)
    print(f"snapshot 2016-02: {len(d)} rows; BBL {d['bbl'].notna().mean():.0%}; serial in sla_licenses "
          f"{d['in_sla_licenses'].mean():.0%}; premise matched {d['sla_premise_key'].notna().mean():.0%}", flush=True)
    return d


def sla_bbls() -> pd.DataFrame:
    """On-premises SLA licences with BBL (geocoded here from address) and their known start/end."""
    lic = pd.read_parquet(GOV / "sla_licenses_nyc.parquet")
    lic = lic[lic["on_premises"]].copy()
    hs = lic["address"].fillna("").str.extract(r"^(\d[\d\-]*[A-Z]?(?:\s1/2)?)\s+(.+)$")
    lic["house"], lic["street"] = hs[0], hs[1]
    lic["boro"] = lic["county"].str.upper().map({"NEW YORK": 1, "MANHATTAN": 1, "BRONX": 2, "KINGS": 3,
                                                 "BROOKLYN": 3, "QUEENS": 4, "RICHMOND": 5, "STATEN ISLAND": 5})
    geo = geocode_df(lic)
    lic["bbl"] = geo["bbl"].where(geo["status"].eq("ok"))
    return lic


def run() -> None:
    snap = snapshot_2016()
    cab = pd.read_parquet(OUT / "cabaret_licenses.parquet")
    cb = [pd.read_parquet(ROOT / "data" / "raw" / "coverage" / "cb3_sla_items.parquet")]
    if (OUT / "cb_sla_items.parquet").exists():
        cb.append(pd.read_parquet(OUT / "cb_sla_items.parquet"))
    cb = pd.concat(cb, ignore_index=True)
    cb["d"] = pd.to_datetime(cb["start_date"])
    lic = sla_bbls()

    ev = []
    # SLA 2016 snapshot: licences with pre-2015 original issue that sla_licenses_nyc lacks a start for
    s = snap[snap["original_date"] < CUT]
    ev.append(pd.DataFrame({"bbl": s["bbl"], "source": "sla_hrvs_20160219", "kind": "start",
                            "date": s["original_date"], "premise_key": s["sla_premise_key"].fillna(s["premise_key"])}))
    c = cab[cab["start_date"] < CUT]
    ev.append(pd.DataFrame({"bbl": c["bbl"], "source": "dcwp_cabaret", "kind": "start", "date": c["start_date"]}))
    c = cab[cab["end_date"] < CUT]
    ev.append(pd.DataFrame({"bbl": c["bbl"], "source": "dcwp_cabaret", "kind": "end", "date": c["end_date"]}))
    c = cb[cb["d"] < CUT]
    ev.append(pd.DataFrame({"bbl": c["bbl"], "source": c["source"].where(c["source"].eq("cb3_minutes"), "cb_other"),
                            "kind": "seen", "date": c["d"]}))
    ev = pd.concat(ev, ignore_index=True).dropna(subset=["bbl"])
    ev["bbl"] = ev["bbl"].astype(str).str.replace(r"\.0$", "", regex=True)
    agg = ev.groupby(["bbl", "source", "kind"]).agg(first=("date", "min"), last=("date", "max"),
                                                    n=("date", "size")).reset_index()
    agg.to_parquet(OUT / "bars_pre2015_evidence.parquet", index=False)

    # coverage: SLA on-premises premises (BBL) and whether they have pre-2015 evidence
    lic["bbl"] = lic["bbl"].astype("string")
    prem = lic.dropna(subset=["bbl"]).groupby("bbl").agg(known_start=("start_date", "min"),
                                                       known_end=("end_date", "min"))
    prem["known_pre2015_start"] = prem["known_start"] < CUT
    prem["known_pre2015_end"] = prem["known_end"] < CUT
    for src in ["sla_hrvs_20160219", "dcwp_cabaret", "cb3_minutes", "cb_other"]:
        prem[src] = prem.index.isin(agg.loc[agg["source"].eq(src), "bbl"])
    newstart = prem.index.isin(agg.loc[agg["kind"].isin(["start", "seen"]), "bbl"]) & ~prem["known_pre2015_start"]
    print(f"SLA on-premises BBLs: {len(prem):,}; known pre-2015 start {prem['known_pre2015_start'].sum():,}; "
          f"known pre-2015 end {prem['known_pre2015_end'].sum():,}", flush=True)
    for src in ["sla_hrvs_20160219", "dcwp_cabaret", "cb3_minutes", "cb_other"]:
        print(f"  {src}: on {prem[src].sum():,} SLA BBLs; new pre-2015 evidence for "
              f"{(prem[src] & ~prem['known_pre2015_start']).sum():,}", flush=True)
    print(f"  any new pre-2015 start/seen evidence: {newstart.sum():,} SLA BBLs", flush=True)
    allb = set(agg["bbl"])
    print(f"  BBLs with any pre-2015 bar evidence (all sources): {len(allb):,}; "
          f"not an SLA on-premises BBL at all: {len(allb - set(prem.index)):,}", flush=True)
    cbo = agg[agg["source"].eq("cb_other")]
    print(f"  cb_other lots {cbo['bbl'].nunique():,}; not in cb3: "
          f"{len(set(cbo['bbl']) - set(agg.loc[agg['source'].eq('cb3_minutes'), 'bbl'])):,}", flush=True)


if __name__ == "__main__":
    sys.exit(run())
