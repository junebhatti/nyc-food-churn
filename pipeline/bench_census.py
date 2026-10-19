"""Census bulk files (no API key needed): CBP county, ZBP ZIP detail, BDS, Nonemployer.

The Census Data API now redirects every keyless request to missing_key.html, so this uses
the www2.census.gov bulk files instead. Each zip is downloaded to DL, filtered to NYC +
food NAICS, written as a small parquet in OUT, and deleted.
"""
import zipfile

import pandas as pd

from bench_common import CTY_NAME_BORO, DL, NYC_COUNTIES, OUT, download, get, log, zip_to_boro

CB = "https://www2.census.gov/programs-surveys"
YEARS = range(2010, 2026)

# Codes kept (dashes/slashes stripped). 2010-11 use NAICS 2007 (7221/7222 instead of 7225).
KEEP = {"", "72", "722", "7221", "7222", "7223", "7224", "7225",
        "722110", "722211", "722212", "722213", "722410",
        "722511", "722513", "722514", "722515", "311811", "445291", "445298"}


def _clean_naics(s):
    return s.astype(str).str.replace("-", "", regex=False).str.replace("/", "", regex=False)


def _read_zip_csv(path, **kw):
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith((".txt", ".csv"))][0]
        with z.open(name) as f:
            yield from pd.read_csv(f, dtype=str, encoding="latin-1", chunksize=500_000, **kw)


MISSING = []  # (url, reason) for files that could not be fetched; written to fetch_log by the caller


def _fetch_zip(url, name):
    try:
        return download(url, DL / name, tries=2)
    except Exception as e:
        if "404" in str(e):
            log(f"not released / not found: {url}")
            return None
        if "non-zip" in str(e):  # census.gov WAF persistently rejects a few files
            log(f"SKIPPED, census.gov WAF rejected it: {url}")
            MISSING.append((url, "census.gov WAF 'Request Rejected'"))
            return None
        raise


def cbp_county():
    out = OUT / "cbp_county_nyc.parquet"
    frames = []
    for y in YEARS:
        yy = f"{y % 100:02d}"
        p = _fetch_zip(f"{CB}/cbp/datasets/{y}/cbp{yy}co.zip", f"cbp{yy}co.zip")
        if p is None:
            continue
        for ch in _read_zip_csv(p):
            ch.columns = [c.lower() for c in ch.columns]
            ch = ch[(ch.fipstate == "36") & ch.fipscty.isin(NYC_COUNTIES)]
            ch = ch.assign(naics=_clean_naics(ch.naics))
            ch = ch[ch.naics.isin(KEEP)]
            if len(ch):
                frames.append(ch.assign(year=y))
        p.unlink()
    df = pd.concat(frames, ignore_index=True)
    df["borough"] = df.fipscty.map(NYC_COUNTIES)
    for c in ("est", "emp"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.to_parquet(out, index=False)
    log(f"cbp_county_nyc: {len(df)} rows, years {df.year.min()}-{df.year.max()}")
    return df


def zbp_detail():
    out = OUT / "zbp_detail_nyc.parquet"
    frames = []
    for y in YEARS:
        yy = f"{y % 100:02d}"
        cache = DL / f"zbp{yy}_nyc.parquet"  # filtered per-year cache so a failed run need not re-download
        if cache.exists():
            frames.append(pd.read_parquet(cache))
            continue
        p = _fetch_zip(f"{CB}/cbp/datasets/{y}/zbp{yy}detail.zip", f"zbp{yy}detail.zip")
        if p is None:
            continue
        parts = []
        for ch in _read_zip_csv(p):
            ch.columns = [c.lower() for c in ch.columns]
            ch = ch.rename(columns={"n1_4": "n<5"})
            ch = ch.assign(zip=ch.zip.str.zfill(5), naics=_clean_naics(ch.naics))
            nyc = ch.zip.map(zip_to_boro).notna()
            if "stabbr" in ch:  # 2019+: drop non-NY ZIPs that share no prefix anyway
                nyc &= ch.stabbr.eq("NY")
            ch = ch[nyc & ch.naics.isin(KEEP)]
            if len(ch):
                parts.append(ch.assign(year=y))
        yd = pd.concat(parts, ignore_index=True)
        yd.to_parquet(cache, index=False)
        frames.append(yd)
        p.unlink()
    df = pd.concat(frames, ignore_index=True)
    df["est"] = pd.to_numeric(df.est, errors="coerce")
    # Borough: Census county name where given (2019+), else USPS prefix.
    names = df.dropna(subset=["cty_name"]) if "cty_name" in df else df.iloc[0:0]
    zip_cty = names.groupby("zip").cty_name.agg(lambda s: s.mode().iat[0]).map(CTY_NAME_BORO)
    df["borough"] = df.zip.map(zip_cty).fillna(df.zip.map(zip_to_boro))
    keep = [c for c in ["year", "zip", "borough", "naics", "est", "n<5", "n5_9", "n10_19", "n20_49",
                        "n50_99", "n100_249", "n250_499", "n500_999", "n1000", "name", "cty_name"] if c in df]
    df = df[keep]
    # Non-NYC counties in the prefix ranges (e.g. Nassau 110xx/115xx are excluded by prefix);
    # drop ZIPs whose Census county is known and outside NYC.
    if "cty_name" in df:
        bad = names.loc[~names.cty_name.isin(CTY_NAME_BORO), "zip"].unique()
        good = names.loc[names.cty_name.isin(CTY_NAME_BORO), "zip"].unique()
        df = df[~df.zip.isin(set(bad) - set(good))]
    df.to_parquet(out, index=False)
    log(f"zbp_detail_nyc: {len(df)} rows, {df.zip.nunique()} ZIPs, years {df.year.min()}-{df.year.max()}")
    return df


def bds():
    """BDS 2023 release (data to 2023): county x sector, metro x sector, national NAICS4."""
    base = f"{CB}/bds/tables/time-series/2023"
    res = {}
    for fn, filt in [("bds2023_st_cty_sec.csv", lambda d: (d.st == "36") & d.cty.isin(NYC_COUNTIES) & (d.sector == "72")),
                     ("bds2023_st_sec.csv", lambda d: (d.st == "36") & (d.sector == "72")),
                     ("bds2023_sec.csv", lambda d: d.sector == "72"),
                     ("bds2023_msa_sec.csv", lambda d: (d.msa == "35620") & (d.sector == "72")),
                     ("bds2023_vcn4.csv", lambda d: d.vcnaics4.isin({"7225", "7224", "7223"}))]:
        p = download(f"{base}/{fn}", DL / fn)
        d = pd.read_csv(p, dtype=str)
        d = d[filt(d)].copy()
        d["year"] = d.year.astype(int)
        d = d[d.year >= 2005]
        name = fn.replace("bds2023_", "bds_").replace(".csv", "")
        d.to_parquet(OUT / f"{name}.parquet", index=False)
        res[name] = d
        p.unlink()
        log(f"{name}: {len(d)} rows")
    return res


def nonemployer():
    out = OUT / "nonemp_county_nyc.parquet"
    frames = []
    for y in YEARS:
        yy = f"{y % 100:02d}"
        p = _fetch_zip(f"{CB}/nonemployer-statistics/datasets/{y}/historical-datasets/nonemp{yy}co.zip",
                       f"nonemp{yy}co.zip")
        if p is None:
            continue
        for ch in _read_zip_csv(p):
            ch.columns = [c.lower() for c in ch.columns]
            ch = ch[(ch.st == "36") & ch.cty.isin(NYC_COUNTIES)]
            ch = ch.assign(naics=_clean_naics(ch.naics))
            ch = ch[ch.naics.isin(KEEP)]
            if len(ch):
                frames.append(ch.assign(year=y))
        p.unlink()
    df = pd.concat(frames, ignore_index=True)
    df["borough"] = df.cty.map(NYC_COUNTIES)
    df["estab"] = pd.to_numeric(df.get("estab"), errors="coerce")
    df.to_parquet(out, index=False)
    log(f"nonemp_county_nyc: {len(df)} rows, years {df.year.min()}-{df.year.max()}")
    return df


if __name__ == "__main__":
    import sys
    OUT.mkdir(parents=True, exist_ok=True)
    for step in sys.argv[1:] or ["cbp_county", "zbp_detail", "bds", "nonemployer"]:
        globals()[step]()
    for u, why in MISSING:
        log(f"MISSING {u}: {why}")
