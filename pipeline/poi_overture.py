"""Overture Maps places -> data/raw/poi/overture_<release>.parquet

Releases come from two anonymous buckets:
  * official S3 (s3://overturemaps-us-west-2/release/) - keeps only the last ~3 releases
  * Fused's mirror on Source Cooperative (data.source.coop/fused/overture/) - 2024-02 .. 2026-05
Schemas drift across releases (categories.main -> categories.primary -> taxonomy.*,
bbox.minx -> bbox.xmin, sources.recordId -> record_id), so SQL is built per release.
"""
from __future__ import annotations

import re

from poi_common import XMAX, XMIN, YMAX, YMIN, clip_and_write, connect, s3_list, s3_prefixes

OFFICIAL = "https://overturemaps-us-west-2.s3.amazonaws.com/"
FUSED = "https://data.source.coop/fused/overture/"

BAR = {"bar", "pub", "lounge", "brewery", "winery", "distillery", "cidery", "meadery", "brewpub",
       "speakeasy", "tavern", "gastropub", "nightlife", "nightclub", "night", "taproom", "saloon",
       "alcoholic", "biergarten", "beer_garden", "hookah", "karaoke"}
CAFE = {"cafe", "coffee", "tea", "juice", "smoothie", "non_alcoholic_beverage_venue"}
SWEET = {"bakery", "dessert", "ice_cream", "donut", "doughnut", "bagel", "cupcake", "yogurt", "gelato",
         "candy", "chocolatier", "chocolate", "patisserie", "pastry", "macaron", "cake", "creperie"}
RETAIL = {"delicatessen", "deli", "grocery_store", "convenience_store", "liquor_store", "supermarket", "butcher_shop",
          "seafood_market", "farmers_market", "health_food_store", "specialty_foods_store",
          "food_and_beverage_store", "beer_wine_spirits_store", "imported_food_store",
          "frozen_foods_store", "food_truck", "food_truck_stand", "food_stand", "bodega",
          "wine_store", "beverage_store", "cheese_shop", "meat_shop", "fruits_and_vegetables",
          "coffee_and_tea_supplies", "food", "gas_station_convenience_store"}
EXCLUDE = {"food_delivery_service", "pizza_delivery_service", "catering", "caterer", "wine_wholesaler",
           "barber", "bartender", "internet_cafe", "pet_cafe", "food_consultant", "food_safety_training",
           "bar_crawl", "food_bank", "food_tours", "beer_wine_and_spirits_wholesaler", "bakery_equipment"}


def map_category(cat: str | None, top: str | None = None, mid: str | None = None) -> str | None:
    """Map an Overture category leaf (old or new taxonomy) to our 5 buckets."""
    if top and top not in ("food_and_drink", "shopping", "arts_and_entertainment"):
        return None
    if not cat or cat in EXCLUDE or "wholesale" in cat or "supplier" in cat or "equipment" in cat:
        return None
    toks = set(cat.split("_"))
    if cat in RETAIL or cat.endswith("grocery_store"):
        return "other_food"
    if "juice" in toks or "smoothie" in toks or "bubble" in toks:
        return "cafe_coffee"
    if (toks & SWEET or "ice_cream" in cat) and "restaurant" not in toks:
        return "bakery_dessert"
    if toks & {"cafe", "coffee", "tea"} and "restaurant" not in toks:
        return "cafe_coffee"
    if toks & BAR and not toks & {"sushi", "salad", "oyster", "noodle", "raw", "snack", "tapas", "milk",
                                    "restaurant", "market", "rental"}:
        return "bar"
    if "restaurant" in toks or cat in {"diner", "cafeteria", "buffet", "food_court", "sandwich_shop",
                                        "casual_eatery", "pizza", "eat_and_drink", "food_and_drink",
                                        "snack_bar", "sushi_bar", "salad_bar", "noodles", "bistro",
                                        "brasserie", "canteen", "taqueria", "hot_dog", "burgers",
                                        "fish_and_chips", "poke", "empanadas", "dumpling"}:
        return "restaurant"
    if top == "food_and_drink":  # new taxonomy catch-all
        return {"alcoholic_beverage_venue": "bar", "non_alcoholic_beverage_venue": "cafe_coffee"}.get(mid, "restaurant")
    return None


def releases() -> dict[str, list[str]]:
    rel: dict[str, list[str]] = {}
    # Source Cooperative quirk: `prefix` is relative to the repo, returned keys include "overture/".
    for p in s3_prefixes(FUSED, ""):
        m = re.match(r"overture/(\d{4}-\d\d-\d\d)-(alpha-|beta-)?(\d+)/$", p)
        if not m:
            continue
        tag = m.group(2)[:-1] if m.group(2) else None
        name = f"{m.group(1)}-{tag}.{m.group(3)}" if tag else f"{m.group(1)}.{m.group(3)}"
        keys = [k for k, _ in s3_list(FUSED, p.removeprefix("overture/") + "theme=places/type=place/")
                if k.endswith(".parquet")]
        if keys:
            rel[name] = ["https://data.source.coop/fused/" + k for k in keys]
    for p in s3_prefixes(OFFICIAL, "release/"):
        name = p.split("/")[1]
        keys = [k for k, _ in s3_list(OFFICIAL, p + "theme=places/type=place/") if k.endswith(".parquet")]
        if keys:
            rel[name] = [OFFICIAL + k for k in keys]  # official copy wins on overlap
    return rel


def release_sql(con, urls: list[str], release: str) -> str:
    cols = {r[0]: r[1] for r in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{urls[-1]}')").fetchall()}
    bx = ("bbox.xmin", "bbox.xmax", "bbox.ymin", "bbox.ymax") if "xmin" in cols["bbox"] else \
         ("bbox.minx", "bbox.maxx", "bbox.miny", "bbox.maxy")
    if "taxonomy" in cols:
        cat, top, mid = "taxonomy.primary", "taxonomy.hierarchy[1]", "taxonomy.hierarchy[2]"
        alt = "taxonomy.alternates"
    else:
        key = "main" if '"primary"' not in cols["categories"] and "primary" not in cols["categories"] else "primary"
        cat, top, mid, alt = f"categories.{key}", "NULL::VARCHAR", "NULL::VARCHAR", "categories.alternate"
    rid = "record_id" if "record_id" in cols["sources"] else "recordId"
    status = "operating_status" if "operating_status" in cols else "NULL::VARCHAR"
    basic = "basic_category" if "basic_category" in cols else "NULL::VARCHAR"
    upd = "s.update_time" if "update_time" in cols["sources"] else "NULL::VARCHAR"
    return f"""
    SELECT id, names.primary AS name, {cat} AS cat, {top} AS top, {mid} AS mid, {alt} AS alt,
           confidence, {status} AS operating_status, {basic} AS basic_category,
           ({bx[0]} + {bx[1]}) / 2 AS lon, ({bx[2]} + {bx[3]}) / 2 AS lat,
           addresses[1] AS addr,
           list_transform(sources, s -> {{'dataset': s.dataset, 'record_id': s.{rid}, 'update_time': {upd}}}) AS srcs
    FROM read_parquet({urls}, union_by_name=true)
    WHERE {bx[0]} BETWEEN {XMIN} AND {XMAX} AND {bx[2]} BETWEEN {YMIN} AND {YMAX}
    """


def run(only: set[str] | None = None) -> None:
    con = connect()
    con.sql("SET s3_region='us-west-2'")
    con.create_function("map_category", map_category, ["VARCHAR", "VARCHAR", "VARCHAR"], "VARCHAR",
                        null_handling="special")
    rels = releases()
    print(f"overture releases reachable: {sorted(rels)}")
    for rel, urls in sorted(rels.items()):
        if only and rel not in only:
            continue
        print(f"overture {rel}: {len(urls)} files")
        con.sql(f"CREATE OR REPLACE TEMP TABLE _ov AS {release_sql(con, urls, rel)}")
        d = rel[:10]
        norm = f"""
        SELECT 'overture' AS source, id AS source_id, name, cat AS category_raw,
               map_category(cat, top, mid) AS category, lat, lon,
               concat_ws(', ', addr.freeform, addr.locality, addr.region, addr.postcode) AS address,
               NULL::DATE AS date_created,
               NULL::DATE AS date_closed,
               DATE '{d}' AS first_seen, DATE '{d}' AS last_seen,
               json_object('release', '{rel}', 'confidence', confidence,
                           'operating_status', operating_status, 'basic_category', basic_category,
                           'alternates', alt, 'sources', srcs)::VARCHAR AS extra
        FROM _ov
        """
        clip_and_write(con, norm, f"overture_{rel}.parquet")
