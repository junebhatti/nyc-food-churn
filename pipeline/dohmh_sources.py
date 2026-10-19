"""Build/refresh data/raw/dohmh/manifest.csv from the Wayback candidate list
(pipeline/dohmh_wayback.py output) plus a curated list of non-Wayback copies.
Stats columns already filled in by dohmh_profile.py are preserved.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/dohmh"
MANIFEST = RAW / "manifest.csv"

FETCH_COLS = ["id", "source", "kind", "url", "snapshot_ts", "member", "format"]
STAT_COLS = ["snapshot_date", "bytes_gz", "rows", "distinct_camis", "min_insp_date",
             "max_insp_date", "has_latlng", "has_bbl", "has_bin", "columns", "notes"]

KAGGLE = "https://www.kaggle.com/api/v1/datasets/download/"
GH = "https://raw.githubusercontent.com/"
CSV_MEMBER = r"(?i)restaurant.?inspection.?results.*\.csv$"

# (id, source, url, member regex, format, note). Pull dates come from RECORD DATE.
CURATED = [
    ("gh_spkal_20140828", "GitHub spkal/NYC_Health_Ratings",
     GH + "spkal/NYC_Health_Ratings/HEAD/dohmh_restaurant-inspections_002.zip",
     r"^WebExtract\.txt$", "webextract", "old DOH WebExtract format with lookup tables"),
    ("gh_sonyakc_20140529", "GitHub sonyakc/restaurant_health_rating_csv_parser",
     GH + "sonyakc/restaurant_health_rating_csv_parser/HEAD/WebExtract.txt",
     "", "webextract", "old DOH WebExtract format"),
    ("cran_mdsr_20160106", "CRAN R package mdsr 0.1.3 (data/Violations.rda)",
     "https://cran.r-project.org/src/contrib/Archive/mdsr/mdsr_0.1.3.tar.gz",
     r"data/Violations\.rda$", "rda", "pull 2016-01-06 bundled in textbook package; cuisine_code only"),
    ("gh_hyeramoon_20160407", "GitHub Hyeramoon/Python_project_NYC_restaurant_inspection",
     GH + "Hyeramoon/Python_project_NYC_restaurant_inspection/HEAD/Data/NYCdata.csv.zip",
     r"\.csv$", "csv", ""),
    ("kaggle_nycinspections_20170828", "Kaggle new-york-city/nyc-inspections",
     KAGGLE + "new-york-city/nyc-inspections", r"\.csv$", "csv", ""),
    ("ia_dataworld_20180727", "archive.org item data-world-snapshot-20260713-agent-city-of-ny-part-1-4",
     "https://archive.org/download/data-world-snapshot-20260713-agent-city-of-ny-part-1-4/43nn-pn8j.zip",
     r"(?i)original/.*\.csv$", "csv", "data.world backup of NYC Open Data"),
    ("gh_jlxu_20181120", "GitHub jlxu07517/1001-NYC-Restaurant-Inspection",
     GH + "jlxu07517/1001-NYC-Restaurant-Inspection/HEAD/DOHMH_New_York_City_Restaurant_Inspection_Results.csv.zip",
     r"\.csv$", "csv", ""),
    ("kaggle_nycdohmh_v1_20190512", "Kaggle new-york-city/ny-department-of-health-and-mental-hygiene v1",
     KAGGLE + "new-york-city/ny-department-of-health-and-mental-hygiene?datasetVersionNumber=1",
     CSV_MEMBER, "csv", ""),
    ("kaggle_nycdohmh_v2_20191006", "Kaggle new-york-city/ny-department-of-health-and-mental-hygiene v2",
     KAGGLE + "new-york-city/ny-department-of-health-and-mental-hygiene?datasetVersionNumber=2",
     CSV_MEMBER, "csv", "v2-v16 are weekly pulls 2019-10-06..2019-12-27; only v2, v9, v16 kept"),
    ("kaggle_nycdohmh_v9_20191124", "Kaggle new-york-city/ny-department-of-health-and-mental-hygiene v9",
     KAGGLE + "new-york-city/ny-department-of-health-and-mental-hygiene?datasetVersionNumber=9",
     CSV_MEMBER, "csv", ""),
    ("kaggle_nycdohmh_v16_20191227", "Kaggle new-york-city/ny-department-of-health-and-mental-hygiene v16",
     KAGGLE + "new-york-city/ny-department-of-health-and-mental-hygiene?datasetVersionNumber=16",
     CSV_MEMBER, "csv", ""),
    ("kaggle_yekahaaagayeham_20200103", "Kaggle yekahaaagayeham/dohmh-newyork-city-restaurant-inspection-results",
     KAGGLE + "yekahaaagayeham/dohmh-newyork-city-restaurant-inspection-results", r"\.csv$", "csv", ""),
    ("kaggle_kylewbrown_20200605", "Kaggle kylewbrown/nyc-restauarant-inspections",
     KAGGLE + "kylewbrown/nyc-restauarant-inspections", r"\.csv$", "csv", ""),
    ("gh_kawczy83_20210930", "GitHub kawczy83/NYC_Restaurant_Inspection",
     GH + "kawczy83/NYC_Restaurant_Inspection/HEAD/nyc_inspection.bz2", "", "csv", ""),
    ("kaggle_minisam_20220323", "Kaggle minisam/new-york-city-restaurant-inspection20172021",
     KAGGLE + "minisam/new-york-city-restaurant-inspection20172021", CSV_MEMBER, "csv", ""),
    (f"socrata_live_{date.today():%Y%m%d}", "NYC Open Data live export (43nn-pn8j)",
     "https://data.cityofnewyork.us/api/views/43nn-pn8j/rows.csv?accessType=DOWNLOAD",
     "", "csv", "live pull"),
]


def main() -> None:
    old = {}
    if MANIFEST.exists():
        with MANIFEST.open() as fh:
            old = {r["id"]: r for r in csv.DictReader(fh)}
    rows = []
    with (RAW / "wayback_candidates.csv").open() as fh:
        for c in csv.DictReader(fh):
            rows.append({"id": f"wayback_{c['timestamp'][:8]}_{c['format']}",
                         "source": "Wayback Machine", "kind": "wayback", "url": c["url"],
                         "snapshot_ts": c["timestamp"], "member": "", "format": c["format"]})
    for cid, src, url, member, fmt, note in CURATED:
        rows.append({"id": cid, "source": src, "kind": "http", "url": url, "snapshot_ts": "",
                     "member": member, "format": fmt, "notes": note})
    # keep any previously-recorded live pulls even though today's id differs
    ids = {r["id"] for r in rows}
    rows += [r for k, r in old.items() if k.startswith("socrata_live_") and k not in ids]
    # keep rows registered by dohmh_extra.py (copies stored under extra/)
    extra = [r for k, r in old.items() if k.startswith("extra/") and k not in ids]
    for r in rows:
        prev = old.get(r["id"], {})
        for c in STAT_COLS:
            r[c] = prev.get(c) or r.get(c, "")
    rows.sort(key=lambda r: r["id"].split("_")[-1] if r["kind"] == "http" else r["snapshot_ts"][:8])
    rows += extra
    with MANIFEST.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FETCH_COLS + STAT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {MANIFEST}")


if __name__ == "__main__":
    main()
