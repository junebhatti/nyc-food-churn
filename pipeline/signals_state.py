"""data.ny.gov proof-of-life signals: SBA PPP loans and RRF grants (COVID era), NYS DOS entity
formation / dissolution filings matched to the legal names in SLA, PPP and RRF.
"""
from __future__ import annotations

import pandas as pd

from signals_common import (NYC_COUNTIES, NYS, OUT, finish, geocoder, norm_name, save, socrata,
                            soql_in)

ROOT_GOV = OUT.parent / "gov"


def _ymd(df, prefix: str) -> pd.Series:
    return pd.to_datetime(dict(year=pd.to_numeric(df[f"{prefix}_year"], errors="coerce"),
                               month=pd.to_numeric(df[f"{prefix}_month"], errors="coerce"),
                               day=pd.to_numeric(df[f"{prefix}_day"], errors="coerce")), errors="coerce")


# ---------------------------------------------------------------- PPP
def fetch_ppp() -> pd.DataFrame:
    """PPP loans 2020-04..2021-05, NAICS 722 (restaurants, bars, caterers, food trucks) + 311811
    (retail bakeries), project county in NYC."""
    where = (f"(naicscode between 722000 and 722599 OR naicscode = 311811) "
             f"AND projectcountyname in ({soql_in(NYC_COUNTIES)})")
    sel = ("loannumber,dateapproved_year,dateapproved_month,dateapproved_day,borrowername,"
           "borroweraddress,borrowercity,borrowerzip,projectcountyname,projectzip,naicscode,"
           "businessagedescription,businesstype,jobsreported,initialapprovalamount,franchisename,"
           "processingmethod,forgivenessdate_year,forgivenessdate_month,forgivenessdate_day")
    raw = socrata(NYS, "y8zq-jmz6", where=where, select=sel)
    base = dict(source_id=raw["loannumber"], legal_name=raw["borrowername"],
                name=raw["franchisename"], address=raw["borroweraddress"],
                boro=raw["projectcountyname"], zip=raw["borrowerzip"].fillna(raw["projectzip"]),
                naics=raw["naicscode"], business_age=raw["businessagedescription"],
                business_type=raw["businesstype"], jobs=pd.to_numeric(raw["jobsreported"], errors="coerce"),
                amount=pd.to_numeric(raw["initialapprovalamount"], errors="coerce"),
                draw=raw["processingmethod"])  # PPP = first draw, PPS = second draw
    a = pd.DataFrame({**base, "event_date": _ymd(raw, "dateapproved"), "event_type": "loan_approved"})
    f = pd.DataFrame({**base, "event_date": _ymd(raw, "forgivenessdate"), "event_type": "loan_forgiven"})
    f = f[f["event_date"].notna()]
    df = pd.concat([a, f], ignore_index=True)
    df["detail"] = ("NAICS " + df["naics"].astype(str) + " | " + df["business_age"].fillna("")
                    + " | " + df["draw"].fillna(""))
    df = finish(df, source="sba_ppp")
    save(df, "sba_ppp_food", dataset_id="y8zq-jmz6", domain=NYS,
         note="SBA PPP loans to NYC NAICS 722xxx/311811 borrowers. legal_name = borrower; name = "
              "franchise. Address is the borrower's (usually the premises). loan_forgiven rows: "
              "forgiveness date, weaker evidence (owner, not premises).")
    return df


# ---------------------------------------------------------------- RRF
def fetch_rrf() -> pd.DataFrame:
    raw = socrata(NYS, "3pjx-bgty")
    g = geocoder()
    z = raw["businesszip"].astype(str).str[:5]
    raw = raw[z.map(lambda x: x in g.zip_boro)]
    df = pd.DataFrame({
        "source_id": raw["loannumber"], "event_date": _ymd(raw, "approvaldate"),
        "event_type": "grant_approved", "legal_name": raw["businessname"], "name": raw["franchisename"],
        "address": raw["businessaddress"], "zip": raw["businesszip"],
        "detail": raw["restauranttype"].fillna("") + " | " + raw["legalorganizationtype"].fillna(""),
        "restaurant_type": raw["restauranttype"],
        "amount": pd.to_numeric(raw["grantamount"], errors="coerce")})
    df = finish(df, source="sba_rrf")
    save(df, "sba_rrf", dataset_id="3pjx-bgty", domain=NYS,
         note="SBA Restaurant Revitalization Fund grants 2021-05..07 to businesses with an NYC ZIP.")
    return df


# ---------------------------------------------------------------- NYS DOS
FORM_DOCS = ("CERTIFICATE OF INCORPORATION", "ARTICLES OF ORGANIZATION", "APPLICATION OF AUTHORITY")
END_DOCS = ("DISSOLUTION BY PROCLAMATION", "CERTIFICATE OF DISSOLUTION", "ARTICLES OF DISSOLUTION",
            "SURRENDER OF AUTHORITY", "ANNULMENT OF AUTHORITY", "CERTIFICATE OF TERMINATION",
            "CERTIFICATE OF CANCELLATION")


def _target_names() -> pd.DataFrame:
    """Legal names we want formation dates for: SLA on-premises licensees, PPP and RRF borrowers."""
    sla = pd.read_parquet(ROOT_GOV / "sla_licenses_nyc.parquet", columns=["legal_name", "on_premises"])
    parts = [sla.loc[sla["on_premises"].fillna(False), ["legal_name"]].assign(src="sla_onprem"),
             sla.loc[~sla["on_premises"].fillna(False), ["legal_name"]].assign(src="sla_other")]
    for f in ("sba_ppp_food", "sba_rrf"):
        p = OUT / f"{f}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p, columns=["legal_name"]).assign(src=f))
        else:
            print(f"  dos: {p.name} missing, run its fetcher first to match its names", flush=True)
    t = pd.concat(parts, ignore_index=True).dropna()
    t["key"] = norm_name(t["legal_name"])
    # entity-looking names only: sole proprietors' personal names do not file with DOS
    ent = t["legal_name"].str.upper().str.contains(r"\b(INC|LLC|CORP|CORPORATION|LTD|L\.L\.C|CO)\b\.?")
    return t[ent & t["key"].notna() & (t["key"].str.len() >= 4)]


def fetch_dos() -> pd.DataFrame:
    """Formation filings of NYC-county entities 1995+ (pulled in yearly slices, then name-matched
    locally), and the end filings (dissolution etc.) of the matched entities by corpid."""
    targets = _target_names()
    keys = set(targets["key"])
    print(f"  dos: {len(keys):,} distinct target legal names", flush=True)
    cache = OUT / "_dos_formations_nyc.parquet"
    if cache.exists():
        form = pd.read_parquet(cache)
    else:
        frames = []
        for y in range(1995, 2027):
            w = (f"documenttype in ({soql_in(FORM_DOCS)}) AND upper(cnty_prin_ofc) in "
                 f"({soql_in(NYC_COUNTIES)}) AND date_filed between '{y}-01-01' and '{y}-12-31T23:59:59'")
            frames.append(socrata(NYS, "63wc-4exh", where=w, page=50_000,
                                  select="corpid_num,date_filed,documenttype,entitytype,corp_name,cnty_prin_ofc"))
        form = pd.concat(frames, ignore_index=True)
        form.to_parquet(cache, index=False, compression="zstd")  # all NYC formations, reused on rerun
    form["key"] = norm_name(form["corp_name"])
    hit = form[form["key"].isin(keys)].copy()
    print(f"  dos: {len(form):,} NYC formations; {len(hit):,} match a target name "
          f"({hit['key'].nunique():,} of {len(keys):,} names)", flush=True)
    ids = sorted(hit["corpid_num"].unique())
    ends = []
    for i in range(0, len(ids), 300):
        w = f"corpid_num in ({soql_in(ids[i:i + 300])}) AND documenttype in ({soql_in(END_DOCS)})"
        ends.append(socrata(NYS, "63wc-4exh", where=w, select="corpid_num,date_filed,documenttype"))
    end = pd.concat(ends, ignore_index=True).merge(
        hit[["corpid_num", "corp_name", "entitytype", "cnty_prin_ofc", "key"]].drop_duplicates("corpid_num"),
        on="corpid_num")
    hit["event_type"], end["event_type"] = "entity_formed", "entity_ended"
    df = pd.concat([hit, end], ignore_index=True)
    srcs = targets.groupby("key")["src"].agg(lambda s: ",".join(sorted(set(s))))
    df = pd.DataFrame({
        "source_id": df["corpid_num"], "event_date": df["date_filed"], "event_type": df["event_type"],
        "legal_name": df["corp_name"], "boro": df["cnty_prin_ofc"].str.upper(),
        "detail": df["documenttype"] + " | " + df["entitytype"].fillna(""),
        "name_key": df["key"], "matched_from": df["key"].map(srcs)})
    df = finish(df, source="nys_dos")
    save(df, "nys_dos_entities", dataset_id="63wc-4exh", domain=NYS,
         note="NYS DOS formation (and later end) filings for entities whose normalized name equals an "
              "SLA licensee / PPP / RRF legal name; county of principal office in NYC. No premises "
              "address (DOS keeps process addresses) -> join by name_key, not location.")
    return df
