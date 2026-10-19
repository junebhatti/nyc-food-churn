"""Restaurant Revitalization Fund (RRF) design table for analysis D.

No public business-level list of unfunded RRF applicants exists (see analysis_inputs.md: GAO-22-105442,
SBA RRF report 2021-06-30). This builds the best available alternative:

  risk set   = CAMIS alive at the RRF application window (first seen before 2021-05-03 and still
               seen at/after the 2021-05-29 copy, or with PPP/Open Restaurants proof of life in 2021)
  treated    = linked to an SBA RRF recipient record at the same BBL (name >= 0.8 or only CAMIS alive)
  eligible   = not a wiki chain with > 20 NYC locations (RRF excluded affiliates with > 20 locations)
  applicant proxies: PPP first draw, PPP second draw (PPS; required a >= 25% revenue drop)
  ny_calibration: NY State had 27,643 RRF applications, 9,775 funded (SBA, through 2021-06-30)

Outputs: camis_rrf_design.parquet, rrf_aggregates.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai_common import OUT, RAW, norm_name, write_out
from ai_operators import sim

WINDOW_OPEN = pd.Timestamp("2021-05-03")


def link_all(src: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    from signals_common import norm_bbl
    s = src.copy()
    s["bbl"] = norm_bbl(s["bbl"])
    s["rid"] = range(len(s))
    s["name_key"] = s["legal_name"].map(norm_name)
    s["dba2"] = s["name"].map(norm_name)
    b = base.dropna(subset=["bbl"])
    m = s.merge(b[["camis", "bbl", "dba_key", "start", "end"]], on="bbl")
    m = m[(m["event_date"] >= m["start"] - pd.Timedelta(days=90)) & (m["event_date"] <= m["end"] + pd.Timedelta(days=540))]
    m["n_alive"] = m.groupby("rid")["camis"].transform("nunique")
    m["s"] = [max(sim(a, c), sim(d, c)) for a, d, c in zip(m["name_key"], m["dba2"], m["dba_key"])]
    m = m[(m["s"] >= 0.8) | (m["n_alive"] == 1)]
    return m.sort_values("s", ascending=False).drop_duplicates("rid")


def build():
    base = pd.read_parquet(OUT / "camis_base.parquet")
    base["start"] = base["first_insp"].fillna(base["first_snap"])
    base["end"] = base[["last_insp", "last_snap"]].max(axis=1)
    rrf = pd.read_parquet(RAW / "signals" / "sba_rrf.parquet")
    ppp = pd.read_parquet(RAW / "signals" / "sba_ppp_food.parquet")
    ppp = ppp[ppp["event_type"].eq("loan_approved")]
    rl = link_all(rrf, base)
    pl = link_all(ppp, base)
    r = rl.groupby("camis").agg(rrf_amount=("amount", "sum"), rrf_date=("event_date", "min"),
                                rrf_type=("restaurant_type", "first"), rrf_link_sim=("s", "max")).reset_index()
    p = pl.groupby("camis").agg(ppp_first_draw=("draw", lambda x: (x == "PPP").any()),
                                ppp_second_draw=("draw", lambda x: (x == "PPS").any()),
                                ppp_amount=("amount", "sum"), ppp_jobs=("jobs", "max")).reset_index()
    ch = pd.read_parquet(OUT / "camis_chain.parquet", columns=["camis", "wiki_chain", "nyc_max_concurrent"])
    d = base[["camis", "start", "end", "closed", "boro", "nta2020", "bbl"]].merge(r, on="camis", how="left")
    d = d.merge(p, on="camis", how="left").merge(ch, on="camis", how="left")
    ora = pd.read_parquet(RAW / "signals" / "open_restaurants_insp.parquet", columns=["bbl", "event_date", "skipped"])
    from signals_common import norm_bbl
    ora = ora[~ora["skipped"].fillna(False).astype(bool) & (ora["event_date"].dt.year == 2021)]
    ora_bbl = set(norm_bbl(ora["bbl"]).dropna())
    alive_obs = (d["start"] < WINDOW_OPEN) & (d["end"] >= pd.Timestamp("2021-05-29"))
    proof = (d["start"] < WINDOW_OPEN) & (d["end"] >= pd.Timestamp("2020-03-01")) & (
        d["ppp_second_draw"].fillna(False).astype(bool) | d["rrf_amount"].notna() | d["bbl"].isin(ora_bbl))
    d["alive_at_window"] = alive_obs | proof
    d["rrf_recipient"] = d["rrf_amount"].notna()
    d["rrf_ineligible_chain"] = d["wiki_chain"].fillna(False).astype(bool) & (d["nyc_max_concurrent"] > 20)
    for c in ("ppp_first_draw", "ppp_second_draw"):
        d[c] = d[c].fillna(False).astype(bool)
    d["days_survived_after_window"] = (d["end"] - WINDOW_OPEN).dt.days
    write_out(d.drop(columns=["bbl"]), "camis_rrf_design", "signals/sba_rrf + signals/sba_ppp_food + camis_base",
              "risk set/treatment/applicant proxies for RRF; no unfunded-applicant list exists publicly")
    agg = pd.DataFrame([
        ("US", "applications", 278304, "SBA RRF Report through 2021-06-30"),
        ("US", "approved", 101004, "SBA RRF Report through 2021-06-30"),
        ("NY", "applications", 27643, "SBA RRF Report through 2021-06-30"),
        ("NY", "approved", 9775, "SBA RRF Report through 2021-06-30"),
        ("US", "applications_total_final", 283741, "GAO-22-105442 Table 6 (read by research subagent; gao.gov blocks scripted PDF download, not re-verified)"),
        ("US", "funded_final", 100572, "GAO-22-105442 Table 6 (read by research subagent; gao.gov blocks scripted PDF download, not re-verified)"),
        ("US", "eligible_unfunded", 150166, "GAO-22-105442 Table 6 (read by research subagent; gao.gov blocks scripted PDF download, not re-verified)"),
        ("US", "denied", 33003, "GAO-22-105442 (not re-verified)"),
        ("US", "priority_approved_rescinded", 2964, "GAO-22-105442 note 16 (not re-verified)"),
        ("NYC", "recipients_in_sba_file", int(len(rrf)), "signals/sba_rrf (data.ny.gov 3pjx-bgty)"),
        ("NYC", "recipients_linked_to_camis", int(d["rrf_recipient"].sum()), "this script"),
        ("NYC", "camis_alive_at_window", int(d["alive_at_window"].sum()), "this script"),
    ], columns=["geo", "measure", "value", "source"])
    write_out(agg, "rrf_aggregates", "SBA, GAO, this script", "aggregate counts for calibration", fmt="csv")


if __name__ == "__main__":
    build()
