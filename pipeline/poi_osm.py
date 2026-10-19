"""OpenStreetMap (current) via Overpass -> data/raw/poi/osm_overpass.parquet

Pulls live food/drink POIs plus lifecycle-prefixed ones (disused:/was:/closed:/... amenity|shop)
and keeps start_date / end_date / opening_date / check_date tags plus the element's last-edit
timestamp & version (out meta).
"""
from __future__ import annotations

import json
import subprocess
import time

import pandas as pd

from poi_common import OUT, XMAX, XMIN, YMAX, YMIN, clip_and_write, connect

UA = "nyc-food-churn/0.1 (research; contact via github)"
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter",
             "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
AMENITY = "restaurant|cafe|bar|pub|fast_food|ice_cream|biergarten|food_court|nightclub"
SHOP = "bakery|coffee|deli|confectionery|pastry|tea|beverages|alcohol|wine|chocolate|ice_cream|convenience"
LIFE = "disused|was|closed|abandoned|removed|demolished|razed|former|vacant"
BBOX = f"{YMIN},{XMIN},{YMAX},{XMAX}"
QUERY = f"""[out:json][timeout:600][bbox:{BBOX}];
(
  nwr["amenity"~"^({AMENITY})$"];
  nwr["shop"~"^({SHOP})$"];
  nwr[~"^({LIFE}):amenity$"~"^({AMENITY})$"];
  nwr[~"^({LIFE}):shop$"~"^({SHOP})$"];
);
out center meta;"""

CAT = {"restaurant": "restaurant", "fast_food": "restaurant", "food_court": "restaurant",
       "bar": "bar", "pub": "bar", "biergarten": "bar", "nightclub": "bar",
       "cafe": "cafe_coffee", "coffee": "cafe_coffee", "tea": "cafe_coffee",
       "ice_cream": "bakery_dessert", "bakery": "bakery_dessert", "pastry": "bakery_dessert",
       "confectionery": "bakery_dessert", "chocolate": "bakery_dessert",
       "deli": "other_food", "beverages": "other_food", "alcohol": "other_food",
       "wine": "other_food", "convenience": "other_food"}
LIFE_PREFIXES = LIFE.split("|")


def overpass(query: str) -> dict:
    """POST via curl: the venv's Python links LibreSSL 2.8, which fails the TLS handshake
    with overpass-api.de. Rotates endpoints and retries on 429/504."""
    last = None
    for attempt in range(8):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        p = subprocess.run(["curl", "-sS", "--max-time", "1200", "-A", UA, "-w", "\\n%{http_code}",
                            "--data-urlencode", f"data={query}", url], capture_output=True, text=True)
        body, _, code = p.stdout.rpartition("\n")
        if p.returncode == 0 and code == "200":
            return json.loads(body)
        last = f"{url}: curl rc={p.returncode} http={code} {p.stderr[:200]} {body[:200]}"
        print(f"  overpass retry {attempt + 1}: {last}")
        time.sleep(60)
    raise RuntimeError(f"Overpass failed after retries: {last}")


def classify(tags: dict) -> tuple[str | None, str | None, str | None]:
    """Return (raw_tag, category, lifecycle_prefix or None)."""
    for k in ("amenity", "shop"):
        v = tags.get(k)
        if v in CAT:
            return f"{k}={v}", CAT[v], None
    for p in LIFE_PREFIXES:
        for k in ("amenity", "shop"):
            v = tags.get(f"{p}:{k}")
            if v in CAT:
                return f"{p}:{k}={v}", CAT[v], p
    return None, None, None


def run() -> None:
    print("osm overpass: querying NYC bbox")
    data = overpass(QUERY)
    rows = []
    for e in data["elements"]:
        t = e.get("tags", {})
        raw, cat, life = classify(t)
        if not cat:
            continue
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        addr = ", ".join(x for x in (addr, t.get("addr:city"), t.get("addr:postcode")) if x)
        dates = {k: v for k, v in t.items() if any(s in k for s in ("date", "check_date", "survey"))}
        rows.append({
            "source": "osm", "source_id": f"{e['type'][0]}{e['id']}",
            "name": t.get("name") or t.get(f"{life}:name") or t.get("old_name"),
            "category_raw": raw, "category": cat, "lat": lat, "lon": lon, "address": addr or None,
            "start_date": t.get("start_date") or t.get("opening_date"),
            "end_date": t.get("end_date"),
            "osm_timestamp": e.get("timestamp"),
            "extra": json.dumps({"lifecycle": life, "version": e.get("version"),
                                 "timestamp": e.get("timestamp"), "date_tags": dates,
                                 "cuisine": t.get("cuisine"), "brand": t.get("brand"),
                                 "website": t.get("website")}),
        })
    print(f"  {len(data['elements']):,} elements, {len(rows):,} classified")
    tmp = OUT / "_osm_tmp.parquet"
    pd.DataFrame(rows).to_parquet(tmp)
    con = connect()
    try:
        clip_and_write(con, f"""
            SELECT source, source_id, name, category_raw, category, lat, lon, address,
                   try_cast(CASE WHEN length(start_date) = 4 THEN start_date || '-01-01'
                                 WHEN length(start_date) = 7 THEN start_date || '-01' ELSE start_date END AS DATE) AS date_created,
                   try_cast(CASE WHEN length(end_date) = 4 THEN end_date || '-01-01'
                                 WHEN length(end_date) = 7 THEN end_date || '-01' ELSE end_date END AS DATE) AS date_closed,
                   NULL::DATE AS first_seen,
                   current_date AS last_seen,  -- present in OSM at query time; last edit is extra.timestamp
                   extra
            FROM '{tmp}'""", "osm_overpass.parquet")
    finally:
        tmp.unlink()
