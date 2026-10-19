"""Price-tier proxies per CAMIS that need no menu -> data/raw/menus/camis_proxies.parquet

  liquor        best on-premises NYSLA license matched to the CAMIS:
                'full' (OP/hotel/club/cabaret/catering...), 'wine_beer' (RW/TW), 'beer' (EB), 'none'
  cuisine       latest DOHMH cuisine (numeric WebExtract codes mapped to names)
  chain_n       distinct CAMIS sharing the normalized DBA (chain = 3+)
  fast_food     cuisine in a quick-service set, or the name is a known QSR/coffee brand,
                or a name-matched OSM node within 80 m is amenity=fast_food
  osm_brand     brand tag of that OSM node (if any)
"""
from __future__ import annotations

import pandas as pd

from menus_common import OUT, ROOT
from menus_match import camis_base, con, match

SLA = ROOT / "data" / "raw" / "gov" / "sla_licenses_nyc.parquet"
OSM = ROOT / "data" / "raw" / "poi" / "osm_overpass.parquet"

LEVEL = {"OP": 3, "HL": 3, "CL": 3, "CR": 3, "CT": 3, "VL": 3, "SL": 3, "EL": 3,
         "RW": 2, "TW": 2, "TS": 2, "EB": 1}
LEVEL_NAME = {3: "full", 2: "wine_beer", 1: "beer", 0: "none"}

QSR_CUISINES = {
    "Hamburgers", "Chicken", "Donuts", "Hotdogs", "Hotdogs/Pretzels", "Bagels/Pretzels",
    "Juice, Smoothies, Fruit Salads", "Frozen Desserts", "Ice Cream, Gelato, Yogurt, Ices",
    "Sandwiches", "Sandwiches/Salads/Mixed Buffet", "Soups/Salads/Sandwiches", "Salads",
    "Soups & Sandwiches", "Bottled Beverages", "Bottled beverages, including water, sodas, juices, etc.",
    "Nuts/Confectionary", "Pancakes/Waffles", "Delicatessen", "Coffee/Tea", "Café/Coffee/Tea",
    "Bakery", "Bakery Products/Desserts", "Fruits/Vegetables", "Soups",
}
QSR_BRANDS = (
    r"MCDONALD|BURGER KING|WENDY|SUBWAY|POPEYE|KFC|KENTUCKY FRIED|TACO BELL|DUNKIN|DOMINO|"
    r"PAPA JOHN|PIZZA HUT|LITTLE CAESAR|CHIPOTLE|STARBUCKS|WHITE CASTLE|CHECKERS|ARBY|"
    r"FIVE GUYS|SHAKE SHACK|SWEETGREEN|JUST SALAD|CHOPT|PRET A MANGER|LE PAIN QUOTIDIEN|"
    r"PANERA|QDOBA|CHICK FIL A|CHICKFILA|JOLLIBEE|DAIRY QUEEN|BASKIN|CARVEL|AUNTIE ANNE|"
    r"WINGSTOP|CROWN FRIED|KENNEDY FRIED|ALPHA FRIED|GOLDEN KRUST|HALAL GUYS|CHIPOTLE|"
    r"PIZZA 2 GO|2 BROS|99 CENT|TIM HORTONS|PANDA EXPRESS|SBARRO|NATHAN|ROBEKS|JAMBA|"
    r"TACO BELL|BOSTON MARKET|IHOP|DENNY|APPLEBEE|RED LOBSTER|OLIVE GARDEN|TGI FRIDAY|"
    r"BLIMPIE|QUIZNOS|JERSEY MIKE|POTBELLY|CAVA|DIG INN|DIG|PRETZEL|CINNABON|HALE AND HEARTY"
)


def sla_levels() -> pd.DataFrame:
    c = con()
    lic = c.execute(f"""
    select serial, coalesce(dba, snap_dba, legal_name, snap_premise_name) as name,
      coalesce(address, snap_address) as addr, coalesce(zip, snap_zip) as zip,
      coalesce(lat, snap_lat) lat, coalesce(lon, snap_lon) lon,
      coalesce(snap_type, '') snap_type, ltrim(coalesce(class, snap_class), '0') cls,
      year(coalesce(start_date, premise_first_start, lamp_original_date)) yr
    from '{SLA}' where on_premises""").df()
    # class -> type from rows that carry both (LAMP rows lack snap_type)
    cls_type = (lic[lic.snap_type.ne("")].groupby("cls").snap_type
                .agg(lambda s: s.value_counts().index[0]))
    lic["ltype"] = lic.snap_type.where(lic.snap_type.ne(""), lic.cls.map(cls_type))
    lic["level"] = lic.ltype.map(LEVEL).fillna(0).astype(int)
    parts = lic["addr"].fillna("").str.extract(r"^\s*([0-9][0-9A-Z/ -]*?)\s+(.*)$")
    src = pd.DataFrame({"id": lic.serial, "name": lic.name, "house": parts[0], "street": parts[1],
                        "zip": lic.zip.astype("string").str[:5], "lat": lic.lat, "lon": lic.lon,
                        "year": lic.yr})
    m = match(src)
    m = m.merge(lic[["serial", "level", "ltype"]], left_on="id", right_on="serial")
    print(f"SLA on-premises licenses matched to a CAMIS: {m.id.nunique():,}/{len(lic):,} "
          f"({m.id.nunique() / len(lic):.0%})")
    return m.groupby("camis").agg(liquor_level=("level", "max"), n_licenses=("id", "nunique")).reset_index()


def osm_fastfood() -> pd.DataFrame:
    c = con()
    osm = c.execute(f"""select source_id id, name, lat, lon, category_raw,
        json_extract_string(extra, '$.brand') brand from '{OSM}' where name is not null""").df()
    src = osm.assign(house=None, street=None, zip=None)
    m = match(src, geocode=False).merge(osm[["id", "category_raw", "brand"]], on="id")
    m["osm_fast_food"] = m.category_raw.str.contains("fast_food", na=False)
    return m.groupby("camis").agg(osm_fast_food=("osm_fast_food", "max"),
                                  osm_brand=("brand", "first")).reset_index()


def build() -> pd.DataFrame:
    base = camis_base()
    c = con()
    c.register("b", base)
    base["nname"] = c.execute("select nn(dba) from b").df().iloc[:, 0].values
    base["chain_n"] = base.groupby("nname").camis.transform("nunique").where(base.nname.ne(""), 1)
    sla = sla_levels()
    osm = osm_fastfood()
    df = base.merge(sla, on="camis", how="left").merge(osm, on="camis", how="left")
    df["liquor_level"] = df.liquor_level.fillna(0).astype(int)
    df["liquor"] = df.liquor_level.map(LEVEL_NAME)
    name_u = df.dba.fillna("").str.upper().str.replace(r"[^A-Z0-9 ]", "", regex=True)
    df["qsr_brand"] = name_u.str.contains(QSR_BRANDS, regex=True) | df.osm_brand.notna() & df.chain_n.ge(3)
    df["fast_food"] = (df.cuisine.isin(QSR_CUISINES) | df.qsr_brand | df.osm_fast_food.fillna(False).astype(bool))
    df["chain"] = df.chain_n.ge(3)
    df["open_year"] = pd.to_datetime(df.first_insp).dt.year
    cols = ["camis", "dba", "boro", "building", "street", "zipcode", "lat", "lon", "bin", "bbl",
            "cuisine", "first_insp", "last_insp", "open_year", "liquor", "liquor_level", "n_licenses",
            "chain_n", "chain", "qsr_brand", "osm_fast_food", "osm_brand", "fast_food"]
    out = df[cols]
    p = OUT / "camis_proxies.parquet"
    out.to_parquet(p, index=False)
    print(f"wrote {p}: {len(out):,} rows")
    print(out.liquor.value_counts().to_string())
    print(f"chain {out.chain.mean():.1%}  fast_food {out.fast_food.mean():.1%}")
    return out


if __name__ == "__main__":
    build()
