"""OSM full history via the ohsome API -> data/raw/poi/
  osm_ohsome_versions.parquet : every version of every NYC food/drink element since 2008
                                (valid_from / valid_to intervals, tags)
  osm_ohsome.parquet          : normalized, one row per (element, name-segment) = one business
                                tenure; first_seen/last_seen are OSM edit dates, not real open/close.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

import pandas as pd

from poi_common import OUT, XMAX, XMIN, YMAX, YMIN, clip_and_write, connect
from poi_osm import AMENITY, CAT, LIFE_PREFIXES, SHOP, UA

API = "https://api.ohsome.org/v1"
A, S = AMENITY.replace("|", ","), SHOP.replace("|", ",")
FILTER = (f"amenity in ({A}) or shop in ({S}) or disused:amenity in ({A}) or disused:shop in ({S})"
          f" or was:amenity in ({A}) or was:shop in ({S})")
DX, DY = 0.1, 0.1  # big tiles are far cheaper per area (fixed per-request cost ~30s); ~30 tiles


def post(endpoint: str, params: dict) -> dict:
    args = ["curl", "-sS", "--max-time", "900", "-A", UA, "-w", "\n%{http_code}"]
    for k, v in params.items():
        args += ["--data-urlencode", f"{k}={v}"]
    last = None
    for attempt in range(5):
        p = subprocess.run(args + [f"{API}/{endpoint}"], capture_output=True, text=True)
        body, _, code = p.stdout.rpartition("\n")
        if p.returncode == 0 and code == "200":
            return json.loads(body)
        last = f"rc={p.returncode} http={code} {p.stderr[:200]} {body[:300]}"
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"ohsome {endpoint} failed: {last}")


def metadata_end() -> str:
    p = subprocess.run(["curl", "-sS", "-A", UA, f"{API}/metadata"], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)["extractRegion"]["temporalExtent"]["toTimestamp"]


def tile(bbox: tuple[float, float, float, float], end: str) -> list[dict]:
    d = post("elementsFullHistory/centroid", {
        "bboxes": ",".join(f"{x:.4f}" for x in bbox), "time": f"2008-01-01,{end}",
        "filter": FILTER, "properties": "tags,metadata"})
    rows = []
    for f in d["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"] if f.get("geometry") else (None, None)
        tags = {k: v for k, v in p.items() if not k.startswith("@")}
        rows.append({"osm_id": p["@osmId"], "version": p.get("@version"), "changeset": p.get("@changesetId"),
                     "valid_from": p["@validFrom"], "valid_to": p["@validTo"], "lat": lat, "lon": lon,
                     "name": tags.get("name"), "amenity": tags.get("amenity"), "shop": tags.get("shop"),
                     "tags": json.dumps(tags)})
    return rows


def classify(r: pd.Series) -> tuple[str | None, str | None, str | None]:
    if r.amenity in CAT:
        return f"amenity={r.amenity}", CAT[r.amenity], None
    if r.shop in CAT:
        return f"shop={r.shop}", CAT[r.shop], None
    t = json.loads(r.tags)
    for pfx in LIFE_PREFIXES:
        for k in ("amenity", "shop"):
            v = t.get(f"{pfx}:{k}")
            if v in CAT:
                return f"{pfx}:{k}={v}", CAT[v], pfx
    return None, None, None


def _norm(n) -> str:
    return re.sub(r"[^a-z0-9]", "", str(n).lower()) if isinstance(n, str) else ""


def _seg_ids(g: pd.DataFrame) -> pd.Series:
    """New tenure when activity flips, or the name changes to something clearly different
    (ignores typo fixes / added suffixes and None -> name)."""
    seg, ids, prev_name, prev_active = 1, [], None, None
    for name, active in zip(g["name"], g["active"]):
        a, b = _norm(prev_name), _norm(name)
        if prev_active is not None and (active != prev_active or (
                a and b and a not in b and b not in a and SequenceMatcher(None, a, b).ratio() < 0.6)):
            seg += 1
        ids.append(seg)
        prev_active = active
        prev_name = name if name else prev_name
    return pd.Series(ids, index=g.index)


def segments(v: pd.DataFrame, end: str) -> pd.DataFrame:
    """Collapse versions into tenures: a new tenure starts when the name changes or the element
    goes from active to lifecycle-prefixed. A tenure is 'closed' if it ended before the data end."""
    v = v.sort_values(["osm_id", "valid_from"])
    v[["category_raw", "category", "life"]] = v.apply(lambda r: pd.Series(classify(r)), axis=1)
    v = v[v.category.notna()].copy()
    v["active"] = v.life.isna()
    v["seg"] = v.groupby("osm_id", group_keys=False)[["name", "active"]].apply(_seg_ids)
    end_ts = pd.Timestamp(end).tz_localize(None) if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end)
    g = v.groupby(["osm_id", "seg"], sort=False)
    out = g.agg(name=("name", "last"), category_raw=("category_raw", "last"), category=("category", "last"),
                active=("active", "last"), lat=("lat", "last"), lon=("lon", "last"),
                first_seen=("valid_from", "min"), last_seen=("valid_to", "max"),
                n_versions=("version", "count"), tags=("tags", "last")).reset_index()
    nseg = out.groupby("osm_id").seg.transform("max")
    out["still_present"] = pd.to_datetime(out.last_seen, utc=True) >= end_ts - pd.Timedelta(days=1)
    out["ended_by"] = None
    out.loc[~out.still_present & (out.seg < nseg), "ended_by"] = "renamed_or_lifecycle"
    out.loc[~out.still_present & (out.seg == nseg), "ended_by"] = "deleted_or_retagged"
    out.loc[~out.active, "ended_by"] = "lifecycle_tag"  # tenure itself is a disused:/was: record
    return out


def run() -> None:
    end = metadata_end()
    print(f"ohsome: history to {end}")
    xs = [XMIN + i * DX for i in range(int((XMAX - XMIN) / DX) + 1)]
    ys = [YMIN + j * DY for j in range(int((YMAX - YMIN) / DY) + 1)]
    tiles = [(x, y, min(x + DX, XMAX), min(y + DY, YMAX)) for x in xs for y in ys]
    print(f"  {len(tiles)} tiles")
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for i, r in enumerate(ex.map(lambda b: tile(b, end), tiles)):
            rows += r
            if i % 5 == 0:
                print(f"  tile {i}/{len(tiles)}: {len(rows):,} versions so far")
    v = pd.DataFrame(rows).drop_duplicates(["osm_id", "version", "valid_from"]).reset_index(drop=True)
    v.to_parquet(OUT / "osm_ohsome_versions.parquet", compression="zstd", index=False)
    print(f"  wrote osm_ohsome_versions.parquet: {len(v):,} versions, {v.osm_id.nunique():,} elements")
    seg = segments(v, end)
    seg["extra"] = [json.dumps({"seg": int(s), "active": bool(a), "still_present": bool(p), "ended_by": e,
                                "n_versions": int(n), "data_end": end,
                                "addr": " ".join(filter(None, (json.loads(t).get("addr:housenumber"),
                                                                json.loads(t).get("addr:street"))))})
                    for s, a, p, e, n, t in zip(seg.seg, seg.active, seg.still_present, seg.ended_by,
                                                seg.n_versions, seg.tags)]
    seg["address"] = [json.loads(e)["addr"] or None for e in seg.extra]
    tmp = OUT / "_ohsome_tmp.parquet"
    seg.drop(columns=["tags"]).to_parquet(tmp)
    con = connect()
    try:
        clip_and_write(con, f"""
            SELECT 'osm_history' AS source, osm_id || '#' || seg AS source_id, name, category_raw, category,
                   lat, lon, address, NULL::DATE AS date_created,
                   CASE WHEN NOT active THEN try_cast(first_seen AS TIMESTAMP)::DATE
                        WHEN NOT still_present THEN try_cast(last_seen AS TIMESTAMP)::DATE END AS date_closed,
                   try_cast(first_seen AS TIMESTAMP)::DATE AS first_seen,
                   try_cast(last_seen AS TIMESTAMP)::DATE AS last_seen, extra
            FROM '{tmp}' WHERE lat IS NOT NULL""", "osm_ohsome.parquet")
    finally:
        tmp.unlink()
