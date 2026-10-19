"""Export the address pages' data and the search index (web/public/data/), after export_site.py.

  places/NNN.json  per-building detail, sharded by FNV-1a of the place id (export_site.shard_of):
                   address, neighbourhood, stats, every business with health grades, acclaim,
                   price tier, liquor licence, and the nearest other addresses
  search.json      [id, address, neighbourhood, recent business names] for the search box
Health grades are public DOHMH data. Acclaim is a fact (on a list, n stars) with a link to the review
where we have one. Google/Yelp ratings are deliberately not exported (their terms, and the
research-only licence of the Google Local data); the site links out to them instead.
Run: .venv/bin/python pipeline/export_places.py
"""
from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
import pandas as pd

from build_lifespans import RAW
from export_site import (FAMILY_LABEL, LIVE, WEB, address_of, clean, load, place_id, shard_of, write)

N_SHARDS = 128
NEARBY = 5
GRADES = {"A", "B", "C"}
CAT_LABEL = {"restaurant": "Restaurant", "bar": "Bar", "cafe": "Café", "bakery": "Bakery", "bodega": "Bodega"}


def inspections() -> pd.DataFrame:
    """Per permit: number of inspections, latest letter grade, last five scores."""
    u = pd.read_parquet(RAW / "dohmh" / "union_inspections.parquet", columns=["camis", "inspection_date", "grade", "score"])
    u["inspection_date"] = pd.to_datetime(u["inspection_date"])
    u = u[u["inspection_date"] >= pd.Timestamp("2005-01-01")].copy()
    u["camis"] = u["camis"].astype(str)
    u["score"] = pd.to_numeric(u["score"], errors="coerce")
    per = u.groupby(["camis", "inspection_date"]).agg(score=("score", "max"), grade=("grade", "first")).reset_index()
    per = per.sort_values("inspection_date")
    out = {}
    for camis, d in per.groupby("camis"):
        g = d[d["grade"].isin(GRADES)]
        out[camis] = {"n": len(d), "last": str(d["inspection_date"].iloc[-1].date()),
                      "grade": g["grade"].iloc[-1] if len(g) else None,
                      "gradeDate": str(g["inspection_date"].iloc[-1].date()) if len(g) else None,
                      "scores": [[str(r.inspection_date.date()), int(r.score)] for r in d.dropna(subset=["score"]).tail(5).itertuples()]}
    return out


def acclaim() -> dict:
    """camis -> list of {kind, label, url?}."""
    r = RAW / "ratings"
    out: dict[str, list] = defaultdict(list)
    m = pd.read_parquet(r / "michelin_nyc.parquet").dropna(subset=["camis"])
    for camis, d in m.groupby(m["camis"].astype(str)):
        stars = d[d["stars"].fillna(0) > 0]
        if len(stars):
            yrs = sorted(stars["year"].astype(int))
            out[camis].append({"kind": "michelin", "label": f"Michelin {int(stars['stars'].max())}★ ({yrs[0]}–{yrs[-1]})" if yrs[0] != yrs[-1] else f"Michelin {int(stars['stars'].max())}★ ({yrs[0]})"})
    e = pd.read_parquet(r / "eater_lists.parquet").dropna(subset=["camis"])
    names = {"eater_38": "Eater 38", "eater_heatmap_nyc": "Eater Heatmap", "eater_heatmap_brooklyn": "Eater Heatmap (Brooklyn)",
             "eater_heatmap_queens": "Eater Heatmap (Queens)"}
    for (camis, lst), d in e.groupby([e["camis"].astype(str), "list"]):
        q = sorted(d["quarter"])
        out[camis].append({"kind": "eater", "label": f"{names.get(lst, lst)}, {q[0]}" + (f" – {q[-1]}" if q[-1] != q[0] else ""),
                           "url": d.sort_values("quarter")["wayback_url"].iloc[-1]})
    n = pd.read_parquet(r / "nyt_reviews.parquet").dropna(subset=["camis"])
    for _, x in n.iterrows():
        stars = f"{int(x['stars'])}★" if pd.notna(x["stars"]) else str(x.get("rating_raw") or "")
        out[str(x["camis"])].append({"kind": "nyt", "label": f"NYT review {stars} ({int(x['year'])})".replace("  ", " "),
                                     "url": x["review_url"] if isinstance(x["review_url"], str) else None})
    a = pd.read_parquet(r / "awards_nyc.parquet").dropna(subset=["camis"])
    for _, x in a.iterrows():
        out[str(x["camis"])].append({"kind": "award", "label": f"{x['list']}: {x['award']} ({int(x['year'])})".replace("_", " ")})
    return out


def nearby(centroids: pd.DataFrame) -> dict:
    """NEARBY closest other buildings per building (grid search, ~1 km)."""
    c = centroids.reset_index(drop=True)
    cell = (np.floor(c["lat"] * 200).astype(int).astype(str) + "," + np.floor(c["lon"] * 150).astype(int).astype(str))
    grid = defaultdict(list)
    for i, k in enumerate(cell):
        grid[k].append(i)
    lat, lon = c["lat"].values, c["lon"].values
    out = {}
    for i in range(len(c)):
        a, b = int(np.floor(lat[i] * 200)), int(np.floor(lon[i] * 150))
        cand = [j for da in (-1, 0, 1) for db in (-1, 0, 1) for j in grid.get(f"{a + da},{b + db}", []) if j != i]
        if not cand:
            continue
        cand = np.array(cand)
        d = 111320 * np.hypot(lat[cand] - lat[i], (lon[cand] - lon[i]) * np.cos(np.radians(lat[i])))
        best = cand[np.argsort(d)[:NEARBY]]
        out[c.at[i, "id"]] = [[c.at[j, "id"], c.at[j, "address"], int(c.at[j, "n"]), int(round(float(dd)))]
                              for j, dd in zip(best, np.sort(d)[:NEARBY])]
    return out


def main() -> None:
    b = load()
    hoods = {h["id"]: h for h in json.loads((WEB / "neighborhoods.json").read_text())}
    betas = pd.read_csv(RAW.parent / "processed" / "analysis" / "beta_by_group.csv")
    betas = betas[betas["group"] == "nta2020"].set_index("level")["beta"].to_dict()
    insp, acc = inspections(), acclaim()
    print(f"inspections for {len(insp):,} permits; acclaim for {len(acc):,}")

    b = b.sort_values("open_date")
    groups = b.groupby("building_key", sort=False)
    cent = groups.agg(lat=("lat", "median"), lon=("lon", "median"), n=("business_id", "size")).reset_index()
    cent["id"] = cent["building_key"].map(place_id)
    cent["address"] = [address_of(groups.get_group(k).iloc[-1]) for k in cent["building_key"]]
    near = nearby(cent[["id", "address", "lat", "lon", "n"]])

    shards: dict[int, dict] = defaultdict(dict)
    search = []
    for key, d in groups:
        pid = place_id(key)
        last = d.iloc[-1]
        code = last["nta2020"] if isinstance(last["nta2020"], str) else None
        hood = hoods.get(code, {})
        closed = d.loc[d["event"], "years"]
        biz = []
        for _, t in d.iloc[::-1].iterrows():
            camis = [str(x) for x in (t["camis_list"] if isinstance(t["camis_list"], (list, np.ndarray)) else [])]
            ins = [insp[c] for c in camis if c in insp]
            latest = max(ins, key=lambda x: x["last"]) if ins else None
            biz.append({
                "name": str(t["dba"]).strip(), "category": CAT_LABEL.get(t["site_category"], t["site_category"]),
                "cuisine": FAMILY_LABEL.get(t["family"], t["label"]), "open": clean(t["o"]),
                "close": clean(t["c"]) if t["event"] else None, "isOpen": not bool(t["closed"]),
                "life": round(float(t["years"]), 1), "price": clean(t.get("price_tier")),
                "chain": bool(t.get("is_chain_loose")) if pd.notna(t.get("is_chain_loose")) else False,
                "liquor": bool(t.get("has_bar_licence")), "source": t["source"],
                "inspections": {"n": sum(x["n"] for x in ins), **{k: latest[k] for k in ("last", "grade", "gradeDate", "scores")}} if latest else None,
                "acclaim": [a for c in camis for a in acc.get(c, [])],
            })
        detail = {"id": pid, "address": address_of(last), "zip": clean(str(last["zip"])[:5]) if pd.notna(last["zip"]) else None,
                  "boro": str(last["boro"]).title() if isinstance(last["boro"], str) else None,
                  "lat": round(float(d["lat"].median()), 5), "lon": round(float(d["lon"].median()), 5),
                  "nta": code, "ntaName": hood.get("name"), "tenants": len(d),
                  "medianLife": clean(round(float(closed.median()), 1)) if len(closed) else None,
                  "hood": {"closure3y": hood.get("closure3y"), "rent": hood.get("rent"), "medianLife": hood.get("medianLife"),
                           "beta": clean(betas.get(code)) if code else None},
                  "businesses": biz, "nearby": near.get(pid, [])}
        shards[shard_of(pid, N_SHARDS)][pid] = detail
        names = list(dict.fromkeys(x["name"] for x in biz))[:8]
        search.append([pid, detail["address"], (hood.get("name") or "").split("-")[0], " | ".join(names)])

    (WEB / "places").mkdir(parents=True, exist_ok=True)
    total = 0
    for i in range(N_SHARDS):
        s = json.dumps(shards.get(i, {}), separators=(",", ":"), allow_nan=False)
        (WEB / "places" / f"{i:03d}.json").write_text(s)
        total += len(s)
    print(f"  places/: {len(search):,} addresses in {N_SHARDS} shards, {total / 1e6:.1f} MB")
    write("search.json", search)


if __name__ == "__main__":
    main()
