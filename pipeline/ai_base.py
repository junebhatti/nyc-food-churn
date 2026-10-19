"""CAMIS-level base table from the DOHMH union: one row per permit with life window.

Output: camis_base.parquet. Used as the denominator for every coverage figure.
"""
from __future__ import annotations

import pandas as pd

from ai_common import LIVE_SNAPSHOT, RAW, UNION, log, con, norm_addr, norm_boro, norm_name, write_out


def add_geo(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise BBL; fill missing BBLs with the local PAD matcher; attach NTA/tract from PLUTO."""
    from gov_geocode import PadGeocoder
    from signals_common import norm_bbl

    df["bbl"] = norm_bbl(df["bbl"])
    df["geo_src"] = df["bbl"].notna().map({True: "dohmh", False: None})
    miss = df["bbl"].isna() & df["building"].notna() & df["street"].notna()
    g = PadGeocoder()
    res = g.geocode_df(df.loc[miss], "building", "street", zip="zipcode", boro="boro")
    ok = res["status"].eq("ok")
    idx = res.index[ok]
    df.loc[idx, "bbl"] = norm_bbl(res.loc[ok, "bbl"]).values
    df.loc[idx, "geo_src"] = "pad"
    log.info("PAD filled %d of %d missing BBLs", ok.sum(), miss.sum())
    pl = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet", columns=["bbl", "nta2020", "ct2020", "lat", "lon"])
    pl["bbl"] = norm_bbl(pl["bbl"])
    pl = pl.dropna(subset=["bbl"]).drop_duplicates("bbl").rename(columns={"lat": "lot_lat", "lon": "lot_lon"})
    df = df.merge(pl, on="bbl", how="left")
    return df


def build() -> pd.DataFrame:
    c = con()
    # latest non-null value per attribute, ordered by inspection date
    df = c.sql(f"""
        with u as (select * from '{UNION}')
        select camis,
          arg_max(dba, inspection_date) filter (where dba is not null) dba,
          arg_max(boro, inspection_date) filter (where boro is not null and boro not in ('0','Missing')) boro_raw,
          arg_max(building, inspection_date) filter (where building is not null) building,
          arg_max(street, inspection_date) filter (where street is not null) street,
          arg_max(zipcode, inspection_date) filter (where zipcode is not null) zipcode,
          arg_max(bbl, inspection_date) filter (where bbl is not null and bbl not in ('0','') ) bbl,
          arg_max(bin, inspection_date) filter (where bin is not null) bin,
          arg_max(latitude, inspection_date) filter (where latitude is not null and latitude <> 0) lat,
          arg_max(longitude, inspection_date) filter (where longitude is not null and longitude <> 0) lon,
          min(inspection_date) filter (where inspection_date > '1901-01-01') first_insp,
          max(inspection_date) filter (where inspection_date > '1901-01-01') last_insp,
          min(first_snapshot) first_snap,
          max(last_snapshot) last_snap,
          max(n_snapshots) n_snapshots
        from u group by camis
    """).df()
    df["boro"] = df["boro_raw"].map(norm_boro)
    df["dba_key"] = df["dba"].map(norm_name)
    df["addr_key"] = [
        (f"{b}|{a}" if a and b else None)
        for a, b in zip(map(norm_addr, df["building"], df["street"]), df["boro"])
    ]
    for col in ("first_insp", "last_insp", "first_snap", "last_snap"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["synthetic_camis"] = df["camis"].astype(str).str.startswith("X")
    df["open_at_live"] = df["last_snap"] >= pd.Timestamp(LIVE_SNAPSHOT)
    df["closed"] = ~df["open_at_live"]
    # left-censored: first inspection inside the first ~3y of data, so true opening is earlier
    df["left_censored"] = df["first_insp"] < pd.Timestamp("2011-07-01")
    df = df.drop(columns=["boro_raw"])
    df = add_geo(df)
    write_out(df, "camis_base", "data/raw/dohmh/union_inspections.parquet",
              "one row per CAMIS; latest non-null attributes; closed = absent from live 2026-10-16 pull; "
              "left_censored = first inspection before 2011-07")
    return df


if __name__ == "__main__":
    build()
