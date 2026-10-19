"""Owner / operator links: CAMIS -> legal business entity -> operator group.

Entity records (legal name + premises BBL + date) come from data already on disk (read-only):
  SLA licences (legal_name, dba, address -> PAD BBL, start/end), Open Restaurants applications
  (legal_business_name, dba, bbl), Open Restaurants inspections, PPP, RRF, Dining Out NYC,
  DCWP historical licences.
Only ENTITY names are kept (INC/LLC/CORP/LTD/LP/...). Records whose legal name is a person
(sole proprietors) are dropped before linking: no individual's data is compiled.

Linking a record to a CAMIS: same BBL, CAMIS alive within +-365 d of the record date, and
either DBA similarity >= 0.80 (rule=name) or the CAMIS is the only one alive at that BBL then
(rule=only_alive). Only rule=name links are used to build operator groups.

Operator group = connected component over (legal entity key) shared by CAMIS, plus
(non-chain) DBA brand key shared by CAMIS at >= 2 addresses (local multi-unit brands).
Wikipedia/strict chains are excluded from brand grouping (franchisees are separate operators).
If entity_process_groups.parquet exists (ai_dos_process.py), entities sharing a non-hub DOS
service-of-process address (2-25 linked food entities, <=25 entities of any kind) are also joined.

Outputs: camis_entity_links.parquet, camis_operator.parquet
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from ai_common import OUT, RAW, log, norm_name, write_out

ENTITY_RE = re.compile(r"\b(INC|INCORPORATED|LLC|L\.L\.C|L L C|CORP|CORPORATION|LTD|LP|LLP|PLLC|CO|COMPANY|"
                       r"HOLDINGS|GROUP|ENTERPRISES|ASSOCIATES|PARTNERS|TRUST|ASSOC)\b\.?", re.I)


def is_entity(s) -> bool:
    return isinstance(s, str) and bool(ENTITY_RE.search(s))


def sim(a, b) -> float:
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0 if min(len(a), len(b)) >= 4 else 0.0
    return SequenceMatcher(None, a, b).ratio()


def records() -> pd.DataFrame:
    from gov_geocode import PadGeocoder
    from signals_common import norm_bbl

    out = []
    sla = pd.read_parquet(RAW / "gov" / "sla_licenses_nyc.parquet",
                          columns=["serial", "legal_name", "dba", "address", "zip", "start_date", "end_date",
                                   "on_premises", "category"])
    sla = sla[sla["legal_name"].map(is_entity)].copy()
    g = PadGeocoder()
    from gov_geocode import split_address
    hs = [split_address(a) if isinstance(a, str) else ("", "") for a in sla["address"]]
    sla["house"] = [h for h, _ in hs]
    sla["street"] = [s for _, s in hs]
    res = g.geocode_df(sla, "house", "street", zip="zip")
    sla["bbl"] = norm_bbl(res["bbl"]) if "bbl" in res else None
    log.info("SLA entity licences %d, PAD BBL %.1f%%", len(sla), 100 * sla["bbl"].notna().mean())
    sla["date"] = sla["start_date"].fillna(sla["end_date"])
    out.append(sla.assign(source="sla")[["source", "legal_name", "dba", "bbl", "date", "end_date"]])

    ora = pd.read_parquet(RAW / "gov" / "open_restaurants_apps.parquet",
                          columns=["legal_business_name", "doing_business_as_dba", "restaurant_name", "bbl",
                                   "time_of_submission"])
    ora = ora.rename(columns={"legal_business_name": "legal_name", "time_of_submission": "date"})
    ora["dba"] = ora["doing_business_as_dba"].where(~ora["doing_business_as_dba"].map(is_entity),
                                                    ora["restaurant_name"])
    out.append(ora.assign(source="open_rest_app")[["source", "legal_name", "dba", "bbl", "date"]])

    for f, src in [("open_restaurants_insp", "open_rest_insp"), ("sba_ppp_food", "ppp"), ("sba_rrf", "rrf")]:
        d = pd.read_parquet(RAW / "signals" / f"{f}.parquet",
                            columns=["legal_name", "name", "bbl", "event_date"])
        d = d.rename(columns={"name": "dba", "event_date": "date"}).assign(source=src)
        out.append(d[["source", "legal_name", "dba", "bbl", "date"]])

    do = pd.read_parquet(RAW / "gov" / "dining_out_nyc.parquet",
                         columns=["business_legal_name", "assumed_name_s", "bbl", "license_issue_date"])
    do.columns = ["legal_name", "dba", "bbl", "date"]
    out.append(do.assign(source="dining_out"))

    dc = pd.read_parquet(RAW / "gov" / "dcwp_hist_licenses_food.parquet",
                         columns=["business_name", "business_name2", "bbl", "license_creation_date"])
    dc.columns = ["legal_name", "dba", "bbl", "date"]
    out.append(dc.assign(source="dcwp_hist"))

    r = pd.concat(out, ignore_index=True)
    r["date"] = pd.to_datetime(r["date"], errors="coerce").dt.tz_localize(None)
    r = r[r["date"] > "1990-01-01"]
    r["bbl"] = norm_bbl(r["bbl"])
    r = r[r["legal_name"].map(is_entity) & r["bbl"].notna()]
    r["legal_key"] = r["legal_name"].map(norm_name)
    r["dba_key"] = r["dba"].map(norm_name)
    r = r.dropna(subset=["legal_key"]).drop_duplicates(["source", "legal_key", "bbl", "date"])
    return r


def link(r: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    b = base.dropna(subset=["bbl"]).copy()
    b["alive_from"] = b["first_insp"].fillna(b["first_snap"]) - pd.Timedelta(days=365)
    b["alive_to"] = b[["last_insp", "last_snap"]].max(axis=1) + pd.Timedelta(days=365)
    m = r.merge(b[["camis", "bbl", "dba_key", "alive_from", "alive_to"]].rename(columns={"dba_key": "camis_dba"}),
                on="bbl")
    m = m[(m["date"] >= m["alive_from"]) & (m["date"] <= m["alive_to"])].copy()
    m["n_alive"] = m.groupby(["source", "legal_key", "bbl", "date"])["camis"].transform("nunique")
    m["sim_dba"] = [max(sim(a, c), sim(l, c)) for a, l, c in zip(m["dba_key"], m["legal_key"], m["camis_dba"])]
    m["rule"] = np.where(m["sim_dba"] >= 0.8, "name", np.where(m["n_alive"] == 1, "only_alive", None))
    m = m[m["rule"].notna()]
    # one CAMIS per record: best similarity
    m = m.sort_values("sim_dba", ascending=False).drop_duplicates(["source", "legal_key", "bbl", "date"])
    return m[["camis", "source", "legal_key", "legal_name", "bbl", "date", "sim_dba", "rule", "n_alive"]]


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build():
    base = pd.read_parquet(OUT / "camis_base.parquet")
    r = records()
    links = link(r, base)
    # a legal key linked to too many CAMIS is usually a landlord/management co or a big franchisor
    write_out(links, "camis_entity_links", "SLA, Open Restaurants, PPP, RRF, Dining Out, DCWP (entities only)",
              "CAMIS <-> legal entity, one row per (source record, CAMIS)")
    chain = pd.read_parquet(OUT / "camis_chain.parquet", columns=["camis", "brand_key", "is_chain_strict",
                                                                 "generic_name", "nyc_n_addresses"])
    for col in ("is_chain_strict", "generic_name"):
        chain[col] = chain[col].fillna(False).astype(bool)
    chain["nyc_n_addresses"] = chain["nyc_n_addresses"].fillna(0)
    d = DSU()
    for c in base["camis"]:
        d.find(("c", c))
    named = links[links["rule"].eq("name")]  # only_alive links are too loose to chain groups
    for c, k in zip(named["camis"], named["legal_key"]):
        d.union(("c", c), ("e", k))
    pg_file = OUT / "entity_process_groups.parquet"
    n_pg = 0
    if pg_file.exists():  # built by ai_dos_process.py from these links; run operators again after it
        pg = pd.read_parquet(pg_file)
        pg = pg[~pg["hub_address"] & pg["n_food_entities_at_addr"].between(2, 25)]
        for k, grp in zip(pg["legal_key"], pg["process_addr_group"]):
            d.union(("e", k), ("p", grp))
        n_pg = len(pg)
    log.info("DOS shared process-address links used: %d", n_pg)
    local = chain[~chain["is_chain_strict"] & ~chain["generic_name"] & (chain["nyc_n_addresses"] >= 2)]
    for c, k in zip(local["camis"], local["brand_key"]):
        d.union(("c", c), ("b", k))
    op = pd.DataFrame({"camis": base["camis"]})
    root = [d.find(("c", c)) for c in op["camis"]]
    op["_root"] = [f"{k}:{v}" for k, v in root]
    # stable id: smallest CAMIS in the component
    op["operator_id"] = "op" + op.groupby("_root")["camis"].transform("min").astype(str)
    op = op.drop(columns="_root")
    op = op.merge(base[["camis", "addr_key", "first_insp", "first_snap", "last_insp", "last_snap"]], on="camis")
    op["start"] = op["first_insp"].fillna(op["first_snap"])
    op["end"] = op[["last_insp", "last_snap"]].max(axis=1)
    op["has_entity_link"] = op["camis"].isin(set(named["camis"]))
    op["has_local_brand"] = op["camis"].isin(set(local["camis"]))
    g = op.groupby("operator_id")
    op["operator_n_camis"] = g["camis"].transform("nunique")
    op["operator_n_addresses"] = g["addr_key"].transform("nunique")
    # units the operator already ran (other addresses) when this CAMIS opened
    op = op.sort_values(["operator_id", "start"])
    prior, conc = [], []
    for _, grp in op.groupby("operator_id", sort=False):
        s, e, a = grp["start"].values, grp["end"].values, grp["addr_key"].values
        for i in range(len(grp)):
            other = a != a[i]
            prior.append(int(((s < s[i]) & other).sum()))
            conc.append(int(((s <= s[i]) & (e >= s[i]) & other).sum()))
    op["prior_units_at_open"] = prior
    op["concurrent_units_at_open"] = conc
    op["multi_unit_operator"] = op["operator_n_addresses"] >= 2
    linked = op["has_entity_link"] | op["has_local_brand"]
    op["first_time_operator"] = np.where(linked, op["prior_units_at_open"] == 0, None)
    op = op.drop(columns=["first_insp", "first_snap", "last_insp", "last_snap", "addr_key"])
    write_out(op, "camis_operator", "camis_entity_links + chain_brands_nyc",
              "operator groups; first_time_operator only where an entity or local-brand link exists")
    log.info("entity link %.1f%%, local brand %.1f%%, multi-unit %.1f%%", 100 * op.has_entity_link.mean(),
             100 * op.has_local_brand.mean(), 100 * op.multi_unit_operator.mean())


if __name__ == "__main__":
    build()
