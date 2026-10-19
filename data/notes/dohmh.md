# DOHMH restaurant inspections: historical copies

Status as of 2026-10-18. There are 43 copies in `data/raw/dohmh/`, 1.0 GB in total. Every copy is a gzipped UTF-8 CSV and parses cleanly.

## The problem

Socrata dataset `43nn-pn8j` only holds restaurants that are **active** on the pull date, with about 3 years of inspections per restaurant. Restaurants that close drop out of it. To see closures, we need many old pulls. Each pull's `RECORD DATE` column gives its true pull date.

## Files

- `manifest.csv` has one row per copy:
  - Fetch fields: `id`, `source`, `kind`, `url`, `snapshot_ts`, `member`, `format`.
  - Stats: `snapshot_date` (from RECORD DATE), `bytes_gz`, `rows`, `distinct_camis`, `min_insp_date` / `max_insp_date` (1900-01-01 excluded), `has_latlng` / `has_bbl` / `has_bin`, `columns`, `notes`.
- `<id>.csv.gz` holds each copy. Content is unchanged, with three exceptions:
  - zip and bz2 members are extracted.
  - Socrata `rows.xml` exports are converted to CSV.
  - The 2014 WebExtract files are transcoded from cp1252 to UTF-8.
- `union_inspections.parquet` has one row per (camis, inspection_date) across all copies. Attributes come from the latest copy containing that inspection. It also records `first_snapshot`, `last_snapshot` and `n_snapshots`.
- `coverage_by_year.csv` holds the table below.
- `wayback_candidates.csv` is the CDX enumeration result.

## Pipeline

| Script | What it does |
|---|---|
| `pipeline/dohmh_wayback.py` | Runs CDX over every URL variant, keeps large captures, picks one per 14-day window (CSV preferred over JSON or XML). |
| `pipeline/dohmh_sources.py` | Merges the Wayback candidates with the curated non-Wayback list into `manifest.csv`, keeping existing stats. |
| `pipeline/fetch_dohmh.py [id ...]` | Downloads missing files only. Runs sequentially, retries with backoff, waits 4 s between requests. |
| `pipeline/dohmh_profile.py` | Fills the manifest stats, builds the union, prints coverage and gaps. |

The `cran_mdsr_20160106` copy needs the pure-python `rdata` package. It is not in `.venv`. I fetched it with a scratch venv: `pip install rdata requests`.

**Wayback quirk:** many `https://…id_/` captures 302-loop between neighbouring timestamps. Requesting the `http://` spelling of the original URL plays the capture back. The fetcher tries both spellings, then plain replay, and rejects any redirect to a different timestamp.

## Copies (pull date, distinct CAMIS)

**Pre-2015.** These are old DOH "WebExtract" files: boro and cuisine are codes, and there is no inspection type.
- 2014-05-29 (25,160): GitHub sonyakc
- 2014-08-28 (25,192): GitHub spkal, the BigApps zip with lookup tables

**2015–2017.**
- 2015-09-07: Wayback
- 2016-01-06: CRAN `mdsr` 0.1.3, `Violations.rda`
- 2016-04-07: GitHub Hyeramoon
- 2016-12-09, 2017-01-15, 2017-04-21: Wayback
- 2017-08-28: Kaggle new-york-city/nyc-inspections

**The old Wayback gap (2017-04 to 2020-11), now partly filled.**
- 2018-07-27: archive.org data.world backup
- 2018-11-20: GitHub jlxu07517
- 2019-05-12: Kaggle new-york-city/ny-department-of-health-and-mental-hygiene v1
- 2019-10-06, 2019-11-24, 2019-12-27: the same Kaggle dataset, v2, v9 and v16
- 2020-01-03: Kaggle yekahaaagayeham
- 2020-06-05: Kaggle kylewbrown. This copy has only 22k CAMIS and its last inspection is 2020-03-16.

**The old 2021-05 to 2022-06 gap.**
- 2021-09-30: GitHub kawczy83 (bz2)
- 2022-03-23: Kaggle minisam

**2020-11 onward.** 26 Wayback copies: 2020-11, 2021-05, 2022-06, 2022-11, then every 1–5 months to 2026-04, plus a live pull on 2026-10-16. Three of these are XML exports: 2024-03, 2025-06 and 2025-12.

Lat/lng, BBL and BIN are present only in copies from 2019-10 onward. 20,277 CAMIS were last seen before 2019-10 and have **addresses only**, so they need geocoding. CharlesFainLehman/nyc-cuisine-atlas on GitHub commits a Census-geocoder cache for pre-2020 restaurants that may help.

## Union coverage

There are **76,395 distinct CAMIS** in the union. The live dataset alone has 31,554, and nyc-cuisine-atlas, which uses Wayback only, had about 63k.

| year | CAMIS inspected | inspection-days |
|---|---|---|
| 2010 | 1,900 | 2,625 |
| 2011 | 14,925 | 40,405 |
| 2012 | 18,408 | 46,171 |
| 2013 | 22,252 | 55,202 |
| 2014 | 25,343 | 57,567 |
| 2015 | 24,535 | 53,380 |
| 2016 | 24,624 | 45,592 |
| 2017 | 23,676 | 40,364 |
| 2018 | 25,798 | 52,072 |
| 2019 | 25,921 | 51,686 |
| 2020 | 8,849 | 10,143 |
| 2021 | 6,667 | 7,738 |
| 2022 | 20,935 | 27,765 |
| 2023 | 20,269 | 25,169 |
| 2024 | 21,043 | 27,293 |
| 2025 | 19,417 | 26,798 |
| 2026 | 17,657 | 22,455 |

How to read the edges and the dip:
- **2010–2011 are partial.** The earliest copy is from 2014-05, and copies keep only about 3 years of history.
- **2020–2021 is real, not missing data.** Inspections stopped in mid-March 2020 and did not resume at scale until July 2021. Monthly counts from 2020-04 to 2021-06 are in single or double digits. Inspection activity cannot date closures in that window.
- **2022 onward is about 20k a year** against about 25k a year in 2018–19. This looks like a lower post-COVID inspection frequency, not missing restaurants, because copies there are dense.

## Remaining gaps

These are the longest stretches between consecutive pulls. A restaurant that opened and closed entirely inside one is invisible.
- **375 d, 2014-08-28 → 2015-09-07: largest, unfilled.**
- **333 d, 2017-08-28 → 2018-07-27: unfilled.**
- 246 d, 2016-04-07 → 2016-12-09
- 205 d, 2020-11-05 → 2021-05-29. This one is mostly harmless because no inspections took place.
- 197 d, 2026-04-02 → 2026-10-16
- 174 d, 2021-09-30 → 2022-03-23
- 173 d, 2018-11-20 → 2019-05-12

Everything else is 162 days or less. Nothing exists before 2014-05, so restaurants that closed before about 2011 are absent.

## What I tried

**Wayback CDX** (prefix, status 200, collapsed by digest):
- Every URL variant under `api/views/43nn-pn8j/`: rows.csv, json, xml, tsv, pdf, `bom=true`, `format=true`, cacheBust and other variants.
- `api/geospatial/43nn-pn8j`, `resource/43nn-pn8j*`, `api/odata/v4/43nn-pn8j`, `download/43nn-pn8j`.
- `xx67-kt59` (only RSS and attachments), `nycopendata.socrata.com`.
- Filtered views on the same table: gra9-xbjk, w5cg-9t9b, w3z6-mr9h, 4vkw-7nck, rs6k-p7g6, 59dk-tdhz. None had exports.
- All large `api/views/*` exports captured during the gap windows: 25 IDs, none restaurant data.
- `resource/` captures are 1,000-row pages, so they are useless.
- nyc.gov `html/doh/downloads/{zip,txt,csv}` and `assets/doh/downloads`.
- The NYC DataMine `raw.js`, which names `dohmh_restaurant-inspections_001.zip`. It was never archived.
- a816-health ABC Eats and a816-restaurantinspection, which only have per-restaurant pages.

**Elsewhere:**
- Kaggle API search; 6 datasets used. Others are near-duplicates, kept out as redundant: sdawar 2020-12 and 2021-04, estebanprez 2021-05, shivanielakurthy 2021-10, prajwalsyallur, and Kaggle weekly v3–v15.
- GitHub repo search and tree listing of about 90 repos. Unauthenticated, because `gh` is not installed, so code search was not available. Skipped copies:
  - vaibhavdiyora 2018-07-17, as redundant.
  - bkleyn 2017-07-13, which was edited in Excel.
  - MarinPetel 2020-12, adcm2292 2020-11, Guin-/ickly 2017-03 (partial), MrSnickers 2014-03, mendoncakr 2014 (Excel-mangled), umangkeshri 2017-08 (modified).
- archive.org item search; the data.world NYC agent items were checked.
- CRAN package data; only mdsr has it.
- Hugging Face, Zenodo, Dataverse: nothing.

**Not tried:** authenticated GitHub code search, which is the best remaining lever for the 2014-09…2015-08 and 2017-09…2018-06 gaps. Also BigQuery, openICPSR, figshare and OSF.

## Caveats

- CAMIS is per permit. An ownership change gets a new CAMIS at the same address.
- Old WebExtract copies code boro as 1–5 and cuisine as codes. The lookup tables (`Cuisine.txt`, `Violation.txt`, `Action.txt`) are inside the spkal zip but are not stored here; re-download the zip if needed.
- The mdsr copy has cuisine_code only and float phone numbers.
- Inspection dates of 1900-01-01 mean "not yet inspected". They are excluded from min dates but kept in the union.
- Several copies (2014-05, 2015-09, 2021-09, 2025-12 onward) contain a few inspections dated 2007–2009, which are long-retained records.
