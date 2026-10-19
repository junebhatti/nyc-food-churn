"""Coverage gap measurement: combined inventory (DOHMH CAMIS + SLA licences + new coverage sources)
against Overture's current open places, by fine category and NTA, plus per-year active counts.

    .venv/bin/python pipeline/fetch_coverage.py gaps

Outputs (data/raw/coverage/):
  gap_category.csv    Overture 2026-09 places by fine category: share matched by DOHMH, +SLA, +new sources
  gap_nta.csv         same by NTA (2020), with before/after match rates
  inventory_year.csv  active places per source x category x borough x year (2005-2026)
  dohmh_nta_dips.csv  NTA-years whose DOHMH active-CAMIS count dips >= 20% below both neighbouring years
Match rule (as crosscheck_recent.py): within 100 m and normalized-name Jaro-Winkler >= 0.85.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from coverage_common import OUT, ROOT, geocode, log

RAW = ROOT / "data" / "raw"
OV = RAW / "poi" / "overture_2026-09-23.0.parquet"
NOW = "2026-04-01"  # "open now" = seen in a source on/after this date

OV_CAT = [
    ("bodega_deli", r"^(delicatessen|convenience_store|grocery_store)$"),
    ("bakery", r"^(bakery|bagel_shop|donut_shop|patisserie_cake_shop|cupcake_shop)$"),
    ("coffee_tea", r"^(coffee_shop|cafe|bubble_tea_shop|tea_room|coffee_roastery)$"),
    ("juice", r"^smoothie_juice_bar$"),
    ("dessert", r"^(ice_cream_shop|dessert_shop|candy_store|frozen_yoghurt_shop|chocolatier|gelato)$"),
    ("bar", r"^(bar|cocktail_bar|lounge|wine_bar|sports_bar|pub|beer_bar|night_club|brewery|dive_bar|"
            r"hookah_bar|beer_garden|irish_pub|karaoke|tiki_bar|whiskey_bar|gay_bar|speakeasy)$"),
    ("food_hall_market", r"^(food_court|farmers_market|public_market|food_hall|market)$"),
    ("food_truck", r"^food_truck_stand$"),
    ("restaurant", r"restaurant|^(diner|sandwich_shop|steakhouse|bistro|buffet|gastropub|food_stand|"
                   r"noodles|salad_bar|hot_dog_stand|deli_sandwich|poke)$"),
]


def dohmh_cat(c):
    c = str(c or "").lower()
    for k, pat in [("coffee_tea", r"coffee|tea"), ("bakery", r"bakery|bagel|donut|pretzel"),
                   ("juice", r"juice|smoothie"), ("dessert", r"ice cream|frozen|dessert|gelato"),
                   ("bodega_deli", r"delicatessen|sandwiches$|bottled")]:
        if pd.Series([c]).str.contains(pat).iat[0]:
            return k
    return "restaurant"


def dohmh_places(c):
    """One row per CAMIS: name, category, coords (source or PAD), first/last year."""
    u = c.sql(f"""
      select camis, any_value(dba order by inspection_date desc) dba,
             any_value(building order by inspection_date desc) building,
             any_value(street order by inspection_date desc) street,
             any_value(zipcode order by inspection_date desc) zipcode,
             any_value(boro order by inspection_date desc) boro_raw,
             mode(cuisine) filter (where not regexp_matches(coalesce(cuisine,''), '^[0-9.]+$')) cuisine,
             max(try_cast(latitude as double)) filter (where try_cast(latitude as double) > 40) lat,
             min(try_cast(longitude as double)) filter (where try_cast(longitude as double) < -73) lon,
             any_value(bbl) filter (where bbl is not null and length(bbl) = 10) bbl,
             min(inspection_date) filter (where inspection_date > date '1901-01-01') first_insp,
             max(inspection_date) filter (where inspection_date > date '1901-01-01') last_insp,
             max(last_snapshot) last_snapshot
      from '{RAW}/dohmh/union_inspections.parquet' group by camis""").df()
    u["category"] = u["cuisine"].map(dohmh_cat)
    need = u["lat"].isna()
    g = pd.DataFrame({"house": u.loc[need, "building"], "street": u.loc[need, "street"],
                      "zip": u.loc[need, "zipcode"], "boro": None, "lat": np.nan, "lon": np.nan})
    g = geocode(g)
    u.loc[need, "lat"], u.loc[need, "lon"] = g["lat"], g["lon"]
    u.loc[need & u["bbl"].isna(), "bbl"] = g["bbl"]
    log(f"dohmh places {len(u):,}; coords {u['lat'].notna().mean():.1%}")
    return u


def build_points(c, d):
    """Union of place points with (src, name, lat, lon, category, start, end)."""
    pts = [pd.DataFrame({"src": "dohmh", "name": d["dba"], "lat": d["lat"], "lon": d["lon"],
                         "category": d["category"], "start": d["first_insp"],
                         "end": d["last_snapshot"]})]
    sla = c.sql(f"""select coalesce(dba, legal_name) as name, legal_name, lat, lon, category, on_premises,
                    start_date, end_date from '{RAW}/gov/sla_licenses_nyc.parquet' where lat is not null""").df()
    sla["category"] = sla["category"].map({"restaurant": "restaurant", "bar_tavern": "bar", "club": "bar",
                                           "additional_bar": "bar", "grocery_drug": "bodega_deli",
                                           "catering": "restaurant", "hotel": "bar"}).fillna("other")
    for nm in ("name", "legal_name"):
        pts.append(pd.DataFrame({"src": "sla", "alias": nm != "name", "name": sla[nm], "lat": sla["lat"], "lon": sla["lon"],
                                 "category": sla["category"], "start": sla["start_date"],
                                 "end": sla["end_date"].fillna(pd.Timestamp("2026-10-18"))}))
    for f, src in [("snap_retailers_nyc", "snap"), ("dcwp_tobacco_nyc", "dcwp_tob"),
                   ("agm_retail_food_stores_nyc", "agm_rfs"), ("agm_inspections_nyc", "agm_insp"),
                   ("cb3_sla_items", "cb3")]:
        p = OUT / f"{f}.parquet"
        if not p.exists():
            log(f"  (missing {p.name}, skipped)")
            continue
        x = pd.read_parquet(p)
        end = x["end_date"].where(x["end_date"].notna(), x["last_seen"])
        if src == "snap":
            end = x["end_date"].where(x["end_date"].notna(), pd.Timestamp("2026-10-18").date())
        if src == "dcwp_tob":
            st = x["extra"].str.extract(r'"status": "([^"]*)"')[0].str.lower()
            end = x["end_date"].where(st.isin(["active", "issued"]) | x["source"].eq("dcwp_cig_legacy"),
                                      pd.to_datetime(x["end_date"]).dt.date.clip(upper=pd.Timestamp("2026-01-01").date()))
        start = x["start_date"].where(x["start_date"].notna(), x["first_seen"])
        for nm in ("name", "legal_name"):
            pts.append(pd.DataFrame({"src": src, "alias": nm != "name", "name": x[nm], "lat": x["lat"], "lon": x["lon"],
                                     "category": x["category"], "start": start, "end": end}))
    p = pd.concat(pts, ignore_index=True)
    p = p[p["lat"].notna() & (p["name"].notna() | ~p["alias"].fillna(False).astype(bool))]
    p["start"] = pd.to_datetime(p["start"], errors="coerce")
    p["end"] = pd.to_datetime(p["end"], errors="coerce")
    return p


def match_overture(c, pts):
    ov = c.sql(f"""select source_id, name, lat, lon, category_raw,
                   try_cast(json_extract_string(extra, '$.confidence') as double) conf,
                   json_extract_string(extra, '$.operating_status') status
                   from '{OV}'""").df()
    ov["fine"] = None
    for k, pat in OV_CAT:
        ov.loc[ov["fine"].isna() & ov["category_raw"].fillna("").str.contains(pat), "fine"] = k
    ov = ov[ov["fine"].notna() & (ov["conf"].fillna(0) >= 0.5) & ov["status"].fillna("open").ne("permanently_closed")]
    pl = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet", columns=["lat", "lon", "nta2020", "ntaname"]).dropna()
    # NTA for each Overture point = nearest lot centroid (grid lookup)
    pl["k"] = list(zip((pl["lat"] * 500).round().astype(int), (pl["lon"] * 500).round().astype(int)))
    names = pl.drop_duplicates("nta2020").set_index("nta2020")["ntaname"]
    nta = pl.groupby("k")["nta2020"].agg(lambda s: s.mode().iat[0]).to_frame()
    nta["ntaname"] = nta["nta2020"].map(names)
    ov["k"] = list(zip((ov["lat"] * 500).round().astype(int), (ov["lon"] * 500).round().astype(int)))
    ov = ov.join(nta, on="k").drop(columns="k")
    now = pts[pts["end"] >= pd.Timestamp(NOW)]
    c.register("ov", ov)
    c.register("now", now)
    c.execute(r"""create or replace macro norm(s) as trim(regexp_replace(
      regexp_replace(upper(coalesce(s, '')), '[^A-Z0-9 ]', '', 'g'),
      '\b(THE|INC|LLC|CORP|CO|RESTAURANT|RESTAURANTS|CAFE|BAR|AND|NYC|NY|DELI|GROCERY|CORPORATION)\b', '', 'g'))""")
    m = c.sql("""
      with o as (select source_id, norm(name) n, lat, lon from ov),
           p as (select src, norm(name) n, lat, lon from now where length(norm(name)) > 1)
      select o.source_id, p.src from o join p
        on p.lat between o.lat - 0.0009 and o.lat + 0.0009
       and p.lon between o.lon - 0.0012 and o.lon + 0.0012
      where jaro_winkler_similarity(o.n, p.n) >= 0.85
        and 111320 * sqrt(power(o.lat - p.lat, 2) + power((o.lon - p.lon) * 0.758, 2)) <= 100
      group by all""").df()
    hit = m.groupby("source_id")["src"].agg(set)
    ov["srcs"] = ov["source_id"].map(hit)
    has = lambda s: ov["srcs"].map(lambda x: isinstance(x, set) and bool(x & s))
    base = {"dohmh", "sla"}
    new = {"snap", "dcwp_tob", "agm_rfs", "agm_insp", "cb3"}
    ov["m_dohmh"] = has({"dohmh"})
    ov["m_before"] = has(base)
    ov["m_after"] = has(base | new)
    ov["m_new_only"] = ov["m_after"] & ~ov["m_before"]
    return ov


def year_inventory(pts, d):
    rows = []
    pl = pts[pts["start"].notna()].copy()
    pl["end"] = pl["end"].fillna(pd.Timestamp("2026-10-18"))
    pl = pl[~pl["alias"].fillna(False).astype(bool)]
    for y in range(2005, 2027):
        a, b = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
        act = pl[(pl["start"] <= b) & (pl["end"] >= a)]
        rows.append(act.groupby(["src", "category"]).size().rename("n_active").reset_index().assign(year=y))
    inv = pd.concat(rows, ignore_index=True)
    # DOHMH NTA x year dips
    d = d.copy()
    pl2 = pd.read_parquet(RAW / "gov" / "pluto_slim.parquet", columns=["bbl", "nta2020", "ntaname"])
    d = d.merge(pl2, on="bbl", how="left")
    d["y0"] = pd.to_datetime(d["first_insp"]).dt.year
    d["y1"] = pd.to_datetime(d["last_snapshot"]).dt.year
    recs = []
    for y in range(2011, 2027):
        a = d[(d["y0"] <= y) & (d["y1"] >= y)]
        recs.append(a.groupby(["nta2020", "ntaname"]).size().rename("n").reset_index().assign(year=y))
    ny = pd.concat(recs).pivot_table(index=["nta2020", "ntaname"], columns="year", values="n", fill_value=0)
    dips = []
    for y in range(2012, 2026):
        prev, cur, nxt = ny[y - 1], ny[y], ny[y + 1]
        flag = (cur < 0.8 * prev) & (cur < 0.8 * nxt) & (prev >= 20)
        for (code, name), v in ny[flag].iterrows():
            dips.append({"nta2020": code, "ntaname": name, "year": y, "n": int(v[y]),
                         "prev": int(v[y - 1]), "next": int(v[y + 1])})
    return inv, pd.DataFrame(dips), ny


def novelty(c, d):
    """Share of each new source's records at BBLs never seen in DOHMH or SLA (new locations), and
    whether a DOHMH/SLA record at that BBL overlaps it in time."""
    from coverage_sources import split_house
    sla = c.sql(f"select address, zip, start_date, end_date, on_premises, category from "
                f"'{RAW}/gov/sla_licenses_nyc.parquet'").df()
    hs = sla["address"].map(split_house)
    g = geocode(pd.DataFrame({"house": [h for h, _ in hs], "street": [x for _, x in hs],
                              "zip": sla["zip"].astype(str).str[:5], "boro": None, "lat": np.nan, "lon": np.nan}))
    sla["bbl"] = g["bbl"].values
    log(f"sla geocoded to BBL: {sla['bbl'].notna().mean():.1%}")
    known = pd.concat([pd.DataFrame({"bbl": d["bbl"], "s": pd.to_datetime(d["first_insp"]),
                                     "e": pd.to_datetime(d["last_snapshot"]), "k": "dohmh"}),
                       pd.DataFrame({"bbl": sla["bbl"], "s": pd.to_datetime(sla["start_date"]),
                                     "e": pd.to_datetime(sla["end_date"]).fillna(pd.Timestamp("2026-10-18")),
                                     "k": "sla"})]).dropna(subset=["bbl"])
    kb = set(known["bbl"])
    kd = set(known.loc[known["k"].eq("dohmh"), "bbl"])
    rows = []
    for f in ("snap_retailers_nyc", "dcwp_tobacco_nyc", "agm_retail_food_stores_nyc", "agm_inspections_nyc",
              "cb3_sla_items"):
        p = OUT / f"{f}.parquet"
        if not p.exists():
            continue
        x = pd.read_parquet(p)
        x = x[x["bbl"].notna()]
        st = pd.to_datetime(x["start_date"].where(x["start_date"].notna(), x["first_seen"]))
        if f == "cb3_sla_items":
            x = x[(st >= "2005-01-01") & (st < "2015-01-01")]
            st = st.loc[x.index]
        for cat, gx in x.groupby("category"):
            rows.append({"file": f, "category": cat, "n_geocoded": len(gx),
                         "bbl_in_dohmh_or_sla": round(gx["bbl"].isin(kb).mean(), 3),
                         "bbl_in_dohmh": round(gx["bbl"].isin(kd).mean(), 3),
                         "new_bbl": int((~gx["bbl"].isin(kb)).sum())})
    if (OUT / "cb3_sla_items.parquet").exists():  # pre-2015 bar evidence the SLA file lacks
        cb = pd.read_parquet(OUT / "cb3_sla_items.parquet")
        cb["m"] = pd.to_datetime(cb["start_date"])
        cb = cb[cb["bbl"].notna() & (cb["m"] < "2015-01-01") & (cb["m"] >= "2005-01-01")]
        early = sla[sla["bbl"].notna() & (pd.to_datetime(sla["start_date"]) < pd.Timestamp("2015-01-01"))
                    & sla["on_premises"]]
        rows.append({"file": "cb3_sla_items", "category": "2005-14 items: BBL has no SLA on-prem start <2015",
                     "n_geocoded": len(cb), "bbl_in_dohmh_or_sla": round(cb["bbl"].isin(set(early["bbl"])).mean(), 3),
                     "bbl_in_dohmh": round(cb["bbl"].isin(kd).mean(), 3),
                     "new_bbl": int((~cb["bbl"].isin(set(early["bbl"]))).sum())})
    nv = pd.DataFrame(rows)
    nv.to_csv(OUT / "novelty.csv", index=False)
    log("novelty vs DOHMH+SLA (BBL level):\n" + nv.to_string(index=False))


def run():
    c = duckdb.connect()
    d = dohmh_places(c)
    pts = build_points(c, d)
    log(f"points {len(pts):,}")
    ov = match_overture(c, pts)
    agg = lambda g: pd.Series({"n_overture": len(g), "dohmh": g["m_dohmh"].mean(), "before": g["m_before"].mean(),
                               "after": g["m_after"].mean(), "new_only": g["m_new_only"].sum()})
    cat = ov.groupby("fine").apply(agg).sort_values("before")
    cat.loc["ALL"] = agg(ov)
    cat.round(3).to_csv(OUT / "gap_category.csv")
    log("by category:\n" + cat.round(3).to_string())
    nta = ov.groupby(["nta2020", "ntaname"]).apply(agg)
    nta = nta[nta["n_overture"] >= 30].sort_values("before")
    nta.round(3).to_csv(OUT / "gap_nta.csv")
    log("worst NTAs (before):\n" + nta.head(12).round(3).to_string())
    inv, dips, ny = year_inventory(pts, d)
    inv.to_csv(OUT / "inventory_year.csv", index=False)
    dips.to_csv(OUT / "dohmh_nta_dips.csv", index=False)
    piv = inv.pivot_table(index="year", columns="src", values="n_active", aggfunc="sum").fillna(0).astype(int)
    log("active by source/year:\n" + piv.to_string())
    log(f"DOHMH NTA-year dips: {len(dips)}; by year {dips.groupby('year').size().to_dict() if len(dips) else {}}")
    bod = inv[inv["category"].eq("bodega_deli")].pivot_table(index="year", columns="src", values="n_active",
                                                              aggfunc="sum").fillna(0).astype(int)
    log("bodega/deli active by source/year:\n" + bod.to_string())
    novelty(c, d)
