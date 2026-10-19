"""Normalize fetched menus, match to CAMIS -> data/raw/menus/

  menupages.parquet        one row per MenuPages restaurant capture (name, address, lat/lon,
                           snapshot_date, price_level, median_main_price, n_items_priced, camis)
  menupages_items.parquet  priced items (slug, ts, section, item, price)
"""
from __future__ import annotations

import pandas as pd

from menus_common import OUT
from menus_match import match
from menus_wayback import FAILED, PARSED, load_parsed

# MenuPages' own key: avg dinner entree $ <7, 7-12, 12-18, 18-25, >25 (1-5 $ signs)
NUM = ["lat", "lon", "median_main_price", "median_item_price", "p75_item_price"]


def build() -> pd.DataFrame:
    recs = load_parsed()
    items = [(r["slug"], r["ts"], s, n, p) for r in recs for s, n, p in r.get("items", [])]
    it = pd.DataFrame(items, columns=["slug", "ts", "section", "item", "price"])
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "items"} for r in recs])
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["snapshot_date"] = pd.to_datetime(df.ts.str[:8], format="%Y%m%d")
    df["price_level_n"] = df.price_level.str.len()
    df["source"] = "menupages_wayback"
    # keep NYC records only (www host is NYC, but guard on ZIP/coords)
    nyc = df.zip.fillna("").str.match(r"^(100|101|102|103|104|110|111|112|113|114|116)\d\d") | \
        (df.lat.between(40.45, 40.95) & df.lon.between(-74.30, -73.65))
    print(f"parsed {len(df):,}; NYC by zip/coords {nyc.sum():,}; "
          f"with price level {df.price_level.notna().sum():,}; with items {df.n_items_priced.gt(0).sum():,}")
    df = df[nyc].copy()
    parts = df.street.fillna("").str.extract(r"^\s*([0-9][0-9A-Za-z/ -]*?)\s+(.*)$")
    src = pd.DataFrame({"id": df.slug, "name": df.name, "house": parts[0], "street": parts[1],
                        "zip": df.zip, "lat": df.lat, "lon": df.lon, "year": df.snapshot_date.dt.year})
    m = match(src)
    df = df.merge(m.rename(columns={"id": "slug"}), on="slug", how="left")
    rate = df.camis.notna().mean()
    print(f"matched to CAMIS: {df.camis.notna().sum():,}/{len(df):,} ({rate:.1%}); by method:\n"
          f"{df.match_method.value_counts(dropna=False).to_string()}")
    cols = ["source", "slug", "name", "street", "locality", "zip", "lat", "lon", "cross", "hood",
            "cuisine", "snapshot_date", "price_level", "price_level_n", "median_main_price",
            "n_main_items", "median_item_price", "p75_item_price", "n_items_priced", "url",
            "camis", "match_method", "match_sim", "n_candidates"]
    df = df.rename(columns={"cuisine": "cuisine"})[cols]
    df.to_parquet(OUT / "menupages.parquet", index=False)
    it.to_parquet(OUT / "menupages_items.parquet", index=False)
    print(f"wrote menupages.parquet ({len(df):,}) and menupages_items.parquet ({len(it):,})")
    if FAILED.exists():
        print(f"failed fetches: {sum(1 for _ in open(FAILED)):,} (see {FAILED.name})")
    return df


if __name__ == "__main__":
    build()
