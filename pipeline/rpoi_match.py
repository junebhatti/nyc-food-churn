"""Match research-POI venues to DOHMH CAMIS and SLA premises, then measure how
much they tighten DOHMH closure dates.

Matching (same rule as crosscheck_recent.py / ratings_common.match_geo): best
normalized-name Jaro-Winkler >= 0.85 within 80 m. Venues without a name are not
matched.

Closure window per DOHMH CAMIS: (last snapshot that lists it, next snapshot that
does not). PARTIAL copies are skipped as "next" snapshots; DERIVED copies are
full CAMIS lists and count. A research activity date inside that window moves
the last-seen-open date later ("tightened"); one after the window's end
contradicts DOHMH (wrong match, successor at the same spot, or stale venue).

Outputs (data/raw/research_poi/):
  rpoi_venue_match.parquet   source, venue_id, camis, match_sim, match_m, sla_premise_key, sla_sim
  rpoi_closure_evidence.parquet  per closed CAMIS: window, research last date, verdict
"""
from __future__ import annotations

import glob

import pandas as pd

import rpoi_common as rc

LIVE = "2026-10-16"
MAX_M, NAME_SIM = 80, 0.85
GAPS = [  # named multi-month gaps between DOHMH pulls (from data/notes/dohmh_gaps.md)
    ("2015-03..08", "2015-03-01", "2015-08-02"),
    ("2016-04..09", "2016-04-07", "2016-09-27"),
    ("2018-04..07", "2018-04-06", "2018-07-27"),
    ("2018-11..2019-05", "2018-11-20", "2019-05-12"),
    ("2020-04..2021-06 COVID", "2020-01-03", "2021-05-29"),
    ("2021-09..2022-03", "2021-09-30", "2022-03-23"),
]


def load_venues(c) -> None:
    files = sorted(glob.glob(str(rc.OUT / "*_venues.parquet")))
    if not files:
        raise RuntimeError("no *_venues.parquet in research_poi; run the fetch steps first")
    c.execute(f"""
    create or replace table rv as
    select source, venue_id, name, category, lat, lon, first_date, last_date, n_activity
    from read_parquet({files}, union_by_name=true)""")
    print(c.execute("select source, count(*) n, count(name) named, min(first_date), max(last_date) "
                    "from rv group by 1 order by 1").df().to_string(index=False))


def match_sla(c) -> pd.DataFrame:
    return c.execute(f"""
    with s as (select source, venue_id, norm(name) nn, lat, lon from rv where name is not null),
    l as (select premise_key, norm(coalesce(dba, legal_name)) dn, norm(legal_name) ln, lat, lon
          from '{rc.RAW / 'gov' / 'sla_licenses_nyc.parquet'}' where lat is not null),
    p as (
      select s.source, s.venue_id, l.premise_key,
             greatest(jaro_winkler_similarity(s.nn, l.dn), jaro_winkler_similarity(s.nn, coalesce(l.ln, ''))) sim
      from s join l on l.lat between s.lat - 0.0008 and s.lat + 0.0008
                   and l.lon between s.lon - 0.0011 and s.lon + 0.0011
      where s.nn <> '' and dist_m(s.lat, s.lon, l.lat, l.lon) <= {MAX_M})
    select source, venue_id, arg_max(premise_key, sim) sla_premise_key, max(sim) sla_sim
    from p where sim >= {NAME_SIM} group by 1, 2""").df()


def snapshots() -> list[str]:
    m = pd.read_csv(rc.RAW / "dohmh" / "manifest.csv")
    m = m[~m.notes.fillna("").str.startswith("PARTIAL")]
    return sorted(m.snapshot_date.dropna().astype(str).unique())


def load_dohmh(c) -> None:
    """One row per CAMIS from analysis_inputs/camis_base: DOHMH coords, else the
    PAD lot centroid (pre-2019 copies have addresses only)."""
    c.execute(f"""
    create or replace table dohmh as
    select camis, dba, norm(dba) nname,
           coalesce(try_cast(lat as double), lot_lat) lat, coalesce(try_cast(lon as double), lot_lon) lon,
           geo_src, first_insp::date first_insp, last_insp::date last_insp, last_snap::date last_snap
    from '{rc.RAW / 'analysis_inputs' / 'camis_base.parquet'}'
    where coalesce(try_cast(lat as double), lot_lat) between 40.4 and 41.0""")


def match_dohmh(c) -> pd.DataFrame:
    """Best CAMIS per venue: name JW >= 0.85 within 80 m. Ties on similarity
    (to 2 decimals) go to the CAMIS whose DOHMH life overlaps the activity most."""
    return c.execute(f"""
    with s as (select source, venue_id, norm(name) nn, lat, lon, first_date, last_date
               from rv where name is not null),
    p as (
      select s.source, s.venue_id, d.camis, jaro_winkler_similarity(s.nn, d.nname) sim,
             dist_m(s.lat, s.lon, d.lat, d.lon) m,
             greatest(0, date_diff('day', greatest(s.first_date, d.first_insp - 365),
                                          least(s.last_date, d.last_snap + 365))) overlap
      from s join dohmh d on d.lat between s.lat - 0.0008 and s.lat + 0.0008
                         and d.lon between s.lon - 0.0011 and s.lon + 0.0011
      where s.nn <> '' and d.nname <> '')
    select source, venue_id, camis, round(sim, 3) match_sim, round(m) match_m from p
    where m <= {MAX_M} and sim >= {NAME_SIM}
    qualify row_number() over (partition by source, venue_id
                               order by round(sim, 2) desc, overlap desc, m) = 1""").df()


def run() -> None:
    c = rc.connect()
    load_venues(c)
    load_dohmh(c)
    dm = match_dohmh(c)
    sm = match_sla(c)
    v = c.execute("select * from rv").df().merge(dm, on=["source", "venue_id"], how="left").merge(
        sm, on=["source", "venue_id"], how="left")
    v.to_parquet(rc.OUT / "rpoi_venue_match.parquet", index=False)

    print("\n== Match rates (named venues) ==")
    named = v[v.name.notna()].copy()
    named["rest"] = named.category.fillna("").str.contains(
        r"(?i)restaurant|pizz|diner|deli|bakery|caf|coffee|sandwich|burger|food truck|joint")
    g = named.groupby("source")
    t = pd.DataFrame({
        "venues": g.size(), "dohmh": g.camis.apply(lambda s: s.notna().mean()),
        "sla": g.sla_premise_key.apply(lambda s: s.notna().mean()),
        "either": g.apply(lambda x: (x.camis.notna() | x.sla_premise_key.notna()).mean()),
        "dohmh_restaurantlike": named[named.rest].groupby("source").camis.apply(lambda s: s.notna().mean()),
        "not_in_dohmh_restaurantlike": named[named.rest].groupby("source").camis.apply(lambda s: s.isna().sum()),
        "not_in_dohmh_other": named[~named.rest].groupby("source").camis.apply(lambda s: s.isna().sum())})
    print(t.round(3).to_string())
    print(f"  distinct CAMIS matched: {v.camis.nunique():,}")

    # ---- closure tightening ----
    snaps = snapshots()
    c.register("snaps", pd.DataFrame({"s": pd.to_datetime(snaps).date}))
    c.register("vm", v[v.camis.notna()][["camis", "source", "last_date", "first_date"]])
    c.register("gaps", pd.DataFrame(GAPS, columns=["gap", "g0", "g1"]))
    # Window gap label: the (last_snap, next_snap) interval overlaps a named gap.
    ev = c.execute(f"""
    with closed as (
      select camis, first_insp, last_insp, last_snap,
             (select min(s) from snaps where s > last_snap) next_snap
      from dohmh where last_snap < '{LIVE}'),
    r as (select camis, max(last_date) r_last, min(first_date) r_first,
                 string_agg(distinct source, ',') sources from vm group by 1)
    select c.*, r.r_last, r.r_first, r.sources,
           case when r.r_last is null then 'no research match'
                when r.r_last >= c.next_snap then 'after window (contradicts)'
                when r.r_last > c.last_snap then 'later than last snapshot'
                when r.r_last > c.last_insp then 'after last inspection only'
                else 'no later evidence' end verdict,
           case when r.r_last > c.last_insp and r.r_last < c.next_snap
                then date_diff('day', c.last_insp, r.r_last) end gain_vs_insp_days,
           case when r.r_last > c.last_snap and r.r_last < c.next_snap
                then date_diff('day', c.last_snap, r.r_last) end gain_vs_snap_days,
           coalesce((select min(g.gap) from gaps g
                     where c.last_snap < g.g1::date and c.next_snap > g.g0::date
                       and date_diff('day', c.last_snap, c.next_snap) > 60),
                    'not a named gap') window_gap,
           (select min(g.gap) from gaps g
             where r.r_last between g.g0::date and g.g1::date and r.r_last > c.last_insp
               and r.r_last < c.next_snap) evidence_in_gap
    from closed c left join r using (camis)""").df()
    ev.to_parquet(rc.OUT / "rpoi_closure_evidence.parquet", index=False)
    print(f"\n== DOHMH closures (CAMIS not in live {LIVE}, with coords): {len(ev):,}; "
          f"with a research match: {(ev.verdict != 'no research match').sum():,} ==")
    print(ev.verdict.value_counts().to_string())
    m = ev[ev.verdict != "no research match"]
    tab = m.pivot_table(index="window_gap", columns="verdict", values="camis", aggfunc="count", fill_value=0)
    tab.insert(0, "closures", ev.groupby("window_gap").size())
    tab["median_gain_vs_snap_d"] = m[m.verdict == "later than last snapshot"].groupby("window_gap").gain_vs_snap_days.median()
    print("\nBy the gap the DOHMH drop-out window falls in:")
    print(tab.to_string())
    print("\nNew last-seen-open date (after last inspection, before drop-out) falling inside a named gap:")
    print(ev.evidence_in_gap.value_counts().to_string())
    later = ev[ev.verdict.isin(["later than last snapshot", "after last inspection only"])]
    print(f"\nLater last-seen than last inspection: {len(later):,} CAMIS, median +{later.gain_vs_insp_days.median():.0f} d; "
          f"by year of new date: {pd.to_datetime(later.r_last).dt.year.value_counts().sort_index().to_dict()}")
    print("by source:", later.sources.str.split(",").explode().value_counts().to_dict())
    early = ev[ev.r_first < ev.first_insp]
    print(f"Research first-seen before first DOHMH inspection: {len(early):,} closed CAMIS "
          f"(median {(pd.to_datetime(early.first_insp) - pd.to_datetime(early.r_first)).dt.days.median():.0f} d)")


if __name__ == "__main__":
    run()
