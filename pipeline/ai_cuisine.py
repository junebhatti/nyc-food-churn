"""Cuisine: decode old WebExtract numeric codes, fix mojibake, map every value to ~22 families.

Code list: Cuisine.txt in DOHMH's own BigApps zip (dohmh_restaurant-inspections_002.zip,
2014-08-28; copy at github.com/spkal/NYC_Health_Ratings). Checked against an empirical
crosswalk: CAMIS seen with a code in 2013-16 copies and with text in later copies.

Outputs: cuisine_codes.csv, cuisine_code_crosswalk.csv, cuisine_family_map.csv, camis_cuisine.parquet
"""
from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from ai_common import SRC, UNION, WEB, con, log, write_out

ZIP_URL = "https://raw.githubusercontent.com/spkal/NYC_Health_Ratings/HEAD/dohmh_restaurant-inspections_002.zip"

FAMILY = {
    "american": ["American", "New American", "Continental", "Californian", "Southwestern", "Hawaiian",
                 "Polynesian", "Australian"],
    "burgers_hotdogs": ["Hamburgers", "Hotdogs", "Hotdogs/Pretzels"],
    "chicken": ["Chicken"],
    "bbq_steak_southern": ["Barbecue", "Steak", "Steakhouse", "Soul Food", "Cajun", "Creole", "Creole/Cajun"],
    "pizza": ["Pizza", "Pizza/Italian"],
    "italian": ["Italian"],
    "chinese": ["Chinese", "Chinese/Cuban", "Chinese/Japanese"],
    "japanese_korean": ["Japanese", "Korean"],
    "southeast_asian_other_asian": ["Thai", "Vietnamese/Cambodian/Malaysia", "Filipino", "Indonesian",
                                    "Southeast Asian", "Asian", "Asian/Asian Fusion", "Fusion"],
    "south_asian": ["Indian", "Bangladeshi", "Pakistani", "Afghan"],
    "mexican_texmex": ["Mexican", "Tex-Mex"],
    "latin_caribbean": ["Latin (Cuban, Dominican, Puerto Rican, South & Central American)", "Latin American",
                        "Caribbean", "Spanish", "Peruvian", "Brazilian", "Chilean", "Chimichurri"],
    "mideast_mediterranean": ["Mediterranean", "Middle Eastern", "Greek", "Turkish", "Lebanese", "Moroccan",
                              "Egyptian", "Iranian", "Armenian"],
    "european": ["French", "New French", "Haute Cuisine", "German", "Irish", "English", "Eastern European",
                 "Russian", "Polish", "Czech", "Scandinavian", "Portuguese", "Basque", "Tapas"],
    "african": ["African", "Ethiopian"],
    "jewish_kosher": ["Jewish/Kosher"],
    "seafood": ["Seafood"],
    "vegetarian_vegan": ["Vegetarian", "Vegan"],
    "cafe_coffee_tea": ["Café/Coffee/Tea", "Coffee/Tea"],
    "bakery_desserts": ["Bakery", "Bakery Products/Desserts", "Donuts", "Frozen Desserts",
                        "Ice Cream, Gelato, Yogurt, Ices", "Nuts/Confectionary", "Pancakes/Waffles"],
    "juice_beverages": ["Juice, Smoothies, Fruit Salads", "Bottled Beverages",
                        "Bottled beverages, including water, sodas, juices, etc.", "Fruits/Vegetables"],
    "deli_sandwich_salad": ["Sandwiches", "Sandwiches/Salads/Mixed Buffet", "Delicatessen", "Bagels/Pretzels",
                            "Salads", "Soups", "Soups & Sandwiches", "Soups/Salads/Sandwiches"],
    "other_unknown": ["Other", "Not Listed/Not Applicable"],
}
# families that are mostly counter / limited service (for a rough service-style split)
LIMITED = {"burgers_hotdogs", "chicken", "pizza", "cafe_coffee_tea", "bakery_desserts", "juice_beverages",
           "deli_sandwich_salad"}


def fix_text(v: str | None) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    for _ in range(4):  # undo repeated latin-1 / cp1252 mojibake: CafÃƒÂ© -> Café
        if "Ã" not in s:
            break
        for enc in ("latin-1", "cp1252"):
            try:
                s = s.encode(enc).decode("utf-8")
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        else:
            break
    if re.fullmatch(r"Caf\S*/Coffee/Tea", s):  # any residue of the one accented value
        s = "Café/Coffee/Tea"
    return s.strip() or None


def code_key(v: str | None) -> str | None:
    """Two numbering systems exist:
    '03' / '3'  -> 'W03'  WebExtract list (official Cuisine.txt), 2013-2015 copies
    '3.0'       -> 'S03'  a different (2015-16 Socrata-era, alphabetical) list, in the CRAN mdsr
                          2016 copy; no official list found, so it is decoded empirically.
    """
    if v is None:
        return None
    s = str(v).strip()
    m = re.fullmatch(r"(\d{1,2})\.0+", s)
    if m:
        return "S" + m.group(1).zfill(2)
    m = re.fullmatch(r"\d{1,2}", s)
    return "W" + s.zfill(2) if m else None


def official_codes() -> pd.DataFrame:
    d = SRC / "spkal"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "Cuisine.txt"
    if not f.exists():
        r = WEB.get(ZIP_URL, timeout=300)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for n in ("Cuisine.txt", "Action.txt", "Violation.txt"):
                (d / n).write_bytes(z.read(n))
    t = pd.read_csv(f, dtype=str, encoding="cp1252")
    t.columns = ["code", "desc"]
    t["desc"] = t["desc"].str.strip()
    t["source"] = "DOHMH BigApps zip 2014-08-28 Cuisine.txt"
    return t


def build():
    codes = official_codes()
    write_out(codes, "cuisine_codes", ZIP_URL, "official DOHMH WebExtract cuisine code list", fmt="csv")
    c = con()
    rows = c.sql(f"""select camis, cuisine, max(inspection_date) last_date, count(*) n
                     from '{UNION}' where cuisine is not null and cuisine not in ('NA')
                     group by 1,2""").df()
    rows["code"] = rows["cuisine"].map(code_key)
    rows["text"] = rows["cuisine"].where(rows["code"].isna()).map(fix_text)

    # empirical crosswalk: per CAMIS, code value vs latest text value
    txt = rows.dropna(subset=["text"]).sort_values("last_date").groupby("camis")["text"].last()
    cw = rows.dropna(subset=["code"]).merge(txt.rename("later_text"), on="camis")
    cw = cw.groupby(["code", "later_text"]).camis.nunique().rename("n_camis").reset_index()
    cw["share"] = cw["n_camis"] / cw.groupby("code")["n_camis"].transform("sum")
    cw = cw.merge(codes.assign(code="W" + codes["code"])[["code", "desc"]], on="code", how="left").sort_values(["code", "n_camis"],
                                                                              ascending=[True, False])
    write_out(cw, "cuisine_code_crosswalk", "union_inspections",
              "code -> text agreement for CAMIS seen both coded and in text copies", fmt="csv")
    top = cw.groupby("code").head(1).set_index("code")
    code_desc = {"W" + k: v for k, v in codes.set_index("code")["desc"].items()}
    code_desc["S58"] = "Other"  # dominant later text is mixed (American 21%); behaves like W99 'Other'
    # codes absent from the official list: use the dominant empirical text if it is clear
    for k, r in top.iterrows():
        if k not in code_desc and r["n_camis"] >= 1:
            code_desc[k] = r["later_text"]
            log.info("code %s not in official list; empirical -> %s (%.0f%%)", k, r["later_text"], 100 * r["share"])
    rows["value"] = rows["text"].fillna(rows["code"].map(code_desc))

    fam = {v: f for f, vals in FAMILY.items() for v in vals}
    vals = (rows.dropna(subset=["value"]).groupby("value").camis.nunique().rename("n_camis").reset_index())
    vals["family"] = vals["value"].map(fam)
    unmapped = vals[vals["family"].isna()]
    if len(unmapped):
        log.warning("UNMAPPED cuisine values (-> other_unknown): %s", unmapped["value"].tolist())
    vals["family"] = vals["family"].fillna("other_unknown")
    vals["limited_service"] = vals["family"].isin(LIMITED)
    raw_map = rows[["cuisine", "code", "value"]].drop_duplicates().merge(vals[["value", "family"]], on="value",
                                                                         how="left")
    write_out(raw_map.sort_values("cuisine"), "cuisine_family_map", "this script",
              "every raw DOHMH cuisine string (text, coded, mojibake) -> clean value -> family", fmt="csv")

    # per CAMIS: latest informative value (skip Other/Not Listed when a real one exists)
    rows = rows.merge(vals[["value", "family"]], on="value", how="left")
    rows["informative"] = rows["family"].ne("other_unknown")
    rows = rows.sort_values(["camis", "informative", "last_date"])
    best = rows.groupby("camis").tail(1)[["camis", "value", "family"]]
    nfam = rows[rows.informative].groupby("camis")["family"].nunique().rename("n_families_seen")
    out = best.merge(nfam, on="camis", how="left").rename(columns={"value": "cuisine_clean"})
    out["n_families_seen"] = out["n_families_seen"].fillna(0).astype(int)
    out["limited_service"] = out["family"].isin(LIMITED)
    write_out(out, "camis_cuisine", "union_inspections + cuisine_family_map",
              "one row per CAMIS with a cuisine; latest informative value")
    return out


if __name__ == "__main__":
    build()
