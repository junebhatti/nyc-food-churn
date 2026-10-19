"""Menus and price tiers. Outputs in data/raw/menus/ (see data/notes/menus.md).

    .venv/bin/python pipeline/fetch_menus.py [steps...]   # default: all, in order

  cdx      MenuPages Wayback CDX index (154 pages, ~1-2 h; resumable)
  select   one capture per MenuPages slug
  fetch    download + parse chosen captures (resumable JSONL; ~2/s with 2-3 workers)
  build    normalize -> menupages.parquet, menupages_items.parquet, CAMIS match
  proxies  per-CAMIS liquor / cuisine / chain / fast-food -> camis_proxies.parquet
  tiers    combined tier rule -> camis_price_tier.parquet, tier_source_by_open_year.csv
"""
from __future__ import annotations

import sys

import menus_build
import menus_match
import menus_proxies
import menus_tiers
import menus_wayback

STEPS = {
    "cdx": menus_wayback.cdx,
    "select": menus_wayback.select,
    "fetch": menus_wayback.fetch,
    "build": menus_build.build,
    "proxies": lambda: (menus_match.camis_base(rebuild=True), menus_proxies.build()),
    "tiers": menus_tiers.build,
}

if __name__ == "__main__":
    for step in sys.argv[1:] or list(STEPS):
        if step not in STEPS:
            sys.exit(f"unknown step {step!r}; choose from {list(STEPS)}")
        print(f"== {step}", flush=True)
        STEPS[step]()
