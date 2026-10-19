"""NY State Liquor Authority (NYSLA) licenses for the 5 NYC counties.

Sources
- data.ny.gov 9s3h-dpkz  Current active licenses (new LAMP system; original dates reset ~2020-08)
- data.ny.gov 6dg3-2z7i  Current inactive licenses (expirations 2015+)
- data.ny.gov f8i8-k2gm  Current pending applications
- Wayback Machine copies of the retired data.ny.gov hrvs-fxs2 "Liquor Authority Quarterly
  List of Active Licenses" (now private): 2017-04, 2021-04, 2022-12 statewide CSVs. These keep
  the true pre-2020 original issue dates and are joined to the new system via legacy serial no.

Outputs (data/raw/gov/)
- sla_active_nyc, sla_inactive_nyc, sla_pending_nyc   (current, raw fields)
- sla_snapshots_nyc   (harmonised Wayback snapshots, one row per serial per snapshot)
- sla_licenses_nyc    (one row per license: best start date, end date, status, class, names)
"""
from __future__ import annotations

import gzip
import io

import pandas as pd

from gov_common import NYC_COUNTIES, OUT, get, save, socrata

NYC_WHERE = "upper({c}) in ('NEW YORK','KINGS','QUEENS','BRONX','RICHMOND')"
# Wayback captures of retired (now private) data.ny.gov datasets: (dataset id, timestamp)
#  hrvs-fxs2 = quarterly list of ACTIVE licenses (true original issue dates)
#  i594-5w3n = inactive licenses with "Date Inactive" (rolling ~5-7 yr window)
#  wzgj-tb42 = expired (not renewed) licenses
WAYBACK = [
    ("hrvs-fxs2", "20170424224417"), ("hrvs-fxs2", "20210414225347"),
    ("hrvs-fxs2", "20221208073325"),
    ("i594-5w3n", "20210330215301"), ("i594-5w3n", "20210702111237"),
    ("i594-5w3n", "20220123111444"), ("i594-5w3n", "20221208012520"),
    ("i594-5w3n", "20230622115920"),
    ("wzgj-tb42", "20221129210053"), ("wzgj-tb42", "20230622115332"),
]
NYC_ABBR = {"NEW", "KING", "QUEE", "BRON", "RICH"}  # wzgj/i594 4-letter county codes
# column name variants across snapshot schemas -> harmonised name
RENAME = {
    "License Serial Number": "serial", "Serial Number": "serial",
    "County Name (Licensee)": "county", "County": "county",
    "License Type Name": "type_name", "License Class Code": "class_code",
    "License Type Code": "type_code", "Premises Name": "premise_name", "Premise Name": "premise_name",
    "Doing Business As (DBA)": "dba", "DBA": "dba",
    "Actual Address of Premises (Address1)": "address", "Premise Address": "address",
    "Additional Address Information (Address2)": "address2", "Premise Address 2": "address2",
    "City": "city", "Premise City": "city", "Zip": "zip", "Premise Zip": "zip",
    "License Certificate Number": "certificate", "Certificate Number": "certificate",
    "License Original Issue Date": "original_date", "Original Date": "original_date",
    "License Effective Date": "effective_date", "Effective Date": "effective_date",
    "License Expiration Date": "expiration_date", "License Issued Date": "issued_date",
    "Method of Operation": "method_of_operation", "Latitude": "lat", "Longitude": "lon",
    "Georeference": "georeference", "Date Inactive": "date_inactive",
    "Expiration Date": "expiration_date", "Expired": "expiration_date",
    "Effective": "effective_date", "License Issue Date": "issued_date",
    "Received Date": "received_date", "County Name": "county_name",
}


def wayback_snapshot(dsid: str, ts: str) -> pd.DataFrame:
    cache = OUT / "wayback" / f"{dsid}_{ts}.csv.gz"
    if cache.exists():
        raw = gzip.decompress(cache.read_bytes())
    else:
        url = f"https://data.ny.gov/api/views/{dsid}/rows.csv?accessType=DOWNLOAD"
        raw = get(f"http://web.archive.org/web/{ts}id_/{url}", timeout=600).content
        if raw[:2] == b"\x1f\x8b":  # some captures are stored gzip-encoded
            raw = gzip.decompress(raw)
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(gzip.compress(raw))
    df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, na_values=[""])
    if "serial" not in df.rename(columns=RENAME):
        raise ValueError(f"wayback {ts}: unexpected columns {list(df.columns)[:6]}")
    df = df.rename(columns=RENAME)
    cty = df["county"].str.upper()
    nyc = cty.isin(NYC_COUNTIES) | cty.isin(NYC_ABBR)
    if "county_name" in df:
        nyc = df["county_name"].str.upper().isin(NYC_COUNTIES)
    df = df[nyc].copy()
    if "georeference" in df and "lat" not in df:  # "POINT (lon lat)"
        xy = df["georeference"].str.extract(r"POINT \(([-\d.]+) ([-\d.]+)\)")
        df["lon"], df["lat"] = xy[0], xy[1]
    keep = [c for c in dict.fromkeys(RENAME.values()) if c in df and c != "georeference"]
    df = df[keep]
    df.insert(0, "snapshot", pd.Timestamp(ts[:8]).date().isoformat())
    df.insert(0, "dataset", dsid)
    for c in ("original_date", "effective_date", "expiration_date", "issued_date",
              "date_inactive", "received_date"):
        if c in df:
            df[c] = pd.to_datetime(df[c], format="%m/%d/%Y", errors="coerce")
    return df


def _point(df: pd.DataFrame) -> pd.DataFrame:
    """Socrata CSV exports the point as 'POINT (lon lat)'."""
    if "georeference" in df:
        xy = df["georeference"].str.extract(r"POINT \(([-\d.]+) ([-\d.]+)\)")
        df["lon"], df["lat"] = xy[0].astype(float), xy[1].astype(float)
        df = df.drop(columns="georeference")
    return df


# Old-system type codes (hrvs-fxs2 era) -> unified category
OLD_TYPE = {
    **dict.fromkeys(["OP", "RL", "RW", "EB", "SL", "SB", "SW", "MR"], "restaurant"),
    **dict.fromkeys(["TW", "TS", "EL", "ZT", "TL", "CR", "BL"], "bar_tavern"),
    **dict.fromkeys(["HL", "HW"], "hotel"), **dict.fromkeys(["CT", "WC"], "catering"),
    **dict.fromkeys(["CL", "CW", "CB"], "club"),
    **dict.fromkeys(["VL", "AL", "RR", "BP", "ZL", "ZW", "ZB"], "other_on_premises"),
    **dict.fromkeys(["A", "AX", "DX", "AW"], "grocery_drug"), **dict.fromkeys(["L", "W"], "liquor_store"),
}


def category(desc, old_type, method) -> str:
    """Unified license category across the old (pre-2023) and LAMP class systems."""
    d = desc.lower() if isinstance(desc, str) else ""
    m = method.upper() if isinstance(method, str) else ""
    if old_type in OLD_TYPE:
        cat = OLD_TYPE[old_type]
        if cat == "restaurant" and ("TAVERN" in m or "BAR/" in m or "NIGHT" in m):
            return "bar_tavern"
        return cat
    if not d:
        return "unknown"
    if d.startswith("additional bar"):
        return "additional_bar"
    if "restaurant" in d and "brewer" not in d:
        return "restaurant"
    if "food & beverage" in d or "tavern" in d or d in ("cabaret", "night club", "bottle club"):
        return "bar_tavern"  # LAMP "Food & Beverage Business" = on-premises bars/taverns etc.
    if "club" in d:
        return "club"
    if d == "hotel":
        return "hotel"
    if "catering" in d or "caterer" in d:
        return "catering"
    if d in ("grocery store", "drug store"):
        return "grocery_drug"
    if d in ("liquor store", "wine store"):
        return "liquor_store"
    if any(k in d for k in ("vessel", "theatre", "theater", "venue", "stadium", "aircraft",
                            "railroad", "golf", "concert")):
        return "other_on_premises"
    return "manufacturer_wholesale_other"


def build_licenses(active, inactive, snaps) -> pd.DataFrame:
    """One row per NYC license (keyed by legacy serial number)."""
    a = active.rename(columns={
        "legacyserialnumber": "serial", "licensepermitid": "license_id", "premisescounty": "county",
        "legalname": "legal_name", "actualaddressofpremises": "address", "zipcode": "zip",
        "originalissuedate": "lamp_original_date", "expirationdate": "expiration_date",
        "effectivedate": "effective_date"})
    a["status"] = "active"
    i = inactive.rename(columns={
        "legacy_serial_number": "serial", "license_permit_id": "license_id",
        "premises_county": "county", "legalname": "legal_name",
        "actual_address_of_premises": "address", "zip_code": "zip",
        "original_issue_date": "lamp_original_date", "expiration_date": "expiration_date",
        "effective_date": "effective_date"})
    i["status"] = "inactive"
    cols = ["serial", "license_id", "status", "county", "type", "class", "description",
            "legal_name", "dba", "address", "city", "zip", "lamp_original_date",
            "effective_date", "expiration_date", "lat", "lon"]
    cur = pd.concat([a[cols], i[cols]], ignore_index=True)
    for c in ("lamp_original_date", "effective_date", "expiration_date"):
        cur[c] = pd.to_datetime(cur[c], errors="coerce")
    # same serial can be both (renewed under new id); prefer active, then latest expiry
    cur = cur.sort_values(["serial", "status", "expiration_date"], ascending=[True, True, False])
    cur = cur.drop_duplicates("serial", keep="first")

    snaps = snaps.sort_values(["dataset", "snapshot"])  # hrvs last -> wins "last" attributes
    s = snaps.groupby("serial").agg(
        snap_original_date=("original_date", "min"),
        snap_premise_name=("premise_name", "last"), snap_dba=("dba", "last"),
        snap_address=("address", "last"), snap_city=("city", "last"), snap_zip=("zip", "last"),
        snap_class=("class_code", "last"), snap_type=("type_code", "last"),
        snap_method=("method_of_operation", "last"), snap_county=("county", "last"),
        snap_lat=("lat", "last"), snap_lon=("lon", "last"),
        snap_last_expiration=("expiration_date", "max"),
        date_inactive=("date_inactive", "max"),
    ).reset_index()
    seen = snaps[snaps["dataset"] == "hrvs-fxs2"].groupby("serial")["snapshot"].agg(
        first_seen_active="min", last_seen_active="max").reset_index()
    s = s.merge(seen, on="serial", how="left")
    s["in_wayback_inactive"] = s["serial"].isin(snaps.loc[snaps["dataset"] != "hrvs-fxs2", "serial"])

    out = cur.merge(s, on="serial", how="outer", indicator=True)
    out["in_current_lists"] = out["_merge"] != "right_only"
    out["in_wayback"] = out["_merge"] != "left_only"
    out = out.drop(columns="_merge")
    out["in_wayback_inactive"] = out["in_wayback_inactive"].astype("boolean").fillna(False)
    # start: true original date from old system if seen, else LAMP original date
    out["start_date"] = out["snap_original_date"].fillna(out["lamp_original_date"])
    out["start_date_source"] = out["snap_original_date"].notna().map(
        {True: "wayback_original", False: "lamp_original"})
    # status for licenses missing from the current lists
    out.loc[~out["in_current_lists"] & out["in_wayback_inactive"], "status"] = "inactive_wayback"
    out.loc[out["status"].isna(), "status"] = "gone_from_lists"
    # end: "Date Inactive" from wayback i594 > current-inactive expiry > last known expiry
    ended = out["status"] != "active"
    out["end_date"] = pd.NaT
    out["end_date_source"] = pd.NA
    for col, tag in (("date_inactive", "date_inactive"), ("expiration_date", "expiration"),
                     ("snap_last_expiration", "last_known_expiration")):
        m = ended & out["end_date"].isna() & out[col].notna()
        out.loc[m, "end_date"] = out.loc[m, col]
        out.loc[m, "end_date_source"] = tag
    out["end_date"] = pd.to_datetime(out["end_date"])
    # an "expiration" end is only an upper bound; surrendered licenses can expire in the future
    today = pd.Timestamp.today().normalize()
    out["end_date"] = out["end_date"].mask(out["end_date"] > today, today)
    for c in ("address", "dba", "zip", "county", "lat", "lon", "city"):
        out[c] = out[c].fillna(out[f"snap_{c}"])
    out["legal_name"] = out["legal_name"].fillna(out["snap_premise_name"])
    out["class"] = out["class"].fillna(out["snap_class"])
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    out["category"] = [category(d, t, m) for d, t, m in
                       zip(out["description"], out["snap_type"], out["snap_method"])]
    out["on_premises"] = out["category"].isin(
        ["restaurant", "bar_tavern", "club", "hotel", "catering", "other_on_premises"])
    # LAMP re-issues a new serial on class changes / additional bars, so group licenses that
    # share a normalised legal name + address into one "premise" with its earliest start.
    norm = lambda x: x.fillna("").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
    out["premise_key"] = norm(out["legal_name"]) + "|" + norm(out["address"]) + "|" + out["zip"].fillna("").str[:5]
    out["premise_first_start"] = out.groupby("premise_key")["start_date"].transform("min")
    return out


def run():
    print("== NYSLA")
    active = _point(socrata("data.ny.gov", "9s3h-dpkz", where=NYC_WHERE.format(c="premisescounty")))
    save(active, "sla_active_nyc", source="data.ny.gov", dataset_id="9s3h-dpkz",
         date_cols=["originalissuedate", "lastissuedate", "expirationdate"],
         note="Current active NYSLA licenses, NYC counties. originalissuedate reset by LAMP "
              "migration (min 2020-08-03); use legacyserialnumber to join older snapshots.")
    inactive = _point(socrata("data.ny.gov", "6dg3-2z7i", where=NYC_WHERE.format(c="premises_county")))
    save(inactive, "sla_inactive_nyc", source="data.ny.gov", dataset_id="6dg3-2z7i",
         date_cols=["original_issue_date", "expiration_date"],
         note="Inactive NYSLA licenses, NYC; expiration_date >= 2015-01-31 only.")
    pending = socrata("data.ny.gov", "f8i8-k2gm", where=NYC_WHERE.format(c="premises_county"))
    save(pending, "sla_pending_nyc", source="data.ny.gov", dataset_id="f8i8-k2gm",
         date_cols=["received_date"], note="Pending NYSLA applications, NYC.")

    snaps = []
    for dsid, ts in WAYBACK:
        print(f"  wayback {dsid} {ts}", flush=True)
        snaps.append(wayback_snapshot(dsid, ts))
    snaps = pd.concat(snaps, ignore_index=True)
    for c in ("lat", "lon"):
        snaps[c] = pd.to_numeric(snaps[c], errors="coerce")
    save(snaps, "sla_wayback_nyc", source="web.archive.org (data.ny.gov, retired datasets)",
         dataset_id="hrvs-fxs2,i594-5w3n,wzgj-tb42",
         date_cols=["original_date", "expiration_date", "date_inactive"],
         note="Wayback captures: " + ", ".join(f"{d}@{t}" for d, t in WAYBACK))

    lic = build_licenses(active, inactive, snaps)
    save(lic, "sla_licenses_nyc", source="derived",
         dataset_id="9s3h-dpkz+6dg3-2z7i+hrvs-fxs2+i594-5w3n+wzgj-tb42",
         date_cols=["start_date", "end_date"],
         note="One row per legacy serial. start_date = old-system original date when known.")


if __name__ == "__main__":
    run()
