"""Coverage sources for small food retail that DOHMH does not inspect (bodegas, delis, bakeries,
coffee/tea retail, groceries), all open data:

  snap      USDA FNS Historical SNAP Retailer Locator Data 2005-2025 (authorization + end dates)
  dcwp_tob  NYC DCWP cigarette / tobacco / e-cig retail dealer licenses (m4ph-grrm legacy to ~2014,
            w7w3-xahh current), the classic bodega licence, 1980s-now with creation/expiry dates
  agm_rfs   NYS Ag & Markets Retail Food Stores licences (9a8c-vfzj): live pull + every Wayback
            rows.csv copy 2016-2026 -> first/last seen per licence
  agm_insp  NYS Ag & Markets Food Safety Inspections (d6dy-3h7r): live + Wayback copies 2020-2026
"""
from __future__ import annotations

import io
import json
import re
import zipfile

import pandas as pd

from coverage_common import (BORO_NAMES, CACHE, NYC_COUNTIES, Wayback, geocode, log, save,
                             socrata_all)

NYC_ZIP3 = ("100", "101", "102", "103", "104", "110", "111", "112", "113", "114", "116")


def split_house(addr: str):
    m = re.match(r"\s*(\d[\d\-]*[A-Z]?(?:\s*1/2)?)\s+(.*)", str(addr or "").upper())
    return (m.group(1), m.group(2)) if m else (None, str(addr or "").upper())


# ---------------------------------------------------------------- SNAP
SNAP_URL = "https://www.fns.usda.gov/sites/default/files/resource-files/snap-retailer-locator-data2005-2025.zip"
SNAP_CAT = {"Convenience Store": "bodega_deli", "Small Grocery Store": "bodega_deli",
            "Combination Grocery/Other": "bodega_deli", "Medium Grocery Store": "grocery",
            "Large Grocery Store": "grocery", "Supermarket": "grocery", "Super Store": "grocery",
            "Bakery Specialty": "bakery", "Seafood Specialty": "specialty_food",
            "Meat/Poultry Specialty": "specialty_food", "Fruits/Veg Specialty": "specialty_food",
            "Farmers' Market": "market", "Food Buying Co-op": "grocery"}


def snap():
    p = CACHE / "snap" / "snap-retailer-locator-data2005-2025.zip"
    if not p.exists():
        raise FileNotFoundError(f"download {SNAP_URL} to {p} first")
    z = zipfile.ZipFile(p)
    df = pd.read_csv(z.open(z.namelist()[0]), dtype=str, encoding="utf-8-sig")
    df = df[df["State"].eq("NY") & df["County"].str.strip().str.upper().isin(NYC_COUNTIES)].copy()
    out = pd.DataFrame({
        "source": "usda_snap", "source_id": df["Record ID"].str.strip(),
        "name": df["Store Name"].str.strip(), "house": df["Street Number"].str.strip(),
        "street": df["Street Name"].str.strip(), "zip": df["Zip Code"].str.strip().str[:5],
        "boro": df["County"].str.strip().str.upper().map(NYC_COUNTIES),
        "category_raw": df["Store Type"], "start_date": pd.to_datetime(df["Authorization Date"], errors="coerce"),
        "end_date": pd.to_datetime(df["End Date"].str.strip(), errors="coerce"),
        "lat": pd.to_numeric(df["Latitude"], errors="coerce"), "lon": pd.to_numeric(df["Longitude"], errors="coerce"),
    })
    out["address"] = (out["house"].fillna("") + " " + out["street"].fillna("")).str.strip()
    out["category"] = out["category_raw"].map(SNAP_CAT).fillna("other_food")
    # bakeries/coffee often typed "Convenience Store" -> name-based refinement
    nm = out["name"].str.upper()
    out.loc[nm.str.contains(r"\bBAKERY|PANADERIA|PASTRY|PATISSERIE|BAKE SHOP", na=False), "category"] = "bakery"
    out.loc[nm.str.contains(r"\bDELI\b|BODEGA|MINI ?MART|GROCERY|CANDY STORE", na=False)
            & out["category"].eq("grocery") & out["category_raw"].str.contains("Medium"), "category"] = "bodega_deli"
    # 1930 auth dates are a placeholder; keep but flag
    out["extra"] = [json.dumps({"auth_placeholder": bool(d.year == 1930)}) if pd.notna(d) else "{}"
                    for d in out["start_date"]]
    out = geocode(out)
    return save(out, "snap_retailers_nyc", source="USDA FNS", url=SNAP_URL,
                note="SNAP-authorized retailers in the 5 counties, 2005-2025 file (auths back to 1970s; "
                     "1930 = placeholder). end_date null = still authorized at file date (2025-12-31).")


# ---------------------------------------------------------------- DCWP tobacco
def dcwp_tob():
    h = socrata_all("data.cityofnewyork.us", "m4ph-grrm",
                    where="business_code_description='CIGARETTE RETAIL DEALER'")
    c = socrata_all("data.cityofnewyork.us", "w7w3-xahh",
                    where="business_category in ('Tobacco Retail Dealer','Electronic Cigarette Dealer')")
    h.to_parquet(CACHE / "dcwp_m4ph_cig.parquet")
    c.to_parquet(CACHE / "dcwp_w7w3_tob.parquet")
    log(f"dcwp legacy {len(h):,}, current {len(c):,}")
    hb = h["borough"].fillna("").str.upper()
    a = pd.DataFrame({
        "source": "dcwp_cig_legacy", "source_id": h["dca_license_number"],
        "name": h.get("business_name"),
        "legal_name": h.get("business_name"),
        "house": h.get("address_building"), "street": h.get("address_street_name"),
        "zip": h.get("address_zip", pd.Series(index=h.index, dtype=str)).astype(str).str[:5],
        "boro": hb.map(BORO_NAMES), "category_raw": h["business_code_description"],
        "start_date": pd.to_datetime(h.get("license_creation_date"), errors="coerce"),
        "end_date": pd.to_datetime(h.get("license_expiration_date"), errors="coerce"),
        "lat": pd.to_numeric(h.get("latitude"), errors="coerce"), "lon": pd.to_numeric(h.get("longitude"), errors="coerce"),
        "extra": [json.dumps({"status": s}) for s in h.get("license_status", pd.Series(index=h.index))],
    })
    cb = c.get("address_borough", pd.Series(index=c.index, dtype=str)).fillna("").str.upper()
    b = pd.DataFrame({
        "source": "dcwp_tobacco_current", "source_id": c["license_nbr"],
        "name": c.get("dba_trade_name", c["business_name"]).fillna(c["business_name"]), "legal_name": c.get("business_name"),
        "house": c.get("address_building"), "street": c.get("address_street_name"),
        "zip": c.get("address_zip", pd.Series(index=c.index, dtype=str)).astype(str).str[:5],
        "boro": cb.map(BORO_NAMES), "category_raw": c["business_category"],
        "start_date": pd.to_datetime(c.get("license_creation_date"), errors="coerce"),
        "end_date": pd.to_datetime(c.get("lic_expir_dd"), errors="coerce"),
        "lat": pd.to_numeric(c.get("latitude"), errors="coerce"), "lon": pd.to_numeric(c.get("longitude"), errors="coerce"),
        "extra": [json.dumps({"status": s}) for s in c.get("license_status", pd.Series(index=c.index))],
    })
    out = pd.concat([a, b], ignore_index=True)
    out = out[out["boro"].notna() | out["zip"].str[:3].isin(NYC_ZIP3)]
    out.loc[out["start_date"].dt.year < 1950, "start_date"] = pd.NaT  # 1900 placeholders
    out["address"] = (out["house"].fillna("") + " " + out["street"].fillna("")).str.strip()
    out["category"] = "bodega_deli"
    nm = out["name"].fillna("").str.upper()
    out.loc[~nm.str.contains(r"DELI|GROCER|BODEGA|MARKET|MART|FOOD|CANDY|NEWS|CONVENIEN|MINI|STORE|"
                             r"BAKERY|GOURMET|SUPERMARKET|FRUIT|MEAT", na=False), "category"] = "tobacco_retail_other"
    out.loc[nm.str.contains(r"SMOKE|VAPE|HOOKAH|CIGAR|TOBACCO|GAS|FUEL|PHARMA|DRUG|CVS|DUANE|RITE AID|"
                            r"WALGREEN|7-ELEVEN|SUNOCO|MOBIL|SHELL|BP\b|EXXON|CITGO|LUKOIL|HESS", na=False),
            "category"] = "tobacco_retail_other"
    out["src_bbl"] = pd.concat([h.get("bbl"), c.get("bbl")], ignore_index=True).reindex(out.index)
    out = geocode(out)
    miss = out["bbl"].isna() & out["src_bbl"].notna()
    out.loc[miss, "bbl"] = out.loc[miss, "src_bbl"]
    out = out.drop(columns="src_bbl")
    return save(out, "dcwp_tobacco_nyc", source="NYC DCWP (data.cityofnewyork.us)",
                url="m4ph-grrm + w7w3-xahh",
                note="Cigarette/tobacco/e-cig retail dealer licences: the near-universal bodega/deli licence. "
                     "category bodega_deli = food-ish name; tobacco_retail_other = smoke shops, gas, pharmacies, "
                     "unknown names. Legacy file ends ~2014, current starts at its own creation dates.")


# ---------------------------------------------------------------- Ag & Markets Retail Food Stores
RFS_ESTAB = {"A": "store", "B": "bakery", "C": "food_manufacturer", "D": "food_warehouse",
             "E": "beverage_plant", "H": "salvage", "K": "wholesale_produce"}


def _norm_cols(df):
    df.columns = [re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_") for c in df.columns]
    ren = {"license": "license_number", "dba": "dba_name", "street_name": "street_name",
           "zip": "zip_code", "estab_type": "estab_type", "establishment_types": "establishment_type",
           "operation": "operation_type", "entity": "entity_name"}
    return df.rename(columns={k: v for k, v in ren.items() if k in df.columns and v not in df.columns})


def _wayback_copies(dsid, name):
    cdx = Wayback.cdx(f"data.ny.gov/api/views/{dsid}/rows.csv*", filter="statuscode:200")
    if cdx.empty:
        raise RuntimeError(f"no CDX rows for {dsid}")
    cdx["length"] = pd.to_numeric(cdx["length"], errors="coerce")
    cdx["day"] = cdx["timestamp"].str[:8]
    cdx = cdx[~cdx["original"].str.contains("delimiter|format=true", regex=True)]
    cdx = cdx.sort_values("length", ascending=False).drop_duplicates("day")
    d = CACHE / f"wayback_{name}"
    d.mkdir(exist_ok=True)
    out = []
    for ts, orig in sorted(zip(cdx["timestamp"], cdx["original"])):
        p = d / f"{ts}.csv"
        if not p.exists():
            log(f"  fetch {name} {ts}")
            try:
                p.write_bytes(Wayback.raw(ts, orig))
            except RuntimeError as e:  # one bad capture should not sink the other copies
                log(f"  !! skipped capture {ts}: {e}")
                continue
        try:
            df = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
        except Exception as e:  # truncated/HTML playback: report and skip that copy
            log(f"  !! unreadable copy {p.name}: {e!r}")
            continue
        out.append((ts[:8], _norm_cols(df)))
    return out


def agm_rfs():
    live = _norm_cols(socrata_all("data.ny.gov", "9a8c-vfzj").drop(columns=["georeference"], errors="ignore"))
    copies = _wayback_copies("9a8c-vfzj", "rfs") + [(pd.Timestamp.today().strftime("%Y%m%d"), live)]
    rows = []
    for day, df in copies:
        cty = df["county"].str.upper().str.strip()
        df = df[cty.isin(NYC_COUNTIES)].copy()
        df["snap_day"] = day
        rows.append(df)
        log(f"  rfs copy {day}: {len(df):,} NYC rows")
    allc = pd.concat(rows, ignore_index=True)
    allc["license_number"] = allc["license_number"].astype(str).str.strip().str.lstrip("0")
    allc.to_parquet(CACHE / "agm_rfs_snapshots.parquet")
    g = allc.groupby("license_number")
    last = allc.sort_values("snap_day").groupby("license_number").tail(1).set_index("license_number")
    out = pd.DataFrame({
        "source": "agm_retail_food_stores", "source_id": last.index,
        "name": last["dba_name"].fillna(last["entity_name"]).values, "legal_name": last["entity_name"].values,
        "house": last["street_number"].values, "street": last["street_name"].values,
        "zip": last["zip_code"].astype(str).str[:5].values,
        "boro": last["county"].str.upper().str.strip().map(NYC_COUNTIES).values,
        "category_raw": last["estab_type"].values,
        "first_seen": pd.to_datetime(g["snap_day"].min().reindex(last.index)).values,
        "last_seen": pd.to_datetime(g["snap_day"].max().reindex(last.index)).values,
        "n_copies": g["snap_day"].nunique().reindex(last.index).values,
        "square_footage": pd.to_numeric(last.get("square_footage"), errors="coerce").values,
    })
    out["address"] = (out["house"].fillna("") + " " + out["street"].fillna("")).str.strip()
    nm = out["name"].fillna("").str.upper()
    est = out["category_raw"].fillna("")
    out["category"] = "grocery"
    small = out["square_footage"].fillna(1500) <= 2500
    out.loc[small, "category"] = "bodega_deli"
    out.loc[nm.str.contains(r"\bDELI|BODEGA|GROCERY|MINI ?MART|CANDY|NEWS|CONVENIEN|FOOD MART", na=False), "category"] = "bodega_deli"
    out.loc[est.str.contains("B") | nm.str.contains(r"BAKERY|PANADERIA|PASTRY|PATISSERIE|BAKE SHOP|DONUT|BAGEL", na=False), "category"] = "bakery"
    out.loc[nm.str.contains(r"COFFEE|ESPRESSO|\bTEA\b|ROASTER|CAFE\b", na=False), "category"] = "coffee_tea_retail"
    out.loc[nm.str.contains(r"SUPERMARKET|KEY FOOD|C-TOWN|CTOWN|FOODTOWN|STOP & SHOP|WHOLE FOODS|"
                            r"TRADER JOE|FAIRWAY|GRISTEDES|D'AGOSTINO|FOOD BAZAAR|SHOPRITE|ALDI|"
                            r"MET FOOD|ASSOCIATED|BRAVO", na=False), "category"] = "grocery"
    out.loc[nm.str.contains(r"PHARMACY|CVS|DUANE READE|WALGREEN|RITE AID|DOLLAR|GAS|FUEL|MOBIL|"
                            r"SUNOCO|SHELL|BP\b|EXXON|CITGO|LUKOIL|HESS|SPEEDWAY", na=False), "category"] = "other_retail_food"
    out["extra"] = [json.dumps({"estab": [RFS_ESTAB.get(x.strip(), x) for x in str(e).split(",") if x.strip()]})
                    for e in est]
    out = geocode(out)
    return save(out, "agm_retail_food_stores_nyc", source="NYS Ag & Markets (data.ny.gov 9a8c-vfzj) + web.archive.org",
                url="https://data.ny.gov/api/views/9a8c-vfzj/rows.csv",
                note="One row per licence; first/last_seen = earliest/latest copy containing it "
                     "(Wayback copies 2016-12..2026-03 + live). No issue dates in the source: first_seen 2016-12 is "
                     "left-censored. Licence numbers are sequential (higher = newer).")


def agm_insp():
    live = _norm_cols(socrata_all("data.ny.gov", "d6dy-3h7r").drop(columns=["georeference"], errors="ignore"))
    copies = _wayback_copies("d6dy-3h7r", "agm_insp") + [(pd.Timestamp.today().strftime("%Y%m%d"), live)]
    rows = []
    for day, df in copies:
        if "county" not in df:
            log(f"  !! copy {day} has no county column: {list(df.columns)[:8]}")
            continue
        df = df[df["county"].str.upper().str.strip().isin(NYC_COUNTIES)].copy()
        df["snap_day"] = day
        df = df.rename(columns={"zip_code": "zipcode", "statecode": "state_code"})
        if "establishment_type" not in df:
            df["establishment_type"] = None
        keep = [c for c in ("county", "inspection_grade", "inspection_date", "establishment_type", "owner_name",
                            "trade_name", "street", "city", "zipcode", "snap_day") if c in df]
        rows.append(df[keep].drop_duplicates(["trade_name", "street", "inspection_date"]))
        log(f"  insp copy {day}: {len(rows[-1]):,} NYC establishments")
    allc = pd.concat(rows, ignore_index=True)
    allc["inspection_date"] = pd.to_datetime(allc["inspection_date"], errors="coerce")
    allc["key"] = (allc["trade_name"].fillna("").str.upper().str.strip() + "|" +
                   allc["street"].fillna("").str.upper().str.strip() + "|" + allc["zipcode"].astype(str).str[:5])
    allc.to_parquet(CACHE / "agm_insp_snapshots.parquet")
    g = allc.groupby("key")
    last = allc.sort_values(["snap_day", "inspection_date"]).groupby("key").tail(1).set_index("key")
    hs = last["street"].map(split_house)
    out = pd.DataFrame({
        "source": "agm_inspections", "source_id": last.index,
        "name": last["trade_name"].values, "legal_name": last["owner_name"].values,
        "address": last["street"].values, "house": [h for h, _ in hs], "street": [s for _, s in hs],
        "zip": last["zipcode"].astype(str).str[:5].values,
        "boro": last["county"].str.upper().str.strip().map(NYC_COUNTIES).values,
        "category_raw": last["establishment_type"].values,
        "start_date": g["inspection_date"].min().reindex(last.index).values,
        "end_date": None,
        "first_seen": pd.to_datetime(g["snap_day"].min().reindex(last.index)).values,
        "last_seen": pd.to_datetime(g["snap_day"].max().reindex(last.index)).values,
        "last_inspection": g["inspection_date"].max().reindex(last.index).values,
        "n_inspection_dates": g["inspection_date"].nunique().reindex(last.index).values,
    })
    nm = out["name"].fillna("").str.upper()
    out["category"] = "bodega_deli"
    out.loc[out["category_raw"].fillna("").str.contains("B") | nm.str.contains(r"BAKERY|PANADERIA|PASTRY|DONUT|BAGEL", na=False), "category"] = "bakery"
    out.loc[nm.str.contains(r"COFFEE|ESPRESSO|\bTEA\b|ROASTER", na=False), "category"] = "coffee_tea_retail"
    out.loc[nm.str.contains(r"SUPERMARKET|KEY FOOD|C-TOWN|CTOWN|FOODTOWN|STOP & SHOP|WHOLE FOODS|TRADER JOE|"
                            r"FAIRWAY|FOOD BAZAAR|SHOPRITE|ALDI", na=False), "category"] = "grocery"
    out = geocode(out)
    return save(out, "agm_inspections_nyc", source="NYS Ag & Markets (data.ny.gov d6dy-3h7r) + web.archive.org",
                url="https://data.ny.gov/api/views/d6dy-3h7r/rows.csv",
                note="Key = trade name + street + zip. start_date = earliest inspection date seen across copies "
                     "(2020-01..now + live); last_inspection = latest. 'Current ratings' only keeps the last "
                     "inspection, so dates are sparse.")
