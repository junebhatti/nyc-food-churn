"""Match outside records (menus, licenses) to DOHMH CAMIS.

camis_base(): one row per CAMIS (latest name/address, cuisine, first/last inspection), with
PAD geocodes (BIN/BBL/lat-lon) filling the ~20k pre-2019 CAMIS that lack coordinates.
Cached at data/raw/menus/_camis_base.parquet.

match(df): df has id, name, house, street, zip, lat, lon, [year]. Rules, in order:
  1. same BIN (else same BBL) and name similarity >= 0.80        -> method 'bin' / 'bbl'
  2. name similarity >= 0.88 within 80 m                          -> method 'geo80'
Ties go to the CAMIS whose inspection years cover the record year, then higher similarity.
"""
from __future__ import annotations

import re
import sys

import duckdb
import pandas as pd

from menus_common import DOHMH, OUT

BASE = OUT / "_camis_base.parquet"
NAME_SIM_ADDR, NAME_SIM_GEO, MAX_M = 0.80, 0.88, 80


def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute(r"""
    create macro norm(s) as trim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
      upper(strip_accents(coalesce(s, ''))), '&', ' AND ', 'g'), '''', '', 'g'),
      '[^A-Z0-9 ]', ' ', 'g'),
      '\b(THE|INC|LLC|CORP|RESTAURANT|RESTAURANTS|CAFE|BAR|AND|NYC|NY|OF)\b', ' ', 'g'))
    """)
    c.execute("create macro nn(s) as replace(norm(s), ' ', '')")
    # Jaro-Winkler, or 0.9 when the shorter name (5+ chars) is contained in the longer one
    # ("ALIBABA" in "TASTYBURGERSHACKALIBABA")
    c.execute("""create macro namesim(a, b) as greatest(jaro_winkler_similarity(a, b),
      case when least(length(a), length(b)) >= 5 and (contains(a, b) or contains(b, a))
           then 0.9 else 0 end)""")
    c.execute("""create macro dist_m(lat1, lon1, lat2, lon2) as
      111320 * sqrt(power(lat1 - lat2, 2) + power((lon1 - lon2) * cos(radians(lat1)), 2))""")
    return c


def _geocode(df: pd.DataFrame, house: str, street: str, zip_: str, boro: str | None) -> pd.DataFrame:
    sys.path.insert(0, str(OUT.parents[2] / "pipeline"))
    from gov_geocode import PadGeocoder
    g = PadGeocoder()
    cols = [x for x in (house, street, zip_, boro) if x]
    clean = df[cols].astype(object).where(df[cols].notna(), "").astype(str)
    return g.geocode_df(clean, house=house, street=street, zip=zip_, boro=boro)


def camis_base(rebuild: bool = False) -> pd.DataFrame:
    if BASE.exists() and not rebuild:
        return pd.read_parquet(BASE)
    c = con()
    # numeric cuisine codes (old WebExtract) -> most common name seen for the same CAMIS
    c.execute(f"""create table d as select *, trim(cuisine) cu,
        try_cast(try_cast(trim(cuisine) as double) as int) code from '{DOHMH}'""")
    c.execute("""create table codemap as
        with pairs as (select distinct a.camis, a.code, b.cu from d a join d b using (camis)
                       where a.code is not null and b.code is null and b.cu is not null
                         and b.cu not in ('Other', 'Not Listed/Not Applicable'))
        select code, arg_max(cu, n) cuisine_name from
          (select code, cu, count(*) n from pairs group by all) group by code""")
    df = c.execute("""
    select camis, arg_max(dba, inspection_date) dba, arg_max(upper(boro), inspection_date) boro,
      arg_max(building, inspection_date) building, arg_max(street, inspection_date) street,
      arg_max(zipcode, inspection_date) zipcode,
      arg_max(try_cast(latitude as double), case when try_cast(latitude as double) between 40.4 and 41.0 then inspection_date end) lat,
      arg_max(try_cast(longitude as double), case when try_cast(latitude as double) between 40.4 and 41.0 then inspection_date end) lon,
      arg_max(bin, case when bin ~ '^[1-5][0-9]{6}$' and bin !~ '000000$' then inspection_date end) bin,
      arg_max(bbl, case when bbl ~ '^[1-5][0-9]{9}' then inspection_date end) bbl,
      coalesce(arg_max(cu, case when code is null and cu is not null then inspection_date end),
               arg_max(m.cuisine_name, case when code is not null then inspection_date end)) cuisine,
      min(case when inspection_date > date '1901-01-01' then inspection_date end) first_insp,
      max(case when inspection_date > date '1901-01-01' then inspection_date end) last_insp
    from d left join codemap m using (code) group by camis
    """).df()
    df["cuisine"] = df["cuisine"].str.replace("CafÃ©|CafÃÂÃÂ©", "Café", regex=True).str.strip()
    df["boro"] = df["boro"].replace({"1": "MANHATTAN", "2": "BRONX", "3": "BROOKLYN",
                                     "4": "QUEENS", "5": "STATEN ISLAND"})
    df["bbl"] = df["bbl"].str.replace(r"\.0+$", "", regex=True)
    need = df["bin"].isna() | df["lat"].isna()
    geo = _geocode(df[need], "building", "street", "zipcode", None)
    ok = geo["status"].eq("ok")
    print(f"camis_base: geocoded {ok.sum():,}/{need.sum():,} CAMIS lacking BIN or coords")
    idx = geo.index[ok]
    for col in ("bin", "bbl", "lat", "lon"):
        src = geo.loc[idx, col if col != "bbl" else "bbl"]
        df.loc[idx, col] = df.loc[idx, col].where(df.loc[idx, col].notna(), src)
    df["geo_src"] = "dohmh"
    df.loc[idx, "geo_src"] = "pad"
    df.to_parquet(BASE, index=False)
    print(f"wrote {BASE}: {len(df):,} CAMIS")
    return df


def match(src: pd.DataFrame, geocode: bool = True) -> pd.DataFrame:
    """src: id, name, house, street, zip, lat, lon, year(optional). Returns id -> camis."""
    src = src.copy()
    for col in ("year", "bin", "bbl"):
        if col not in src:
            src[col] = None
    src["year"] = pd.to_numeric(src["year"], errors="coerce")
    if geocode:
        g = _geocode(src, "house", "street", "zip", None)
        src["bin"] = g.get("bin")
        src["bbl"] = g.get("bbl")
        src["lat"] = pd.to_numeric(src["lat"], errors="coerce").fillna(g.get("lat"))
        src["lon"] = pd.to_numeric(src["lon"], errors="coerce").fillna(g.get("lon"))
    base = camis_base()
    c = con()
    s0 = src[["id", "name", "bin", "bbl", "lat", "lon", "year"]].copy()
    for col in ("id", "name", "bin", "bbl"):
        s0[col] = s0[col].astype("string")
    c.register("s0", s0)
    c.register("b0", base)
    res = c.execute(f"""
    with s as (select id, nn(name) n, bin, bbl, try_cast(lat as double) lat,
                      try_cast(lon as double) lon, try_cast(year as int) yr from s0),
    b as (select camis, nn(dba) n, bin, bbl, lat, lon, year(first_insp) y0, year(last_insp) y1 from b0),
    addr as (
      select s.id, b.camis, case when s.bin = b.bin then 'bin' else 'bbl' end as how,
             namesim(s.n, b.n) sim, s.yr, b.y0, b.y1
      from s join b on (s.bin = b.bin or s.bbl = b.bbl)
      where s.n <> '' and b.n <> ''),
    geo as (
      select s.id, b.camis, 'geo80' as how, namesim(s.n, b.n) sim, s.yr, b.y0, b.y1
      from s join b on b.lat between s.lat - 0.00075 and s.lat + 0.00075
                   and b.lon between s.lon - 0.001 and s.lon + 0.001
      where s.n <> '' and b.n <> '' and dist_m(s.lat, s.lon, b.lat, b.lon) <= {MAX_M}),
    cand as (
      select * from addr where sim >= {NAME_SIM_ADDR}
      union all select * from geo where sim >= {NAME_SIM_GEO}),
    scored as (
      select *, (case when yr is null or yr between y0 - 1 and y1 + 1 then 1 else 0 end) yr_ok,
             case how when 'bin' then 0.02 when 'bbl' then 0.01 else 0 end bonus from cand)
    select id, arg_max(camis, yr_ok * 10 + sim + bonus) camis,
           arg_max(how, yr_ok * 10 + sim + bonus) match_method,
           max(sim) match_sim, count(distinct camis) n_candidates
    from scored group by id
    """).df()
    return res


if __name__ == "__main__":
    camis_base(rebuild=True)
