"""NYC Open Data: storefront registry, storefront rent stats, outdoor dining, DCWP licenses."""
from __future__ import annotations

import pandas as pd

from gov_common import save, socrata

NYC = "data.cityofnewyork.us"

# DCWP license categories relevant to food/drink businesses
DCWP_HIST_FOOD = ("'SIDEWALK CAFE','CABARET','CATERING'")
DCWP_CUR_FOOD = ("'Stoop Line Stand','Sidewalk Cafe','Catering Establishment','Cabaret'")


def to_num(s: pd.Series) -> pd.Series:
    """'1,234' / '$12.50' / '-' -> float; anything unparseable stays NaN but is counted."""
    clean = s.astype("string").str.replace(r"[,$\s]", "", regex=True).replace("*", pd.NA)  # * = suppressed
    out = pd.to_numeric(clean, errors="coerce")
    bad = clean.notna() & (clean != "") & out.isna()
    if bad.any():
        print(f"    to_num({s.name}): {bad.sum()} unparseable e.g. {clean[bad].unique()[:5].tolist()}")
    return out


def storefronts():
    df = socrata(NYC, "92iy-9c3n")
    save(df, "storefronts_registry", source=NYC, dataset_id="92iy-9c3n",
         date_cols=["filing_due_date", "sold_date", "expir_dt_of_most_recent_lease"],
         note="Class 2/4 storefront registry (LL157), one row per storefront per reporting year.")

    for dsid, name in (("dxru-eun8", "storefront_stats_class24"),
                       ("x3n4-h56k", "storefront_stats_class1")):
        st = socrata(NYC, dsid)
        keep_txt = {"reporting_year", "aggregate_level_citywide", "aggregate_level_id"}
        for c in st.columns:
            if c not in keep_txt:
                st[c] = to_num(st[c])
        save(st, name, source=NYC, dataset_id=dsid, note=(
            "Storefront registration stats by aggregate level (citywide/borough/council district/"
            "census tract...). Text numbers cleaned to float. Rents are $/sq ft per MONTH."))


def outdoor_dining():
    for dsid, name, dates, note in (
        ("pitm-atqc", "open_restaurants_apps", ["time_of_submission"],
         "COVID Open Restaurants applications 2020-2023 (has SLA serial, BBL)."),
        ("qcdj-rwhu", "sidewalk_cafe_hist", ["submit_date", "expiration_date", "app_status_date"],
         "DCWP sidewalk cafe licenses+applications snapshot (pre Dining Out NYC)."),
        ("fpeh-f7ci", "dining_out_nyc", ["license_issue_date", "license_expiration_date"],
         "DOT Dining Out NYC permanent outdoor dining licenses (2024-)."),
        ("d54t-ywim", "open_storefronts_apps", ["submission", "creationda"],
         "Open Storefronts (retail sidewalk) applications 2021."),
        ("w49t-5gha", "mbpo_broadway_vacancy_2020", [], "Manhattan BP Broadway storefront survey 2020."),
    ):
        df = socrata(NYC, dsid)
        df = df.drop(columns=[c for c in ("the_geom",) if c in df])
        save(df, name, source=NYC, dataset_id=dsid, date_cols=dates, note=note)


def dcwp():
    h = socrata(NYC, "m4ph-grrm", where=f"business_code_description in ({DCWP_HIST_FOOD})")
    save(h, "dcwp_hist_licenses_food", source=NYC, dataset_id="m4ph-grrm",
         date_cols=["license_creation_date", "license_expiration_date", "license_status_date"],
         note="DCWP legacy-system licenses (to ~2014): sidewalk cafe, cabaret, catering.")
    ha = socrata(NYC, "vnz6-h2k4", where=f"license_category in ({DCWP_HIST_FOOD})")
    save(ha, "dcwp_hist_license_apps_food", source=NYC, dataset_id="vnz6-h2k4",
         date_cols=["activity_date"], note="DCWP legacy license application activity 1994-2013.")
    cur = socrata(NYC, "w7w3-xahh", where=f"business_category in ({DCWP_CUR_FOOD})")
    save(cur, "dcwp_licenses_food", source=NYC, dataset_id="w7w3-xahh",
         date_cols=["license_creation_date", "lic_expir_dd"],
         note="DCWP issued licenses (all statuses incl. expired/surrendered), food categories.")
    apps = socrata(NYC, "ptev-4hud", where=f"business_category in ({DCWP_CUR_FOOD})")
    save(apps, "dcwp_license_apps_food", source=NYC, dataset_id="ptev-4hud",
         date_cols=["submission_date", "date_closed"], note="DCWP license applications, food cats.")


def run():
    print("== NYC city datasets")
    storefronts()
    outdoor_dining()
    dcwp()


if __name__ == "__main__":
    run()
