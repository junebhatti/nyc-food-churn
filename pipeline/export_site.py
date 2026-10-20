"""Export compact JSON for the site (web/public/data/), following the design handoff's data contract.

  summary.json        hero numbers and years
  buildings.json      columnar: one entry per building seen since 2012 (map columns/hexes)
  tenants.json        per building: its businesses, for the hover card / tap sheet (lazy-loaded)
  neighborhoods.json  NTA polygons + rent, 3-yr closure odds, places, median life, survival curve
  yearly.json         openings / closings per year and category (scrubber butterfly chart)
  cursed.json         top single-storefront buildings by tenant count, with full timelines
  land.json           borough outlines (the map's land plate, clipped to the shoreline)
  parks.json          parks of PARK_MIN_ACRES+ (NYC Parks Properties, enfh-gkve), drawn under the columns
Rent = mean storefront rent $/sq ft/yr (LL157, 2019-24). Closure odds and lifespans use
Kaplan-Meier on places opened since 2012-07-06, excluding bodegas (SNAP dates mean something
different). Run after the build_* steps: .venv/bin/python pipeline/export_site.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter

from analysis_common import FIRST_COPY
from build_lifespans import AI, OUT, RAW

WEB = OUT.parent.parent / "web" / "public" / "data"
YEARS = list(range(2012, 2027))
CATS = ["restaurant", "bar", "cafe", "bakery", "bodega"]
LIVE = pd.Timestamp("2026-10-16")
MIN_NTA = 60
PARK_MIN_ACRES = 12
PARKS_URL = ("https://data.cityofnewyork.us/resource/enfh-gkve.geojson"
             f"?$where=acres>{PARK_MIN_ACRES}&$limit=2000")
PARKS_CACHE = RAW / "gov" / "parks_large.geojson.gz"
FAMILY_LABEL = {
    "american": "American", "latin_caribbean": "Latin & Caribbean", "chinese": "Chinese",
    "cafe_coffee_tea": "Café", "pizza": "Pizza", "bakery_desserts": "Bakery & desserts",
    "japanese_korean": "Japanese & Korean", "mexican_texmex": "Mexican", "deli_sandwich_salad": "Deli & sandwiches",
    "southeast_asian_other_asian": "Asian", "italian": "Italian", "mideast_mediterranean": "Middle Eastern",
    "european": "European", "juice_beverages": "Juice", "chicken": "Chicken", "south_asian": "South Asian",
    "burgers_hotdogs": "Burgers & hot dogs", "jewish_kosher": "Kosher", "bbq_steak_southern": "BBQ & Southern",
    "seafood": "Seafood", "vegetarian_vegan": "Vegetarian", "african": "African", "other_unknown": "Other",
    "bar": "Bar", "bodega": "Bodega",
}


def yfrac(d: pd.Series) -> pd.Series:
    return (d.dt.year + (d.dt.dayofyear - 1) / 365.25).round(2)


def write(name: str, obj) -> None:
    WEB.mkdir(parents=True, exist_ok=True)
    s = json.dumps(obj, separators=(",", ":"), allow_nan=False)
    (WEB / name).write_text(s)
    print(f"  {name}: {len(s) / 1e6:.2f} MB ({len(gzip.compress(s.encode())) / 1e6:.2f} MB gz)")


def clean(x):
    """JSON-safe scalar: NaN, inf, pd.NA and None become null."""
    if x is None or (not isinstance(x, (str, list, dict)) and pd.isna(x)):
        return None
    return None if isinstance(x, float) and not np.isfinite(x) else x


def load() -> pd.DataFrame:
    b = pd.read_parquet(OUT / "businesses.parquet")
    b = b[(b["end_date"] >= FIRST_COPY) & b["lat"].between(40.4, 41.0)].copy()
    b["event"] = b["closed"].astype(bool) & ~b["relocated"].fillna(False).astype(bool)
    b["years"] = b["lifespan_days"] / 365.25
    b["family"] = b["family"].where(b["source"] == "dohmh", b["site_category"])
    b["label"] = b["family"].map(FAMILY_LABEL).fillna("Other")
    b["o"], b["c"] = yfrac(b["open_date"]), yfrac(b["close_date"])
    return b


def place_id(building_key: str) -> str:
    """Stable, URL-safe id for /place/<id>: b<BIN>, l<BBL>, or t<hash> for text-only addresses."""
    kind, _, val = building_key.partition(":")
    if kind == "BIN":
        return f"b{val}"
    if kind == "BBL":
        return f"l{val}"
    return "t" + hashlib.md5(val.encode()).hexdigest()[:10]


def shard_of(pid: str, n: int = 128) -> int:
    """FNV-1a 32-bit; web/lib/places.ts uses the same function to find a place's shard file."""
    h = 0x811C9DC5
    for ch in pid.encode():
        h = ((h ^ ch) * 0x01000193) & 0xFFFFFFFF
    return h % n


def address_of(row) -> str:
    street = f"{row['building']} {row['street']}" if isinstance(row.get("building"), str) else str(row["street"])
    # .title() turns "5th" into "5Th"; put ordinals back in lower case
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), " ".join(street.split()).title())


def lit_masks(b: pd.DataFrame) -> pd.DataFrame:
    """Per business, a 15-bit mask of the years 2012..2026 it was open at any point."""
    m = np.zeros(len(b), dtype=np.int64)
    end = b["end_date"].fillna(LIVE)
    for i, y in enumerate(YEARS):
        on = (b["open_date"] <= pd.Timestamp(f"{y}-12-31")) & (end >= pd.Timestamp(f"{y}-01-01"))
        m |= on.values.astype(np.int64) << i
    return b.assign(mask=m)


def km(d: pd.DataFrame) -> tuple[float, float, list]:
    f = KaplanMeierFitter().fit(d["years"], d["event"])
    s = f.survival_function_at_times(range(0, 11)).values
    return float(f.median_survival_time_), float(1 - s[3]), [round(float(v), 3) for v in s]


def neighborhoods(b: pd.DataFrame) -> list[dict]:
    g = gpd.read_file(f"/vsigzip/{RAW / 'gov' / 'geo_nta2020.geojson.gz'}")
    g["geometry"] = g.geometry.simplify(0.0002, preserve_topology=True)
    rent = pd.read_parquet(AI / "nta_year_rent.parquet")
    rent = rent[rent["year"].between(2019, 2024)].groupby("nta2020")["ll157_rent_psf_yr"].mean()
    coh = b[(b["open_date"] >= FIRST_COPY) & (b["site_category"] != "bodega")]
    out = []
    for _, r in g.iterrows():
        code = r["nta2020"]
        d = coh[coh["nta2020"] == code]
        places = int((b["nta2020"] == code).sum())
        stats = km(d) if len(d) >= MIN_NTA else (None, None, None)
        geom = json.loads(gpd.GeoSeries([r.geometry]).to_json())["features"][0]["geometry"]
        geom = json.loads(json.dumps(geom), parse_float=lambda v: round(float(v), 5))
        out.append({"id": code, "name": r["ntaname"], "boro": r["boroname"], "places": places,
                    "rent": clean(round(float(rent[code]), 1)) if code in rent and pd.notna(rent[code]) else None,
                    "closure3y": clean(round(stats[1], 3)) if stats[1] is not None else None,
                    "medianLife": clean(round(stats[0], 2)) if stats[0] is not None else None,
                    "curve": stats[2], "geometry": geom})
    return out


def buildings(b: pd.DataFrame, nta: dict) -> tuple[dict, list]:
    b = lit_masks(b)
    rows, tenants = [], []
    for i, (key, d) in enumerate(b.sort_values("open_date").groupby("building_key", sort=False)):
        cmask = [int(np.bitwise_or.reduce(d.loc[d["site_category"] == c, "mask"].values)) if (d["site_category"] == c).any() else 0
                 for c in CATS]
        closed = d.loc[d["event"], "years"]
        last = d.iloc[-1]
        rows.append([place_id(key), round(float(d["lat"].median()), 5), round(float(d["lon"].median()), 5), len(d),
                     clean(round(float(closed.median()), 2)) if len(closed) else None,
                     nta.get(last["nta2020"]), *cmask])
        tenants.append([address_of(last), last["nta2020"] if isinstance(last["nta2020"], str) else None,
                        [[str(t["dba"]).strip()[:48], CATS.index(t["site_category"]), t["label"], clean(t["o"]),
                          clean(t["c"]) if t["event"] else None] for _, t in d.iterrows()]])
    cols = ["id", "lat", "lon", "tenants", "medianLife", "nta", *[f"lit_{c}" for c in CATS]]
    return {"columns": cols, "rows": rows}, tenants


def year_series(d: pd.DataFrame) -> dict:
    end = d["end_date"].fillna(LIVE)
    return {"open": [int((d["open_date"].dt.year == y).sum()) for y in YEARS],
            "close": [int((d["event"] & (d["close_date"].dt.year == y)).sum()) for y in YEARS],
            "alive": [int(((d["open_date"] <= pd.Timestamp(f"{y}-12-31")) & (end >= pd.Timestamp(f"{y}-01-01"))).sum())
                      for y in YEARS]}


def yearly(b: pd.DataFrame) -> dict:
    out = {c: year_series(b if c == "all" else b[b["site_category"] == c]) for c in CATS + ["all"]}
    return {"years": YEARS, **out}


def yearly_by_nta(b: pd.DataFrame) -> dict:
    """The scrubber's openings/closings/open counts for each neighbourhood and category."""
    out = {}
    for code, d in b.dropna(subset=["nta2020"]).groupby("nta2020"):
        out[code] = {c: year_series(d if c == "all" else d[d["site_category"] == c]) for c in CATS + ["all"]}
    return out


def max_open_at_once(d: pd.DataFrame) -> int:
    t = np.concatenate([d["open_date"].values, d["end_date"].fillna(LIVE).values])
    ev = np.concatenate([np.ones(len(d)), -np.ones(len(d))])
    return int(np.cumsum(ev[np.lexsort((ev, t))]).max())


def cursed(b: pd.DataFrame, names: dict, nta_life: dict, n: int = 50) -> list[dict]:
    """True single storefronts (at most 2 tenants open at once, allowing for fuzzy dates), counting
    restaurants, bars, cafes and bakeries only; bodega SNAP dates are too rough for timelines."""
    f = b[b["site_category"] != "bodega"]
    g = f.groupby("building_key")
    bld = pd.DataFrame({"n": g.size(), "conc": g.apply(max_open_at_once),
                        "med": g.apply(lambda d: d.loc[d["event"], "years"].median())}).reset_index()
    top = bld[bld["conc"] <= 2].sort_values(["n", "med"], ascending=[False, True]).head(n)
    span0, span1 = 2012.51, yfrac(pd.Series([LIVE])).iloc[0]
    out = []
    for rank, (_, r) in enumerate(top.iterrows(), 1):
        d = f[f["building_key"] == r["building_key"]].sort_values("open_date")
        end = d["c"].where(d["event"], span1)
        cover = np.zeros(int((span1 - span0) * 365) + 1, bool)
        for o, e in zip(d["o"].clip(lower=span0), end):
            cover[int((o - span0) * 365):max(int((e - span0) * 365), 0)] = True
        last = d.iloc[-1]
        street = f"{last['building']} {last['street']}" if isinstance(last.get("building"), str) else str(last["street"])
        out.append({"rank": rank, "id": place_id(r["building_key"]), "address": address_of(last),
                    "neighborhood": names.get(last["nta2020"], ""), "boro": str(last["boro"]).title(),
                    "lat": round(float(d["lat"].median()), 5), "lon": round(float(d["lon"].median()), 5),
                    "tenants": len(d), "medianLife": clean(round(float(d.loc[d["event"], "years"].median()), 2)),
                    "vacantPct": round(float(1 - cover.mean()), 3), "areaMedianLife": nta_life.get(last["nta2020"]),
                    "timeline": [{"name": str(t["dba"]).strip(), "cuisine": t["label"], "price": clean(t.get("price_tier")),
                                  "open": clean(t["o"]), "close": clean(t["c"]) if t["event"] else None,
                                  "life": round(float(t["years"]), 2), "isOpen": not t["event"]}
                                 for _, t in d.iterrows()]})
    return out


def parks() -> dict:
    """Large parks, fetched once from NYC Open Data and cached in data/raw/gov/."""
    if not PARKS_CACHE.exists():
        import requests
        r = requests.get(PARKS_URL, timeout=120)
        r.raise_for_status()
        PARKS_CACHE.write_bytes(gzip.compress(r.content))
    g = gpd.read_file(f"/vsigzip/{PARKS_CACHE}")
    g = g[g.geometry.notna()].copy()
    g["geometry"] = g.geometry.simplify(0.00012, preserve_topology=True)
    g = g[~g.geometry.is_empty]
    out = json.loads(g[["geometry"]].to_json(), parse_float=lambda v: round(float(v), 5))
    print(f"  parks: {len(g)} of {PARK_MIN_ACRES}+ acres")
    return out


def main() -> None:
    b = load()
    hoods = neighborhoods(b)
    names = {h["id"]: h["name"] for h in hoods}
    nta_life = {h["id"]: h["medianLife"] for h in hoods}
    nta_idx = {h["id"]: i for i, h in enumerate(hoods)}
    bld, tenants = buildings(b, nta_idx)
    _, _, curve = km(b[(b["open_date"] >= FIRST_COPY) & (b["site_category"] != "bodega")])
    med = km(b[(b["open_date"] >= FIRST_COPY) & (b["site_category"] != "bodega")])[0]
    summary = {"opened": int(len(b)), "openNow": int((~b["event"] & ~b["closed"].astype(bool)).sum()),
               "medianLife": round(med, 1), "years": YEARS, "categories": CATS, "liveDate": str(LIVE.date()),
               "buildings": len(bld["rows"])}
    print("exporting to", WEB)
    write("summary.json", summary)
    write("neighborhoods.json", hoods)
    write("buildings.json", bld)
    write("tenants.json", tenants)
    write("yearly.json", yearly(b))
    write("yearly_nta.json", yearly_by_nta(b))
    write("cursed.json", cursed(b, names, nta_life))
    land = gpd.read_file(f"/vsigzip/{RAW / 'gov' / 'geo_boroughs.geojson.gz'}")
    land["geometry"] = land.geometry.simplify(0.0003, preserve_topology=True)
    write("land.json", json.loads(land[["geometry"]].to_json(), parse_float=lambda v: round(float(v), 5)))
    write("parks.json", parks())
    print(summary)


if __name__ == "__main__":
    main()
