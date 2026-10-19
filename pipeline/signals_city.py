"""NYC Open Data proof-of-life signals: 311, DOB job filings, Open Restaurants inspections.

Each fetch_* pulls with a SoQL filter (never a full download) and saves one parquet in
data/raw/signals/ via signals_common.finish/save.
"""
from __future__ import annotations

import re

import pandas as pd

from signals_common import NYC, finish, save, socrata, word_re

# ---------------------------------------------------------------- 311
# 2010-2019 and 2020-present are separate datasets with the same columns.
SR_311 = {"76ig-c548": "2010-2019", "erm2-nwe9": "2020-now"}
# location_type values that name a food/drink business as the place complained about
FOOD_LOC = ("Restaurant/Bar/Deli/Bakery", "Club/Bar/Restaurant", "Restaurant", "Catering Service",
            "Food Establishment or Vendor")
CLOSED_RE = re.compile(r"out of business|closed and padlocked|establishment was closed|"
                       r"was re-closed|establishment .{0,20}closed", re.I)


def fetch_311() -> pd.DataFrame:
    sel = ("unique_key,created_date,complaint_type,descriptor,location_type,incident_address,"
           "incident_zip,borough,bbl,latitude,longitude,resolution_description")
    where = (f"location_type in ({','.join(repr(x) for x in FOOD_LOC)}) "
             "OR complaint_type = 'Outdoor Dining'")
    frames = []
    for dsid, span in SR_311.items():
        print(f"311 {dsid} ({span})", flush=True)
        frames.append(socrata(NYC, dsid, where=where, select=sel).assign(dataset=dsid))
    raw = pd.concat(frames, ignore_index=True).drop_duplicates("unique_key")
    ct = raw["complaint_type"].fillna("")
    etype = pd.Series("complaint_other", index=raw.index)
    etype[ct.str.contains("Noise", case=False)] = "complaint_noise"
    etype[ct.isin(["Food Establishment", "Food Poisoning"])] = "complaint_food"
    etype[ct.str.startswith("Smoking")] = "complaint_smoking"
    etype[ct.eq("Drinking")] = "complaint_drinking"
    etype[ct.eq("Outdoor Dining")] = "complaint_outdoor_dining"
    df = pd.DataFrame({
        "source_id": raw["unique_key"], "event_date": raw["created_date"], "event_type": etype,
        "address": raw["incident_address"], "boro": raw["borough"], "zip": raw["incident_zip"],
        "bbl": raw["bbl"], "lat": raw["latitude"], "lon": raw["longitude"],
        "detail": raw["complaint_type"] + " | " + raw["descriptor"].fillna("") + " | "
        + raw["location_type"].fillna(""),
        "resolution_closed": raw["resolution_description"].fillna("").str.contains(CLOSED_RE),
        "dataset": raw["dataset"],
    })
    df = finish(df, source="311")
    save(df, "sr311_food", dataset_id=",".join(SR_311), domain=NYC,
         note="311 SRs whose location_type is a restaurant/bar/deli/club/caterer, plus all Outdoor "
              "Dining SRs. No business name. resolution_closed = resolution text says closed/out of business.")
    return df


# ---------------------------------------------------------------- DOB
FOOD_WORDS = [r"RESTAURANTS?", r"EATING (AND|&) DRINKING", r"EATING", r"CAFES?", r"CAF\xc9",
              r"BARS?", r"TAVERN", r"PUB", r"LOUNGE", r"PIZZERIA", r"PIZZA", r"BAKERY", r"COFFEE SHOP",
              r"COFFEE", r"DELI", r"DELICATESSEN", r"DINER", r"BISTRO", r"KITCHEN EXHAUST",
              r"COMMERCIAL KITCHEN", r"KITCHEN HOOD", r"ANSUL", r"GREASE (TRAP|INTERCEPTOR)",
              r"FOOD SERVICE", r"TAKE ?OUT", r"BAR/RESTAURANT", r"NIGHT ?CLUB", r"BEER", r"WINE BAR"]
FOOD_RE = word_re(FOOD_WORDS)
# words that make a hit almost always non-commercial-food: school/office cafeterias, residential amenity
# lounges, grab bars, rebar, "bar joists", sushi-bar furniture in apartments etc.
NOT_FOOD_RE = re.compile(r"CAFETERIA|GRAB BARS?|REBAR|BAR JOIST|RESIDENT(IAL|S)? LOUNGE|"
                         r"TENANT LOUNGE|SCHOOL|\bP\.?S\.? ?\d|HOSPITAL|CHURCH|BARRIER|BARRICADE|"
                         r"\bTOW(ING)? BAR|SALAD BAR|NAIL BAR|DRY BAR|BLOW ?DRY|STUDENT LOUNGE|"
                         r"EMPLOYEE (CAFE|LOUNGE)|STAFF (CAFE|LOUNGE)|PANTRY", re.I)
STRONG_RE = re.compile(r"RESTAURANT|EATING (AND|&) DRINKING|PIZZ|BAKERY|TAVERN|\bBAR\b|\bCAFE\b|"
                       r"COFFEE SHOP|DELI\b|DINER|BISTRO|NIGHT ?CLUB|TAKE ?OUT", re.I)
DESC_LIKE = ["RESTAURANT", "EATING", "CAFE", " BAR", "BAR ", "TAVERN", " PUB", "LOUNGE", "PIZZ",
             "BAKERY", "COFFEE", "DELI", "DINER", "BISTRO", "KITCHEN EXHAUST", "COMMERCIAL KITCHEN",
             "KITCHEN HOOD", "ANSUL", "GREASE", "FOOD SERVICE", "TAKE OUT", "TAKEOUT", "NIGHT CLUB",
             "NIGHTCLUB", "WINE BAR", "BEER"]


def _desc_where(col: str) -> str:
    return "(" + " OR ".join(f"upper({col}) like '%{w}%'" for w in DESC_LIKE) + ")"


def _food_filter(desc: pd.Series) -> pd.Series:
    d = desc.fillna("")
    return d.str.contains(FOOD_RE) & ~(d.str.contains(NOT_FOOD_RE) & ~d.str.contains(STRONG_RE))


def fetch_dob_bis() -> pd.DataFrame:
    """BIS job filings (ic3t-wcy2), one row per job (doc 01), 1989-2020s."""
    sel = ("job__,doc__,borough,house__,street_name,bin__,bbl,job_type,job_status,job_status_descrp,"
           "pre__filing_date,approved,fully_permitted,signoff_date,latest_action_date,"
           "existing_occupancy,proposed_occupancy,owner_s_business_name,job_description,"
           "gis_latitude,gis_longitude,zip")
    raw = socrata(NYC, "ic3t-wcy2", where=_desc_where("job_description"), select=sel)
    raw = raw[_food_filter(raw["job_description"])]
    raw = raw.sort_values("doc__").drop_duplicates("job__")
    rows = []
    for col, et in (("pre__filing_date", "dob_filing"), ("fully_permitted", "dob_permit"),
                    ("signoff_date", "dob_signoff")):
        r = raw[raw[col].notna()]
        rows.append(pd.DataFrame({
            "source_id": r["job__"], "event_date": pd.to_datetime(r[col], format="%m/%d/%Y", errors="coerce"),
            "event_type": et, "name": r["owner_s_business_name"], "house": r["house__"],
            "street": r["street_name"], "boro": r["borough"], "zip": r["zip"], "bbl": r["bbl"],
            "bin": r["bin__"], "lat": r["gis_latitude"], "lon": r["gis_longitude"],
            "detail": r["job_type"] + " | " + r["job_description"].str.slice(0, 300),
            "job_type": r["job_type"], "job_status": r["job_status_descrp"],
            "occ_from_to": r["existing_occupancy"].fillna("") + ">" + r["proposed_occupancy"].fillna("")}))
    df = pd.concat(rows, ignore_index=True)
    # BIS stores blank dates as 01/01/1900-ish placeholders in places
    df = df[pd.to_datetime(df["event_date"], errors="coerce") >= "1990-01-01"]
    df = finish(df, source="dob_bis")
    save(df, "dob_bis_food", dataset_id="ic3t-wcy2", domain=NYC,
         note="BIS job filings whose description mentions a restaurant/bar/cafe/kitchen exhaust etc. "
              "One row per (job, milestone): filing, fully permitted, signoff. name = owner business "
              "name (often the landlord).")
    return df


def fetch_dob_now() -> pd.DataFrame:
    """DOB NOW: Build job filings (w9ak-ipjd), 2016+."""
    sel = ("job_filing_number,filing_status,house_no,street_name,borough,bin,bbl,zip,postcode,job_type,"
           "filing_date,first_permit_date,approved_date,signoff_date,owner_s_business_name,"
           "job_description,latitude,longitude,place_of_assembly_work_type_")
    raw = socrata(NYC, "w9ak-ipjd", where=_desc_where("job_description"), select=sel)
    raw = raw[_food_filter(raw["job_description"])]
    raw["job"] = raw["job_filing_number"].str.split("-").str[0]
    raw = raw.sort_values("job_filing_number").drop_duplicates("job")
    rows = []
    for col, et in (("filing_date", "dob_filing"), ("first_permit_date", "dob_permit"),
                    ("signoff_date", "dob_signoff")):
        r = raw[raw[col].notna()]
        rows.append(pd.DataFrame({
            "source_id": r["job"], "event_date": r[col], "event_type": et,
            "name": r["owner_s_business_name"], "house": r["house_no"], "street": r["street_name"],
            "boro": r["borough"], "zip": r["postcode"].fillna(r["zip"]), "bbl": r["bbl"], "bin": r["bin"],
            "lat": r["latitude"], "lon": r["longitude"],
            "detail": r["job_type"] + " | " + r["job_description"].str.slice(0, 300),
            "job_type": r["job_type"], "job_status": r["filing_status"]}))
    df = finish(pd.concat(rows, ignore_index=True), source="dob_now")
    save(df, "dob_now_food", dataset_id="w9ak-ipjd", domain=NYC,
         note="DOB NOW job filings (2016+) mentioning restaurant/bar/cafe/kitchen etc.; one row per "
              "(job, milestone).")
    return df


# ---------------------------------------------------------------- Open Restaurants inspections
def fetch_open_rest_insp() -> pd.DataFrame:
    raw = socrata(NYC, "4dx7-axux")
    df = pd.DataFrame({
        "source_id": raw["restaurantinspectionid"], "event_date": raw["inspectedon"],
        "event_type": "outdoor_dining_inspection", "name": raw["restaurantname"],
        "legal_name": raw["legalbusinessname"], "address": raw["businessaddress"],
        "boro": raw["borough"], "zip": raw["postcode"], "bbl": raw["bbl"], "bin": raw["bin"],
        "lat": raw["latitude"], "lon": raw["longitude"],
        "detail": raw["agencycode"].fillna("") + " | sidewalk:" + raw["issidewaycompliant"].fillna("")
        + " roadway:" + raw["isroadwaycompliant"].fillna("") + " | " + raw["skippedreason"].fillna(""),
        "skipped": raw["skippedreason"].notna(),
    })
    df = finish(df, source="open_restaurants_insp")
    save(df, "open_restaurants_insp", dataset_id="4dx7-axux", domain=NYC,
         note="DOT/DOB/SBS compliance inspections of COVID Open Restaurants setups 2020-07..2024-05, "
              "with DBA and legal name. skipped=True: inspector skipped (e.g. 'closed', 'no setup').")
    return df


# ---------------------------------------------------------------- NYC Business Acceleration
NYCBA_FOOD = ("Restaurants and Other Eating Places", "Drinking Places (Alcoholic Beverages)",
              "Food Services and Drinking Places", "Specialty Food Stores", "Special Food Services")


def fetch_nycba() -> pd.DataFrame:
    """SBS NYC Business Acceleration clients (2010-2019) with their *actual opening date*."""
    raw = socrata(NYC, "9b9u-8989")
    p = "establishment_record_"
    food = raw[f"{p}establishment_category"].isin(NYCBA_FOOD) | (
        raw[f"{p}establishment_category"].isna() & raw[f"{p}business_sector"].eq("Accommodations and Food"))
    raw = raw[food & raw[f"{p}actual_opening_date"].notna()]
    df = pd.DataFrame({
        "source_id": raw.index.astype(str), "event_date": raw[f"{p}actual_opening_date"],
        "event_type": "opened", "name": raw[f"{p}dba"], "address": raw[f"{p}establishment_street"],
        "zip": raw[f"{p}establishment_zip"], "boro": raw[f"{p}establishment_borough"],
        "detail": raw[f"{p}establishment_category"].fillna("") + " | " + raw[f"{p}type_of_cuisine"].fillna(""),
        "employees": pd.to_numeric(raw["number_of_employees"], errors="coerce")})
    df = finish(df, source="nyc_business_acceleration")
    save(df, "nyc_business_acceleration", dataset_id="9b9u-8989", domain=NYC,
         note="SBS NYC Business Acceleration clients in food/drink with their actual opening date "
              "(2010-2019). source_id = row order of the pull (dataset has no id).")
    return df
