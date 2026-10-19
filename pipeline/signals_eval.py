"""How useful are the signals? Prints the numbers quoted in data/notes/signals.md.

    .venv/bin/python pipeline/signals_eval.py

1. Closures in gaps: for each DOHMH CAMIS that left the data, the closure lies between its last
   inspection L and the first full copy U without it. A signal at the same BBL inside (L, U) is
   *attributable* when its name matches the DBA, or no other CAMIS at that BBL was plausibly open
   then. The latest attributable signal is a new last-seen date.
2. PPP/RRF records vs DOHMH CAMIS and SLA premises (BBL + time, with/without name agreement).
3. SLA on-premises bars: how many get dated evidence before 2015.
Writes data/raw/signals/camis_bbl.parquet (CAMIS -> BBL, life window) and
data/raw/signals/closure_tightening.parquet (per closed CAMIS: old/new last-seen, evidence source).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals_common import OUT, geocoder, norm_bbl, norm_name

ROOT = OUT.parents[2]
DOH = ROOT / "data" / "raw" / "dohmh"
GOV = ROOT / "data" / "raw" / "gov"
# copies that hold only part of the restaurants: absence there does not mean closed
PARTIAL = ("akkaluzny", "vsm1013", "miguel75an", "kylewbrown")
GAPS = {"2015-03..08": ("2015-03-01", "2015-08-02"), "2016-04..12": ("2016-04-07", "2016-12-09"),
        "2017-10..2018-07": ("2017-10-19", "2018-07-27"), "COVID 2020-03..2021-06": ("2020-03-16", "2021-06-30")}
NAMED = ("sba_ppp", "sba_rrf", "open_restaurants_insp")
STOP = {"RESTAURANT", "CAFE", "BAR", "PIZZA", "PIZZERIA", "DELI", "GRILL", "KITCHEN", "FOOD", "AND",
        "NY", "NYC", "OF", "NEW", "YORK", "INC", "CORP", "LLC", "THE", "GROCERY", "CHINESE", "BAKERY"}


def tokens(s) -> frozenset:
    if not isinstance(s, str):
        return frozenset()
    return frozenset(t for t in s.split() if len(t) > 2 and t not in STOP)


def name_match(a, b) -> bool:
    ta, tb = tokens(a), tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def snapshots() -> tuple[np.ndarray, pd.Timestamp]:
    m = pd.read_csv(DOH / "manifest.csv")
    m = m[m["snapshot_date"].notna() & ~m["id"].str.contains("|".join(PARTIAL))]
    s = np.sort(pd.to_datetime(m["snapshot_date"]).unique())
    return s, pd.Timestamp(s.max())


def camis_table() -> pd.DataFrame:
    u = pd.read_parquet(DOH / "union_inspections.parquet",
                        columns=["camis", "inspection_date", "dba", "boro", "building", "street",
                                 "zipcode", "bbl", "last_snapshot"])
    for col in ("inspection_date", "last_snapshot"):
        u[col] = pd.to_datetime(u[col])
    u = u[u["inspection_date"] > pd.Timestamp("1901-01-01")]
    u["bbl"] = norm_bbl(u["bbl"])
    u = u.sort_values("inspection_date")
    c = u.groupby("camis").agg(dba=("dba", "last"), boro=("boro", "last"), building=("building", "last"),
                               street=("street", "last"), zip=("zipcode", "last"),
                               bbl=("bbl", lambda s: s.dropna().mode().iat[0] if s.notna().any() else None),
                               first_insp=("inspection_date", "min"), last_insp=("inspection_date", "max"),
                               last_snap=("last_snapshot", "max")).reset_index()
    need = c["bbl"].isna() & c["building"].notna()
    g = geocoder()
    res = [g.one(h, s, z, b) for h, s, z, b in c.loc[need, ["building", "street", "zip", "boro"]]
           .itertuples(index=False)]
    c.loc[need, "bbl"] = norm_bbl(pd.Series([r.get("bbl") for r in res], index=c.index[need]))
    snaps, last = snapshots()
    nxt = np.searchsorted(snaps, c["last_snap"].values.astype("datetime64[ns]"), side="right")
    c["U"] = pd.NaT
    closed = (c["last_snap"] < last) & (nxt < len(snaps))
    c.loc[closed, "U"] = snaps[nxt[closed]]
    c["key"] = norm_name(c["dba"])
    print(f"CAMIS {len(c):,}; with BBL {c['bbl'].notna().mean():.1%}; closed (U known) {closed.sum():,}")
    c.drop(columns=["key"]).to_parquet(OUT / "camis_bbl.parquet", index=False)
    return c


def load_signals() -> pd.DataFrame:
    parts = []
    for f in sorted(OUT.glob("*.parquet")):
        if f.stem in ("camis_bbl", "closure_tightening", "nys_dos_entities") or f.stem.startswith("_"):
            continue
        x = pd.read_parquet(f)
        if "skipped" in x:  # Open Restaurants: inspector found no setup ("No Seating") -> not proof
            x = x[~x["skipped"].fillna(False)]
        parts.append(x[["source", "source_id", "event_date", "event_type", "name", "legal_name", "bbl"]])
    s = pd.concat(parts, ignore_index=True)
    s = s[s["bbl"].notna() & (s["event_type"] != "loan_forgiven")]
    s["key"] = norm_name(s["name"].fillna(s["legal_name"]))
    s["key2"] = norm_name(s["legal_name"])
    return s


def attributable(win: pd.DataFrame, s: pd.DataFrame, occ: pd.DataFrame) -> pd.DataFrame:
    """Signals at win.bbl strictly inside (lo, hi) that belong to win.camis: the name matches
    (named sources), or no other occupant (CAMIS or SLA on-prem premise) was plausibly there."""
    j = win[["camis", "bbl", "key", "lo", "hi"]].merge(s, on="bbl")
    j = j[(j["event_date"] > j["lo"]) & (j["event_date"] < j["hi"])]
    jj = j[["camis", "bbl", "event_date"]].drop_duplicates().merge(occ, on="bbl")
    jj = jj[(jj["o"] != jj["camis"]) & (jj["of"].isna() | (jj["event_date"] >= jj["of"]))
            & (jj["oU"].isna() | (jj["event_date"] <= jj["oU"]))]
    busy = set(zip(jj["camis"], jj["event_date"]))
    j["alone"] = [(a, b) not in busy for a, b in zip(j["camis"], j["event_date"])]
    # key_x = DOHMH DBA, key_y = signal name (DBA or franchise), key2 = signal legal name
    j["named"] = [name_match(a, b) or name_match(a, c2) for a, b, c2 in zip(j["key_x"], j["key_y"], j["key2"])]
    return j[j["alone"] | (j["source"].isin(NAMED) & j["named"])]


def occupants(c: pd.DataFrame, sla: pd.DataFrame) -> pd.DataFrame:
    """Everything that could have generated a signal at a BBL, with its plausible presence window."""
    a = c[["camis", "bbl", "first_insp", "U"]].rename(columns={"camis": "o", "first_insp": "of", "U": "oU"})
    a["of"] = a["of"] - pd.Timedelta(days=60)  # buildout / pre-permit inspection lead
    b = sla.dropna(subset=["bbl"])[["premise_key", "bbl", "start_date", "end_date"]].rename(
        columns={"premise_key": "o", "start_date": "of", "end_date": "oU"})
    b["of"] = b["of"].where(b["of"].notna(), pd.Timestamp("1900-01-01"))
    return pd.concat([a, b], ignore_index=True)


def closures(c: pd.DataFrame, s: pd.DataFrame, sla: pd.DataFrame) -> None:
    # DOB filings after the last inspection are mostly the *next* tenant's buildout -> not proof of life
    s = s[~s["source"].str.startswith("dob") & (s["event_type"] != "opened")]
    occ = occupants(c, sla)
    closed = c[c["U"].notna() & c["bbl"].notna()].copy()
    closed["win"] = (closed["U"] - closed["last_insp"]).dt.days
    a = attributable(closed.assign(lo=closed["last_insp"], hi=closed["U"]), s, occ)
    best = a.sort_values("event_date").groupby("camis").tail(1)[["camis", "event_date", "source", "event_type"]]
    out = closed.merge(best, on="camis", how="left").rename(columns={"event_date": "new_last_seen"})
    out["gain_days"] = (out["new_last_seen"] - out["last_insp"]).dt.days
    out["frac_closed"] = out["gain_days"] / out["win"]
    out.drop(columns=["key"]).to_parquet(OUT / "closure_tightening.parquet", index=False)
    print(f"\n== closures: {len(closed):,} closed CAMIS with BBL; median window L..U {closed['win'].median():.0f} d")
    for lab, (g0, g1) in {"all closures": ("1900-01-01", "2100-01-01"), **GAPS}.items():
        sub = out
        if lab != "all closures":
            sub = out[(out["last_insp"] < pd.Timestamp(g1)) & (out["U"] > pd.Timestamp(g0)) & (out["win"] > 120)]
        hit = sub["gain_days"] > 0
        print(f"  {lab:24s} n={len(sub):6,}  tightened {hit.sum():6,} ({hit.mean():.0%})  "
              f"median gain {sub.loc[hit, 'gain_days'].median():4.0f} d  "
              f"median share of window {sub.loc[hit, 'frac_closed'].median():.0%}")
    per = a.merge(closed[["camis", "win"]], on="camis")
    per = per[per["win"] > 120].groupby("source")["camis"].nunique()
    print("  CAMIS (window > 120 d) with >=1 attributable signal, by source:\n" + per.to_string())
    # placebo: same rule, 365 d after U (known gone) vs 365 d before L (known open)
    after = attributable(closed.assign(lo=closed["U"], hi=closed["U"] + pd.Timedelta(days=365)), s, occ)
    before = attributable(closed.assign(lo=closed["last_insp"] - pd.Timedelta(days=365),
                                        hi=closed["last_insp"]), s, occ)
    print("  placebo, share of closed CAMIS with an attributable signal: 365 d before L (open) vs "
          "365 d after U (gone):")
    for src in sorted(s["source"].unique()):
        fb = before.loc[before["source"] == src, "camis"].nunique() / len(closed)
        fa = after.loc[after["source"] == src, "camis"].nunique() / len(closed)
        print(f"    {src:22s} before {fb:6.1%}   after {fa:6.1%}")


def openings(c: pd.DataFrame, s: pd.DataFrame, sla: pd.DataFrame) -> None:
    """DOB food buildouts as opening evidence: lag from DOB milestone to DOHMH first inspection."""
    print("\n== openings: DOB food-related job at the BBL in the 3 years before the first inspection")
    d = s[s["source"].str.startswith("dob")]
    occ = occupants(c, sla)
    w = c[c["bbl"].notna()].copy()
    a = attributable(w.assign(lo=w["first_insp"] - pd.Timedelta(days=3 * 365), hi=w["first_insp"]), d, occ)
    for et in ("dob_filing", "dob_permit", "dob_signoff"):
        x = a[a["event_type"] == et].sort_values("event_date").groupby("camis").tail(1)
        lag = (x["lo"] + pd.Timedelta(days=3 * 365) - x["event_date"]).dt.days
        print(f"  {et:12s} CAMIS with one: {len(x):6,} ({len(x)/len(w):.0%})  lag to first inspection "
              f"median {lag.median():.0f} d, IQR {lag.quantile(.25):.0f}..{lag.quantile(.75):.0f}")
    ba = s[s["source"] == "nyc_business_acceleration"]
    m = ba.merge(w[["camis", "bbl", "key", "first_insp"]], on="bbl")
    m = m[[name_match(a, b) for a, b in zip(m["key_x"], m["key_y"])]]
    m = m.assign(lag=(m["first_insp"] - m["event_date"]).dt.days).sort_values("lag", key=abs).drop_duplicates("source_id")
    print(f"  NYC Business Acceleration: {len(ba):,} openings with BBL; BBL+name match a CAMIS {len(m):,} "
          f"({len(m)/max(len(ba),1):.0%}); DOHMH first inspection minus actual opening: median "
          f"{m['lag'].median():.0f} d, IQR {m['lag'].quantile(.25):.0f}..{m['lag'].quantile(.75):.0f}, "
          f"first inspection before opening {(m['lag'] < 0).mean():.0%}")
    early = w[w["first_insp"] < pd.Timestamp("2011-07-01")]
    e = a[a["camis"].isin(early["camis"])]
    print(f"  left-censored CAMIS (first inspection in data < 2011-07): {len(early):,}; with a DOB food job "
          f"before it: {e['camis'].nunique():,} (earliest year median "
          f"{e.groupby('camis')['event_date'].min().dt.year.median():.0f})")


def sla_premises() -> pd.DataFrame:
    sla = pd.read_parquet(GOV / "sla_licenses_nyc.parquet",
                          columns=["serial", "legal_name", "dba", "address", "zip", "county", "category",
                                   "on_premises", "start_date", "end_date", "premise_key",
                                   "premise_first_start"])
    sla = sla[sla["on_premises"].fillna(False)]
    from gov_geocode import split_address
    g = geocoder()
    hs = sla["address"].map(split_address)
    res = [g.one(h, st, z, b) for (h, st), z, b in zip(hs, sla["zip"], sla["county"].str.upper())]
    sla["bbl"] = norm_bbl(pd.Series([r.get("bbl") for r in res], index=sla.index))
    return sla


def covid_loans(c: pd.DataFrame, s: pd.DataFrame, sla: pd.DataFrame) -> None:
    print("\n== PPP / RRF vs DOHMH and SLA")
    for src in ("sba_ppp", "sba_rrf"):
        p = pd.read_parquet(OUT / f"{src}{'_food' if src == 'sba_ppp' else ''}.parquet")
        p = p[p["event_type"] != "loan_forgiven"].drop_duplicates("source_id")
        p["k1"], p["k2"] = norm_name(p["name"]), norm_name(p["legal_name"])
        n = len(p)
        geo = p["bbl"].notna()
        cc = c[["camis", "bbl", "key", "first_insp", "U"]]
        m = p.loc[geo, ["source_id", "bbl", "event_date", "k1", "k2"]].merge(cc, on="bbl")
        m = m[(m["event_date"] >= m["first_insp"] - pd.Timedelta(days=365)) & (m["U"].isna() | (m["event_date"] <= m["U"]))]
        m["nm"] = [name_match(k, a) or name_match(k, b) for k, a, b in zip(m["key"], m["k1"], m["k2"])]
        bbl_hit = set(m["source_id"])
        name_hit = set(m.loc[m["nm"], "source_id"])
        sl = sla[["bbl", "start_date", "end_date"]].dropna(subset=["bbl"])
        ms = p.loc[geo, ["source_id", "bbl", "event_date"]].merge(sl, on="bbl")
        ms = ms[(ms["start_date"].isna() | (ms["start_date"] <= ms["event_date"]))
                & (ms["end_date"].isna() | (ms["end_date"] >= ms["event_date"] - pd.Timedelta(days=365)))]
        sla_hit = set(ms["source_id"])
        ever = set(p.loc[geo].merge(cc[["bbl"]].drop_duplicates(), on="bbl")["source_id"])
        ids = set(p["source_id"])
        geo_ids = set(p.loc[geo, "source_id"])
        neither = geo_ids - bbl_hit - sla_hit
        print(f"  {src}: {n:,} records, geocoded {geo.mean():.0%}")
        print(f"    BBL+time matches a CAMIS {len(bbl_hit)/n:.0%} (also name agrees {len(name_hit)/n:.0%}); "
              f"SLA on-prem only {len(sla_hit - bbl_hit)/n:.0%}; neither {len(neither)/n:.0%} "
              f"(of which BBL never had any CAMIS {len(neither - ever)/n:.0%}); not geocoded {len(ids - geo_ids)/n:.0%}")
        if src == "sba_ppp":
            for lab, q in (("NAICS 7224 drinking places", p["naics"].astype(str).str.startswith("7224")),):
                sub = set(p.loc[q, "source_id"])
                print(f"    {lab}: {len(sub):,}; CAMIS match {len(sub & bbl_hit)/max(len(sub),1):.0%}, "
                      f"SLA-only {len((sub & sla_hit) - bbl_hit)/max(len(sub),1):.0%}")


def bars(c: pd.DataFrame, s: pd.DataFrame, sla: pd.DataFrame) -> None:
    print("\n== SLA on-premises bars: evidence before 2015")
    b = sla[sla["category"].isin(["bar_tavern", "club", "other_on_premises"])]
    prem = b.sort_values("start_date").groupby("premise_key").agg(
        bbl=("bbl", "first"), legal_name=("legal_name", "first"), start=("premise_first_start", "min")).reset_index()
    print(f"  bar/club premises {len(prem):,}; geocoded {prem['bbl'].notna().mean():.0%}; "
          f"known start < 2015: {(prem['start'] < '2015-01-01').sum():,}")
    pre = s[s["event_date"] < pd.Timestamp("2015-01-01")]
    for lab, q in (("311 bar/club noise or drinking", pre["event_type"].isin(["complaint_noise", "complaint_drinking"])),
                   ("311 any food/bar complaint", pre["source"].eq("311")),
                   ("DOB filing (bar/restaurant work)", pre["source"].str.startswith("dob")),
                   ("any located signal", pd.Series(True, index=pre.index))):
        bb = set(pre.loc[q, "bbl"])
        hit = prem["bbl"].isin(bb)
        new = hit & ~(prem["start"] < "2015-01-01")
        print(f"  {lab:34s} premises with evidence <2015: {hit.sum():6,} ({hit.mean():.0%}); "
              f"of these without a known pre-2015 SLA start: {new.sum():,}")
    dos = OUT / "nys_dos_entities.parquet"
    if dos.exists():
        d = pd.read_parquet(dos)
        f = d[d["event_type"] == "entity_formed"].groupby("name_key")["event_date"].min()
        k = norm_name(prem["legal_name"])
        fd = k.map(f)
        print(f"  DOS: legal entity found for {fd.notna().mean():.0%} of bar premises; formed <2015 for "
              f"{(fd < '2015-01-01').sum():,} ({(fd < '2015-01-01').mean():.0%}); of these without a known "
              f"pre-2015 SLA start: {((fd < '2015-01-01') & ~(prem['start'] < '2015-01-01')).sum():,}")
        lag = (prem["start"] - fd).dt.days
        print(f"  DOS formation -> SLA original issue lag (where both): median {lag.median():.0f} d, "
              f"IQR {lag.quantile(.25):.0f}..{lag.quantile(.75):.0f} d, n={lag.notna().sum():,}")


def main() -> None:
    c = camis_table()
    s = load_signals()
    print("signals with BBL by source:\n" + s.groupby("source")["event_date"].agg(["size", "min", "max"]).to_string())
    sla = sla_premises()
    closures(c, s, sla)
    openings(c, s, sla)
    covid_loans(c, s, sla)
    bars(c, s, sla)


if __name__ == "__main__":
    main()
