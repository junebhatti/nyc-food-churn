"""Business age (for Lindy-type analysis): opening date and earlier-start evidence per CAMIS.

open_date = first DOHMH inspection (validated: median -3 d vs actual opening, signals.md).
For CAMIS first inspected before 2011-07 (left-censored), earlier bounds:
  sla_start   = earliest SLA licence start of a linked entity (camis_entity_links, source sla)
  dos_formed  = NYS DOS formation date of a linked legal entity (an upper-bound-ish: entity may
                predate the premises; median lag formation -> SLA issue is 481 d)
  google_first_review = UCSD Google Local first review (matched CAMIS only)
earliest_evidence = min of the above and open_date.

Output: camis_age.parquet
"""
from __future__ import annotations

import pandas as pd

from ai_common import OUT, RAW, write_out


def build():
    b = pd.read_parquet(OUT / "camis_base.parquet", columns=["camis", "first_insp", "first_snap", "left_censored"])
    links = pd.read_parquet(OUT / "camis_entity_links.parquet", columns=["camis", "source", "legal_key", "date"])
    sla = links[links["source"].eq("sla")].groupby("camis")["date"].min().rename("sla_start")
    dos = pd.read_parquet(RAW / "signals" / "nys_dos_entities.parquet", columns=["name_key", "event_type", "event_date"])
    dos = dos[dos["event_type"].eq("entity_formed")].groupby("name_key")["event_date"].min()
    lk = links.drop_duplicates(["camis", "legal_key"]).copy()
    lk["dos_formed"] = lk["legal_key"].map(dos)
    dosc = lk.groupby("camis")["dos_formed"].min()
    g = pd.read_parquet(RAW / "ratings" / "google_local_nyc.parquet", columns=["camis", "first_review"])
    g = g.dropna(subset=["camis"]).groupby("camis")["first_review"].min()
    out = b.assign(open_date=b["first_insp"])
    out = out.merge(sla, on="camis", how="left").merge(dosc, on="camis", how="left")
    out["google_first_review"] = out["camis"].map(g)
    out["google_first_review"] = pd.to_datetime(out["google_first_review"], errors="coerce")
    cols = ["open_date", "sla_start", "dos_formed", "google_first_review"]
    for c in cols:
        out[c] = pd.to_datetime(out[c], errors="coerce").dt.tz_localize(None)
    out["earliest_evidence"] = out[cols].min(axis=1)
    out["earlier_bound_found"] = out["left_censored"] & (out["earliest_evidence"] < out["open_date"] - pd.Timedelta(days=180))
    write_out(out.drop(columns=["first_insp"]), "camis_age", "camis_base, camis_entity_links, signals/nys_dos_entities, "
              "ratings/google_local_nyc", "opening date and earlier-start evidence for left-censored CAMIS")


if __name__ == "__main__":
    build()
