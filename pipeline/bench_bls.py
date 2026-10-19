"""BLS: QCEW quarterly establishments/employment for NYC counties, and BED openings/closings.

QCEW: the open-data CSV slice API (data.bls.gov/cew/data/api) serves 2014+; 2010-2013 come
from the quarterly by-area bulk zips, read member-by-member with HTTP Range requests.
BED: BLS public API v1 (no key; 25 queries/day, so this makes 2 calls).
"""
import io
import json

import pandas as pd
import requests

from bench_common import NYC_COUNTIES, OUT, UA, get, log, remote_zip

AREAS = {f"36{c}" for c in NYC_COUNTIES}
INDUSTRIES = ["722", "7225", "722511", "722513", "722515", "7224", "722410", "311811", "445291"]
COLS = ["area_fips", "own_code", "industry_code", "agglvl_code", "size_code", "year", "qtr",
        "disclosure_code", "qtrly_estabs", "month1_emplvl", "month2_emplvl", "month3_emplvl",
        "total_qtrly_wages", "avg_wkly_wage"]
API = "https://data.bls.gov/cew/data/api"


def _api_years():
    import datetime
    return range(2014, datetime.date.today().year + 1)


def qcew():
    out = OUT / "qcew_nyc_quarterly.parquet"
    frames = []
    # 2014+ from the API industry slices
    for y in _api_years():
        for q in (1, 2, 3, 4):
            got_any = False
            for ind in INDUSTRIES:
                try:
                    r = get(f"{API}/{y}/{q}/industry/{ind}.csv", tries=3)
                except Exception as e:
                    if "404" in str(e):
                        continue  # quarter not yet published, or industry slice absent
                    raise
                d = pd.read_csv(io.StringIO(r.text), dtype=str)
                d = d[d.area_fips.isin(AREAS)]
                frames.append(d[[c for c in COLS if c in d]])
                got_any = True
            if not got_any:
                log(f"QCEW {y}Q{q}: not published")
    # 2010-2013 from bulk by-area zips (range reads; only the 5 NYC county members)
    want = {i for i in INDUSTRIES}
    for y in range(2010, 2014):
        url = f"https://data.bls.gov/cew/data/files/{y}/csv/{y}_qtrly_by_area.zip"
        z = remote_zip(url)
        members = [n for n in z.namelist() if any(f" {a} " in n for a in AREAS)]
        if len(members) != 5:
            raise RuntimeError(f"{url}: expected 5 NYC county members, got {members}")
        for m in members:
            d = pd.read_csv(z.open(m), dtype=str).rename(columns={"qtrly_estabs_count": "qtrly_estabs"})
            d = d[d.industry_code.isin(want)]
            frames.append(d[[c for c in COLS if c in d]])
        log(f"QCEW {y}: bulk members read")
    df = pd.concat(frames, ignore_index=True).drop_duplicates()
    for c in ["year", "qtr", "qtrly_estabs", "month1_emplvl", "month2_emplvl", "month3_emplvl",
              "total_qtrly_wages", "avg_wkly_wage"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["borough"] = df.area_fips.str[2:].map(NYC_COUNTIES)
    df.to_parquet(out, index=False)
    log(f"qcew: {len(df)} rows, {df.year.min()}Q? - {df.year.max()}Q{df[df.year == df.year.max()].qtr.max()}")
    return df


# BED series: BD + S + area(10) + industry(6) + unit(1) + element(1) + size(2) + class(2) + R/L + Q + own
# industry 300722 = NAICS 722 (national only); state data only at supersector: 200070 = leisure & hospitality.
# element 2 = establishments; class 03 = openings, 06 = closings (07/08 births/deaths: total private only).
BED_SERIES = {}
for area, ind, label in [("0000000000", "300722", "US NAICS 722 food services & drinking places"),
                         ("0000000000", "000000", "US total private"),
                         ("0000036000", "200070", "NY state leisure & hospitality"),
                         ("0000036000", "000000", "NY state total private")]:
    for cls, ev in [("03", "openings"), ("06", "closings")]:
        for rl in ("R", "L"):
            BED_SERIES[f"BDS{area}{ind}12{'00'}{cls}{rl}Q5"] = (label, ev, "rate" if rl == "R" else "level")


def bed():
    out = OUT / "bed_openings_closings.parquet"
    rows = []
    ids = list(BED_SERIES)
    for start, end in [("2010", "2019"), ("2020", "2029")]:
        r = requests.post("https://api.bls.gov/publicAPI/v1/timeseries/data/",
                          json={"seriesid": ids, "startyear": start, "endyear": end},
                          headers=UA, timeout=120).json()
        if r.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(f"BLS API: {r.get('status')} {r.get('message')}")
        for s in r["Results"]["series"]:
            if not s["data"]:
                raise RuntimeError(f"BED series empty: {s['seriesID']} ({r.get('message')})")
            label, ev, kind = BED_SERIES[s["seriesID"]]
            for x in s["data"]:
                rows.append({"series_id": s["seriesID"], "series": label, "event": ev, "kind": kind,
                             "year": int(x["year"]), "qtr": int(x["period"][1:]),
                             "value": float(x["value"])})
    df = pd.DataFrame(rows).drop_duplicates()
    df.to_parquet(out, index=False)
    log(f"bed: {len(df)} rows, {df.year.min()}-{df.year.max()}")
    (OUT / "bed_series.json").write_text(json.dumps(BED_SERIES, indent=1))
    return df


if __name__ == "__main__":
    import sys
    OUT.mkdir(parents=True, exist_ok=True)
    for step in sys.argv[1:] or ["bed", "qcew"]:
        globals()[step]()
