"""Chain vs independent.

Two ingredients:
1. National/regional chain brand names from Wikipedia list pages (MediaWiki API, CC BY-SA),
   first wikilink of each bullet / table row.
2. NYC multi-location brands from DOHMH DBAs: brand key = normalised DBA with store numbers
   stripped; a CAMIS whose DBA starts with a Wikipedia brand key gets that key instead.

Rules (see analysis_inputs.md):
  nyc_max_concurrent = max over years of brand CAMIS active that year (first_insp..last seen)
  generic_name = brand key with no distinctive token (only generic food words / first names), e.g. JOES PIZZA
  weak_name = multi-word key with exactly one distinctive token (KENNEDY FRIED CHICKEN)
  is_chain_strict = wiki_chain or (nyc_max_concurrent >= 3 [>= 5 if weak_name] and not generic_name)
  is_chain_loose  = wiki_chain or nyc_n_addresses >= 3

Outputs: chain_brands_wikipedia.csv, chain_brands_nyc.parquet, camis_chain.parquet
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from ai_common import OUT, SRC, WEB, log, norm_name, write_out

PAGES = [
    "List_of_restaurant_chains_in_the_United_States", "List_of_fast_food_restaurant_chains",
    "List_of_coffeehouse_chains", "List_of_pizza_chains_of_the_United_States",
    "List_of_casual_dining_restaurant_chains", "List_of_bakery_cafés", "List_of_doughnut_shops",
    "List_of_frozen_yogurt_companies", "List_of_ice_cream_parlor_chains", "List_of_fast_casual_restaurants",
    "List_of_bubble_tea_chains",
]
API = "https://en.wikipedia.org/w/api.php?action=parse&page={}&prop=wikitext&format=json&redirects=1"

GENERIC = set("""PIZZA PIZZERIA DELI DELICATESSEN GROCERY CHINESE KITCHEN RESTAURANT CAFE COFFEE BAKERY
GRILL BAR FOOD FOODS CHICKEN FRIED HOUSE EXPRESS GOURMET NEW YORK NY BROOKLYN BRONX QUEENS GOLDEN
DRAGON CHINA WOK GARDEN STAR AND SUSHI TACO TACOS BURGER BURGERS BAGEL BAGELS JUICE BAR TEA PALACE
SPOT CORNER PLACE BEST FAMOUS ORIGINAL HOT FRESH SUPER KING CITY MARKET LUNCH DINER CUISINE TASTE
GYRO HALAL ITALIAN MEXICAN THAI INDIAN JAPANESE KOREAN SPANISH LATIN CARIBBEAN WINGS BBQ NOODLE
NOODLES DUMPLING DUMPLINGS SALAD SALADS FRUIT ICE CREAM DONUT DONUTS TAKE OUT WAY LITTLE GRAND
EMPIRE ROYAL GREAT LUCKY HAPPY ONE NO 1 2 OF THE A""".split())
# common first names / possessives: "JOES PIZZA", "MIKES" are homonyms, not brands
NAMES = set("""JOES TONYS TONY SAMS SAM MARIOS MARIO JOHNS JOHN MIKES MIKE NICKS NICK FRANKS FRANK
SALS SAL JIMMYS JIMMY ANGELOS ANGELO PAULS PAUL DANNYS DANNY GEORGES GEORGE TOMS TOM POPS MAMAS
PAPAS MAMA PAPA ROSAS ROSA MARIAS MARIA""".split())


def wiki_brands() -> pd.DataFrame:
    d = SRC / "wikipedia"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in PAGES:
        f = d / f"{p}.json"
        if not f.exists():
            r = WEB.get(API.format(p))
            r.raise_for_status()
            f.write_bytes(r.content)
        j = json.loads(f.read_text())
        if "parse" not in j:
            raise RuntimeError(f"Wikipedia page {p} did not parse: {str(j)[:200]}")
        text = j["parse"]["wikitext"]["*"]
        rev = j["parse"].get("revid")
        # first wikilink per bullet line, and per table row
        chunks = [ln for ln in text.splitlines() if ln.startswith("*")]
        chunks += [blk for blk in text.split("\n|-") if blk.strip().startswith("|")]
        for ch in chunks:
            m = re.search(r"\[\[([^\]\|#]+)(?:\|([^\]]+))?\]\]", ch)
            if not m:
                continue
            name = (m.group(2) or m.group(1)).strip()
            if re.search(r"^(List of|Category:|File:|Image:)", m.group(1)):
                continue
            rows.append({"page": p, "revid": rev, "link": m.group(1).strip(), "name": name})
    w = pd.DataFrame(rows).drop_duplicates(["name"])
    w["brand_key"] = w["name"].map(norm_name)
    # drop non-brands: US states / big cities that appear as first link in some tables
    geo = set("""ALABAMA ALASKA ARIZONA ARKANSAS CALIFORNIA COLORADO CONNECTICUT DELAWARE FLORIDA GEORGIA
    HAWAII IDAHO ILLINOIS INDIANA IOWA KANSAS KENTUCKY LOUISIANA MAINE MARYLAND MASSACHUSETTS MICHIGAN
    MINNESOTA MISSISSIPPI MISSOURI MONTANA NEBRASKA NEVADA OHIO OKLAHOMA OREGON PENNSYLVANIA TENNESSEE
    TEXAS UTAH VERMONT VIRGINIA WASHINGTON WISCONSIN WYOMING CANADA MEXICO JAPAN CHINA""".split())
    w = w[w["brand_key"].notna() & ~w["brand_key"].isin(geo) & (w["brand_key"].str.len() >= 4)]
    w = w[~w["brand_key"].isin(GENERIC) & ~w["brand_key"].str.match(r"^(NEW YORK|NEW JERSEY|NORTH|SOUTH|WEST|EAST) ")]
    return w


def brand_of(dba_key: str | None, wiki_keys: list[str]) -> tuple[str | None, bool]:
    if not dba_key or dba_key in ("NA", "N A", "NONE", "NULL", "TBD", "UNKNOWN"):
        return None, False
    k = re.sub(r"\b(NO|STORE|UNIT|LOCATION)?\s*\d{2,}\b", " ", dba_key)
    k = re.sub(r"\s+", " ", k).strip() or dba_key
    for wk in wiki_keys:  # longest first
        if k == wk or k.startswith(wk + " "):
            return wk, True
    return k, False


def name_strength(k: str | None) -> int:
    """number of distinctive tokens (not generic food words or common first names)."""
    if not k:
        return 0
    return sum(t not in GENERIC and t not in NAMES for t in k.split())


def build():
    w = wiki_brands()
    write_out(w, "chain_brands_wikipedia", "en.wikipedia.org list pages (CC BY-SA 4.0); revids in file",
              "first wikilink of each bullet/table row, geography and generic words removed", fmt="csv")
    wiki_keys = sorted(set(w["brand_key"]), key=len, reverse=True)
    wiki_keys = [k for k in wiki_keys if (" " in k) or (len(k) >= 5 and name_strength(k) > 0)]  # short keys (e.g. 'BOJ') too ambiguous

    b = pd.read_parquet(OUT / "camis_base.parquet",
                        columns=["camis", "dba_key", "addr_key", "first_insp", "last_insp", "last_snap"])
    cache = {}
    res = []
    for k in b["dba_key"]:
        if k not in cache:
            cache[k] = brand_of(k, wiki_keys)
        res.append(cache[k])
    b["brand_key"] = [r[0] for r in res]
    b["wiki_chain"] = [r[1] for r in res]

    # concurrency by calendar year
    start = b["first_insp"].dt.year
    end = b[["last_insp", "last_snap"]].max(axis=1).dt.year
    years = np.arange(2010, 2027)
    act = pd.DataFrame({y: (start <= y) & (end >= y) for y in years})
    act["brand_key"] = b["brand_key"]
    per_year = act.groupby("brand_key")[list(years)].sum()
    brands = pd.DataFrame({
        "nyc_max_concurrent": per_year.max(axis=1),
        "nyc_peak_year": per_year.idxmax(axis=1),
    })
    g = b.groupby("brand_key")
    brands["nyc_n_camis"] = g["camis"].nunique()
    brands["nyc_n_addresses"] = g["addr_key"].nunique()
    brands["wiki_chain"] = g["wiki_chain"].any()
    brands = brands.reset_index()
    strength = brands["brand_key"].map(name_strength)
    brands["generic_name"] = strength.eq(0)
    brands["weak_name"] = strength.eq(1) & brands["brand_key"].str.contains(" ")
    need = np.where(brands["weak_name"], 5, 3)
    brands["is_chain_strict"] = brands["wiki_chain"] | ((brands["nyc_max_concurrent"] >= need) & ~brands["generic_name"])
    brands["is_chain_loose"] = brands["wiki_chain"] | (brands["nyc_n_addresses"] >= 3)
    write_out(brands[brands["nyc_n_addresses"] >= 2], "chain_brands_nyc", "camis_base + Wikipedia",
              "brands with >=2 NYC addresses ever; rules in module docstring")
    out = b[["camis", "brand_key"]].merge(brands, on="brand_key", how="left")
    write_out(out, "camis_chain", "chain_brands_nyc", "one row per CAMIS")
    log.info("strict chain share %.3f, loose %.3f, wiki %.3f", out.is_chain_strict.mean(),
             out.is_chain_loose.mean(), out.wiki_chain.mean())
    return out


if __name__ == "__main__":
    build()
