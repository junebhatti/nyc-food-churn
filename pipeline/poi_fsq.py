"""Foursquare Open Source Places -> data/raw/poi/fsq_<release>.parquet

Public copies: Fused's mirror on Source Cooperative (4 releases, 2024-11..2025-02).
Later monthly releases (2025-03 .. now) are only on the gated Hugging Face repo or
Foursquare's Places portal; they need a user token (set HF_TOKEN in .env.local after
accepting the terms at huggingface.co/datasets/foursquare/fsq-os-places).
"""
from __future__ import annotations

import os
import re

import requests

from poi_common import ROOT, XMAX, XMIN, YMAX, YMIN, clip_and_write, connect

FUSED = "https://data.source.coop/fused/fsq-os-places/"
HF_API = "https://huggingface.co/api/datasets/foursquare/fsq-os-places/tree/main/release"
HF_FILE = "https://huggingface.co/datasets/foursquare/fsq-os-places/resolve/main/"

# First food/drink label wins. Order matters: specific before general.
FOOD_LABEL = r"""(l LIKE 'Dining and Drinking%' OR l LIKE 'Retail > Food and Beverage Retail%'
                 OR l = 'Retail > Convenience Store' OR l = 'Arts and Entertainment > Night Club')"""
CAT_CASE = """
CASE
  WHEN lab LIKE 'Dining and Drinking > Bar%' OR lab = 'Arts and Entertainment > Night Club'
    OR regexp_matches(lab, '> (Brewery|Winery|Distillery|Meadery|Cidery|Vineyard)$') THEN 'bar'
  WHEN lab LIKE 'Dining and Drinking > Cafe, Coffee, and Tea House%'
    OR regexp_matches(lab, '> (Juice Bar|Smoothie Shop|Coffee Roaster)$') THEN 'cafe_coffee'
  WHEN regexp_matches(lab, 'Dining and Drinking > (Bakery|Dessert Shop|Bagel Shop|Donut Shop)')
    OR regexp_matches(lab, '> (Candy Store|Chocolate Store)$') THEN 'bakery_dessert'
  WHEN lab = 'Dining and Drinking > Restaurant > Deli' THEN 'other_food'
  WHEN regexp_matches(lab, 'Dining and Drinking > (Restaurant|Breakfast Spot|Food Court|Cafeteria|Creperie|Snack Place)')
    THEN 'restaurant'
  WHEN lab LIKE 'Dining and Drinking%' OR lab LIKE 'Retail > Food and Beverage Retail%'
    OR lab = 'Retail > Convenience Store' THEN 'other_food'
END"""


def fused_releases() -> dict[str, list[str]]:
    x = requests.get(FUSED, params={"prefix": ""}, timeout=120)
    x.raise_for_status()
    rel: dict[str, list[str]] = {}
    for k in re.findall(r"<Key>([^<]*\.parquet)</Key>", x.text):
        m = re.match(r"fsq-os-places/(\d{4}-\d\d-\d\d)/places/", k)
        if m:
            rel.setdefault(m.group(1), []).append("https://data.source.coop/fused/" + k)
    return rel


def hf_releases(token: str) -> dict[str, list[str]]:
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(HF_API, headers=h, timeout=120)
    r.raise_for_status()
    rel = {}
    for d in r.json():
        dt = d["path"].split("dt=")[-1]
        f = requests.get(f"{HF_API}/dt={dt}/places/parquet", headers=h, timeout=120)
        f.raise_for_status()
        rel[dt] = [HF_FILE + x["path"] for x in f.json() if x["path"].endswith(".parquet")]
    return rel


def norm_sql(urls: list[str], release: str) -> str:
    return f"""
    WITH raw AS (
      SELECT *, list_filter(fsq_category_labels, l -> {FOOD_LABEL})[1] AS lab
      FROM read_parquet({urls}, union_by_name=true)
      WHERE longitude BETWEEN {XMIN} AND {XMAX} AND latitude BETWEEN {YMIN} AND {YMAX}
    )
    SELECT 'fsq' AS source, fsq_place_id AS source_id, name,
           lab AS category_raw, {CAT_CASE} AS category,
           latitude AS lat, longitude AS lon,
           concat_ws(', ', address, locality, region, postcode) AS address,
           try_cast(date_created AS DATE) AS date_created,
           try_cast(date_closed AS DATE) AS date_closed,
           NULL::DATE AS first_seen, DATE '{release}' AS last_seen,
           json_object('release', '{release}', 'date_refreshed', date_refreshed,
                       'labels', fsq_category_labels, 'tel', tel, 'website', website,
                       'instagram', instagram, 'postcode', postcode)::VARCHAR AS extra
    FROM raw WHERE lab IS NOT NULL
    """


def _env_local(key: str) -> str | None:
    p = ROOT / ".env.local"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        k, _, v = line.partition("=")
        if k.strip() == key and v.strip():
            return v.strip().strip('"').strip("'")
    return None


def run(only: set[str] | None = None) -> None:
    con = connect()
    rels = fused_releases()
    token = os.environ.get("HF_TOKEN") or _env_local("HF_TOKEN")
    if token:
        hf = hf_releases(token)
        for k, v in hf.items():
            rels.setdefault(k, v)
        con.sql(f"CREATE SECRET hf (TYPE http, EXTRA_HTTP_HEADERS MAP {{'Authorization': 'Bearer {token}'}})")
    else:
        print("  HF_TOKEN not set: only the 4 public Fused mirror releases are reachable")
    for rel, urls in sorted(rels.items()):
        if only and rel not in only:
            continue
        print(f"fsq {rel}: {len(urls)} files")
        clip_and_write(con, norm_sql(urls, rel), f"fsq_{rel}.parquet")
