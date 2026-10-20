"""Step 3 of the merge: tenant history per building, and each business's predecessors.

Building = BIN when valid; else the BIN that PAD gives the address or the lot; else tax lot (BBL),
else street text. Bars from NYSLA have only coordinates, so they snap to the nearest PLUTO lot
centroid within SNAP_M metres.
For each building: businesses seen since the first copy (2012-07-06), how many are open now,
the most open at once (food halls and malls hold many), and median lifespan of closed ones.
For each business: tenants that closed in the same building before it opened, the last one's
lifespan, and the vacant gap in between. Buildings with MULTI_TENANT+ businesses open at once
are flagged, since "previous tenant" means little there.

Reads and rewrites data/processed/businesses.parquet; writes data/processed/buildings.parquet.
Run: .venv/bin/python pipeline/build_buildings.py
"""
from __future__ import annotations

import re

import duckdb
import numpy as np
import pandas as pd

from build_lifespans import OUT, RAW

FIRST_COPY = pd.Timestamp("2012-07-06")
SNAP_M = 40
MULTI_TENANT = 4
ADDR_M = 150
STREET_ABBR = {"AVE": "AVENUE", "AV": "AVENUE", "ST": "STREET", "STR": "STREET", "BLVD": "BOULEVARD", "PL": "PLACE",
               "RD": "ROAD", "PKWY": "PARKWAY", "DR": "DRIVE", "LN": "LANE", "CT": "COURT", "TER": "TERRACE",
               "HWY": "HIGHWAY", "TPKE": "TURNPIKE", "SQ": "SQUARE", "EXPY": "EXPRESSWAY", "BWAY": "BROADWAY",
               "PLZ": "PLAZA", "CIR": "CIRCLE", "E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH"}


def snap_to_lots(b: pd.DataFrame) -> pd.DataFrame:
    """Give coordinate-only rows (no BBL) the nearest lot's BBL."""
    need = b[b["bbl"].isna() & b["lat"].notna()][["business_id", "lat", "lon"]]
    if need.empty:
        return b
    c = duckdb.connect()
    c.register("need", need)
    hit = c.execute(f"""
      with lots as (select bbl, lat, lon from '{RAW}/gov/pluto_slim.parquet' where lat is not null),
      p as (
        select n.business_id, l.bbl,
               111320 * sqrt(power(l.lat - n.lat, 2) + power((l.lon - n.lon) * cos(radians(n.lat)), 2)) d
        from need n join lots l
          on abs(l.lat - n.lat) < 0.0005 and abs(l.lon - n.lon) < 0.0007)
      select business_id, arg_min(bbl, d) bbl from p where d <= {SNAP_M} group by 1
    """).df()
    b = b.merge(hit.rename(columns={"bbl": "bbl_snap"}), on="business_id", how="left")
    b["bbl"] = b["bbl"].fillna(b["bbl_snap"].astype("string"))
    return b.drop(columns=["bbl_snap"])


def norm_street(s: str) -> str:
    """'W 4th St' and 'WEST    4 STREET' (PAD's spelling) both become 'WEST 4 STREET'."""
    w = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper()).split()
    out = []
    for i, t in enumerate(w):
        t = re.sub(r"^(\d+)(ST|ND|RD|TH)$", r"\1", t)
        if t == "ST" and i == 0 and len(w) > 1:
            t = "SAINT"
        elif t in STREET_ABBR and not (t in "NSEW" and i == len(w) - 1):
            t = STREET_ABBR[t]
        out.append(t)
    return " ".join(out)


def house_keys(building, street, boro) -> tuple[list[int], str]:
    """PAD's numeric house keys (108 -> 108000, 37-25 -> 37025) and the street without the number.
    Bars carry the number inside street; Queens numbers often lose their hyphen, so 9712 also tries 97-12."""
    if isinstance(building, str) and building.strip():
        h, st = building.strip().upper(), street
    else:
        m = re.match(r"^\s*(\d+(?:[- ]\d+)?[A-Z]?)\s+(.*)$", str(street).upper())
        if not m:
            return [], str(street)
        h, st = m.groups()
    m = re.fullmatch(r"(\d+)[- ](\d+)[A-Z]?", h)
    if m:
        return [int(m.group(1)) * 1000 + int(m.group(2))], st
    m = re.fullmatch(r"(\d+)[A-Z]?", h)
    if not m:
        return [], st
    n = int(m.group(1))
    keys = [n * 1000]
    if str(boro).upper() in ("QUEENS", "4") and n >= 1000:
        keys.append(n // 100 * 1000 + n % 100)
    return keys, st


def bins_for_lots(b: pd.DataFrame, lot: pd.Series) -> pd.Series:
    """BIN for businesses keyed by lot or text, so a bar and a restaurant in one building share a page.
    First the address in PAD (one BIN, on the business's own lot if several, within ADDR_M of its point);
    else the lot's BIN when PAD gives the lot (or condo billing lot) exactly one building."""
    pad = pd.read_parquet(RAW / "gov" / "pad_addr.parquet",
                          columns=["stname", "zipcode", "lkey", "hkey", "lhnd", "bin", "bbl", "bbl_billing"])
    pad["bin"] = pad["bin"].astype(str)
    pad = pad[pad["bin"].str.fullmatch(r"[1-5]\d{6}") & ~pad["bin"].str[1:].str.fullmatch(r"0+")]
    pad["st"] = pad["stname"].map(norm_street)

    rows = []
    for idx, building, street, zip_, boro in zip(b.index, b["building"], b["street"], b["zip"], b["boro"]):
        keys, st = house_keys(building, street, boro)
        rows += [(idx, norm_street(st), str(zip_)[:5], k) for k in keys]
    q = pd.DataFrame(rows, columns=["idx", "st", "zipcode", "k"])
    m = q.merge(pad, on=["st", "zipcode"])
    m = m[(m["k"] >= m["lkey"]) & (m["k"] <= m["hkey"]) & ((m["k"] // 1000 - m["lkey"] // 1000) % 2 == 0)].copy()
    # several BINs: keep those on the business's lot, then prefer real addresses over PAD's "10 REAR", "10 GARAGE"
    m["rowlot"] = lot.reindex(m["idx"]).values
    m = m[m.groupby("idx")["bin"].transform("nunique").eq(1)
          | (m["bbl"] == m["rowlot"]) | (m["bbl_billing"] == m["rowlot"])].copy()
    m["plain"] = m["lhnd"].str.strip().str.fullmatch(r"\d+(-\d+)?[A-Z]?")
    m = m[m.groupby("idx")["bin"].transform("nunique").eq(1) | m["plain"]
          | ~m.groupby("idx")["plain"].transform("any")]
    one = m.groupby("idx")["bin"].nunique()
    hit = m[m["idx"].isin(one[one == 1].index)].drop_duplicates("idx").set_index("idx")
    # guard against a same-named street elsewhere in the zip: the lot must sit near the business
    pl = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet", columns=["bbl", "lat", "lon"]).drop_duplicates("bbl").set_index("bbl")
    cen = np.where(hit["bbl_billing"].isin(pl.index), hit["bbl_billing"], hit["bbl"])
    d = 111320 * np.sqrt((pl["lat"].reindex(cen).values - b.loc[hit.index, "lat"].values) ** 2
                         + ((pl["lon"].reindex(cen).values - b.loc[hit.index, "lon"].values) * 0.76) ** 2)
    by_addr = hit.loc[~(d > ADDR_M), "bin"]

    lots = pd.concat([pad[["bbl", "bin"]], pad[["bbl_billing", "bin"]].rename(columns={"bbl_billing": "bbl"})])
    lot_bins = lots.dropna().drop_duplicates().groupby("bbl")["bin"].agg(list)
    by_lot = lot.map(lot_bins[lot_bins.str.len() == 1].str[0])
    out = by_addr.reindex(b.index).fillna(by_lot)
    print(f"lot/text businesses {len(b):,}: BIN by address {len(by_addr):,}, by single-building lot "
          f"{(out.notna().sum() - len(by_addr)):,}, unresolved {out.isna().sum():,}")
    return out


def building_key(b: pd.DataFrame) -> pd.Series:
    bin_ = b["bin"].astype(str).str.replace(r"\.0$", "", regex=True)
    bin_ok = bin_.str.fullmatch(r"[1-5]\d{6}") & ~bin_.str[1:].str.fullmatch(r"0+")
    bbl = b["bbl"].astype(str).str.replace(r"\.0$", "", regex=True)
    bbl_ok = bbl.str.fullmatch(r"[1-5]\d{9}") & ~bbl.str[1:].str.fullmatch(r"0+")
    # businesses with their own BIN keep it, so existing b<BIN> place ids never change
    found = bins_for_lots(b[~bin_ok], bbl.where(bbl_ok)[~bin_ok]).reindex(b.index)
    key = ("BBL:" + bbl).where(bbl_ok, "TXT:" + b["street"].fillna("") + "|" + b["zip"].fillna("").astype(str))
    key = ("BIN:" + found).where(found.notna(), key)
    return ("BIN:" + bin_).where(bin_ok, key)


def max_concurrent(g: pd.DataFrame) -> int:
    ev = np.concatenate([np.ones(len(g)), -np.ones(len(g))])
    t = np.concatenate([g["open_date"].values, g["end_date"].values])
    order = np.lexsort((ev, t))  # closes before opens on the same day
    return int(np.cumsum(ev[order]).max())


def predecessors(b: pd.DataFrame) -> pd.DataFrame:
    """For each business: closed tenants of its building that ended before it opened."""
    x = b[["business_id", "building_key", "open_date", "end_date", "closed", "lifespan_days"]]
    prior = x[x["closed"]].rename(columns={"business_id": "prev_id", "end_date": "prev_end",
                                           "lifespan_days": "prev_life"})[
        ["building_key", "prev_id", "prev_end", "prev_life"]]
    m = x.merge(prior, on="building_key")
    m = m[(m["prev_end"] <= m["open_date"]) & (m["prev_id"] != m["business_id"])]
    m = m.sort_values("prev_end")
    agg = m.groupby("business_id").agg(n_prior_tenants=("prev_id", "size"),
                                       prev_end=("prev_end", "last"), prev_lifespan_days=("prev_life", "last"))
    agg["prev_gap_days"] = (b.set_index("business_id").loc[agg.index, "open_date"] - agg["prev_end"]).dt.days
    return agg.drop(columns=["prev_end"]).reset_index()


def main() -> None:
    b = pd.read_parquet(OUT / "businesses.parquet")
    b = b.drop(columns=[c for c in ("building_key", "n_prior_tenants", "prev_lifespan_days",
                                    "prev_gap_days", "multi_tenant_building") if c in b])
    b = snap_to_lots(b)
    b["building_key"] = building_key(b)
    seen = b[b["end_date"] >= FIRST_COPY]
    g = seen.groupby("building_key")
    bld = pd.DataFrame({
        "n_businesses": g.size(),
        "n_open_now": g["closed"].apply(lambda s: int((~s).sum())),
        "n_closed": g["closed"].sum().astype(int),
        "median_closed_lifespan_days": g.apply(lambda d: d.loc[d["closed"], "lifespan_days"].median()),
        "max_concurrent": g.apply(max_concurrent),
        "lat": g["lat"].median(), "lon": g["lon"].median(),
        "bbl": g["bbl"].first(), "boro": g["boro"].first(), "nta2020": g["nta2020"].first(),
        "first_open": g["open_date"].min(),
    }).reset_index()
    bld["multi_tenant_building"] = bld["max_concurrent"] >= MULTI_TENANT
    b = b.merge(predecessors(b), on="business_id", how="left")
    b["n_prior_tenants"] = b["n_prior_tenants"].fillna(0).astype(int)
    b = b.merge(bld[["building_key", "multi_tenant_building"]], on="building_key", how="left")
    b.to_parquet(OUT / "businesses.parquet", index=False)
    bld.to_parquet(OUT / "buildings.parquet", index=False)
    single = bld[~bld["multi_tenant_building"]]
    print(f"buildings {len(bld):,} (multi-tenant {bld['multi_tenant_building'].sum():,}); "
          f"single-storefront buildings with 5+ businesses since 2012: {(single['n_businesses'] >= 5).sum():,}; "
          f"max {single['n_businesses'].max()}; businesses with 3+ prior tenants "
          f"{(b['n_prior_tenants'] >= 3).sum():,}")


if __name__ == "__main__":
    main()
