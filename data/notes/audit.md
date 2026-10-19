# QA audit, 2026-10-18 (about 21:15 EDT)

Scope: the five finished areas (gov, poi, signals, ratings, dohmh core) were checked against their notes and manifests. The three running areas (dohmh/extra, menus, traffic) got a health check only; nothing of theirs was modified or started.
Audit scripts are in the session scratchpad (`audit/a1.py`, `audit/cnt.py`), not in `pipeline/`.

**Bottom line.** Every finished file opens and parses. Every manifest row count and date range matches the data. No empty, truncated or corrupt files turned up. No fixable failures were found in finished areas, so nothing was rerun or changed. The main follow-ups: a few stale notes, an unnormalized `boro` field in the union, and CAMIS matches that should be redone once the DOHMH gap search finishes.

## 1. Running work

| process (PID) | area | elapsed | state |
|---|---|---|---|
| `menus_wayback cdx()` (11547), `cdx(60)` (19532), `cdx(110)` (19534) | menus | 21 / 14 / 14 min | progressing (new `p*.txt` pages each minute) but hitting many 503/504s |
| `menus_guides cdx zagat` / `cdx nymag` (39448/39450) | menus | 5 min | progressing, 503 backoffs |
| `menus_wayback fetch 0 2` (33968) | menus | 12 min | about 2.2 pages/s, 1,000 of 5,081 done |
| `chain.sh` (16979) | menus | 21 min | waits in a `sleep 30` loop for the next stage (normal) |
| `traffic_subway.hourly_profile` (34550), two `_hourly_month` jobs (44756/44757) | traffic | 7 / 3 min | progressing; `_tmp/hourly_YYYYMM.parquet` written at 21:10 |
| `traffic_bid` gcp collect (46476) | traffic | under 1 min | just started |
| `dw.py` data.world snapshot scan (88225) | dohmh/extra | 49 min | progressing (2,500 items scanned; `dw_hits.tsv` 36 lines) |
| `cc.py` Common Crawl index (88227) | dohmh/extra | 49 min | **effectively stuck**: all 32 queries returned 504 or 502 and none succeeded |
| `dohmh_profile.py` (46969) | dohmh/extra | finished 21:12 | rebuilt `manifest.csv`, `union_inspections.parquet` and `coverage_by_year.csv` |

Recent file changes (all at 21:09–21:11): dohmh/extra (the gh_munk, uncamy and hmason copies), menus (`_wayback/cdx`, `zagat_cdx`, `menupages_parsed.jsonl`), traffic (`_tmp/hourly_*`). Nothing has gone 20 minutes without file changes.

**Concerns and suggested fixes (for the owning agents):**
- **menus: too many concurrent archive.org clients.** Six or seven clients hit archive.org at once: three CDX workers, two guide-CDX workers, a 2-worker fetch, plus the dohmh `dw.py` scan. Most logs show 503 → sleep 10/20/30 s. `cdx_60.log` and `cdx.log` have "page N FAILED this pass", and `cdx_nymag.log` one more. Suggestion: at most 2 concurrent Wayback clients in total. The failed pages are retried on later passes; after the passes, confirm that no `p*.txt` page is missing.
- **dohmh/extra `cc.py`: retry loop with no successes.** Every query got a 504 or 502 (`cc3.log`), which matches the notes ("nearly every request returned 502/504"). Suggestion: kill it, and retry in a single pass only after `index.commoncrawl.org/collinfo.json` responds.
- **dohmh/extra manifest row mismatch.** The manifest says `extra/gh_datacomputing_20141009` has 531,000 rows, but a full parse of the CSV gives 531,420. The other 23 extra copies match.
- **dohmh/extra has rewritten finished outputs.** `union_inspections.parquet` now has 764,937 rows and **85,175 CAMIS**, 881 of them synthetic `X…` ids. `coverage_by_year.csv` changed too: 2010 is now 16,129 CAMIS, against 1,900 in `dohmh.md`. As a result, `dohmh.md` (76,395) and `dohmh_gaps.md` (77,632) are both stale. When it finishes, the agent should update both notes.

**Disk:** 56 GiB free of 460 GiB (87% used). That is above the 15 GB threshold, so OK.

## 2. Finished areas against their notes

### gov: OK
- All 28 manifest entries exist and parse.
- Rows match exactly. Every date range and non-null count in `date_range` matches. The GeoJSON feature counts match (76 / 5 / 2,325 / 262).
- Notes claims recomputed, all matching:
  - `sla_licenses_nyc`: 58,898 rows; 31,824 on-premises; on-premises with a non-LAMP start date 19,450; on-premises end dates 19,346.
  - Storefront "FOOD SERVICES": 55,474.
  - `dof_commercial_values`: FY2011–19 and FY2023–27, with no FY2020–22.
  - `pluto_slim`: 858,284 lots with unique BBLs.
  - REBNY: 264 rows, 2010–2025.
- All gzips pass `gzip -t`, `pad.zip` passes `testzip`, and all 15 REBNY PDFs pass `pdfinfo`.
- Minor items:
  - `sla_licenses_nyc`: 1 row has a null serial. 93 of 54,239 geocoded rows fall outside the NYC bounding box.
  - `storefronts_registry` includes a partial 2026 reporting year (2,038 rows); the notes say "–2025".
  - `dcwp_licenses_food.license_creation_date` has a 1900-12-31 placeholder.
  - REBNY 2025 has 13 of 17 corridors; 2023–24 have 16.
  - No future dates were found.

### signals: OK
- All 8 manifest files match on rows and on event_date min and max.
- The derived files open: `camis_bbl` 67,066 rows, `closure_tightening` 38,696 (matches the notes' n), `_dos_formations_nyc` 2.68M.
- BBL fill rates match the notes table: 92.4 / 99.8 / 99.9 / 93.9 / 94.8 / 91.0 / 89.9%.
- Every non-null lat/lon is inside NYC. No future dates. No duplicates on (source_id, event_type, event_date), except 1 in `nys_dos_entities`.
- PPP: 26,970 loans approved, matching the notes' "27k".
- Minor: the notes table gives `dob_bis_food` dates as "2000 → 2021", but there are about 660 rows from 2022–2026, and the manifest correctly says 2026-10-14.
- The logs (`city.log`, `state.log`, `eval.log`) contain no errors.

### poi: OK
- All 34 parquets open.
- Counts match the notes: fsq_all 133,799 (64k restaurants / 22k bars / 10k cafés / 10k bakeries / 27k other), overture_2026-09-23.0 65,645, overture_all 91,209, osm_overpass 24,011, osm_ohsome 33,639.
- FSQ `date_closed` count is 35,963 (notes: 35.9k).
- 100% of coordinates are inside the NYC bounding box. No duplicate `source_id` in fsq_all or overture_all.
- Minor: there are 25 per-release Overture files, while the notes say "24 releases kept". `overture_2026-09-23.1` has the same 65,645 ids as `.0`, so it is a redundant patch release.

### ratings: OK
- All 7 parquets open, and row counts match the notes: 2,460 / 4,283 / 129 / 539 / 3,120 / 35,148 / 219,312.
- Recomputed matches agree with the notes:
  - Michelin: 224 starred venues, 75.9% CAMIS-matched (79.7% for those starred 2012 or later).
  - NYT: 87.8%. Google Local: 58.4%.
  - Eater 38: 83%; NYC 77%; Brooklyn 82.5% (notes: 78%); Queens 70.6% (notes: 69%).
  - Google states: 6,116 permanently closed and 1,035 temporarily closed; 22,173 prices; 8.57M reviews.
- Minor:
  - Awards are 96.5% matched for 50 Best and 93.2% for JBF, by row; the notes give 88% / 92%, probably per venue.
  - The snapshot file has 519 distinct names; the notes say 507 venues (name variants).
  - Google `first_review` goes back to 1990 (outliers); the notes say 2002.

### dohmh (core 43 copies): OK
- Each of the 43 copies was parsed in full with Python's `csv` module. Every one matches `manifest.csv` exactly, with 0 ragged rows. (DuckDB's parallel reader rejects 10 of them because of multiline quoted fields. That is a reader limitation, not file damage: use pandas or `read_csv(..., parallel=false)`.)
- `fetch_dohmh.py` with no arguments ran a clean skip pass: 68 of 68 skipped.
- Union quality (the current 85k-CAMIS version):
  - No duplicate (camis, inspection_date) pairs. No future dates. Max date 2026-10-15.
  - 43,320 rows dated 1900-01-01, as documented.
  - 41% of rows have lat/lon; 4,254 of them are (0,0) placeholders.
  - 35% of CAMIS (29.9k) have no coordinates and 34% have no BBL, so geocoding is needed (as documented).
  - **`boro` is not normalized.** It mixes `Manhattan` / `MANHATTAN` / `1`, plus `0`, `Missing` and 26k nulls. Normalize it before any borough grouping.
- Stale note: `dohmh.md` says `rdata` is missing from `.venv`. It is installed now (`import rdata` works).

## 3. Failures found in logs and notes

There are no finished-area log errors and no `.part` or temp leftovers. `dohmh/_tmp` is empty. Every failure that the finished-area notes record falls in class (b), not fixable by us:
- NYSLA retired liquor datasets: private (HTTP 403). opengovny: 403. Bars that opened and closed in 2011–14 need a FOIL request.
- Commercial Rent Tax by area, lot-level income and expense data, BID storefront surveys: not published. CBRE: behind registration.
- FSQ releases after 2025-02: gated. The user must accept the terms and add `HF_TOKEN`.
- Missing Overture releases (2024-04..07, 2025-07/08, 2026-06/07): no longer mirrored.
- Yelp Open Dataset: no NYC. Google Places, SafeGraph/Advan, Data Axle: paid or not storable.
- NYT stars: paywalled. Article Search needs the user's API key. Tripadvisor, Yelp, Google and Foursquare APIs: paid or restricted by terms. OpenTable: partners only. Resy, Beli, Infatuation: terms forbid scraping.
- DOHMH before 2014-05: nothing exists. grep.app: bot wall (not bypassed). The authenticated GitHub code search lever needs `gh`, which is not installed. This belongs to dohmh/extra, the running agent.

Class (a) items exist only in the running dohmh/extra area: Common Crawl 502/504 and the Zenodo API error are transient, and are left to that agent (see section 1).

## 4. Reproducibility
- Every module behind the finished areas imports cleanly in `.venv`. That is 31 modules (fetch_*, gov_*, poi_*, signals_*, ratings_*, dohmh_*).
- Documented step names match the code:
  - `fetch_gov.py`: sla, city, dof, geo, geocode, rebny, geocode_eval.
  - `fetch_poi.py`: fsq, overture, osm, ohsome, combine.
  - `fetch_ratings.py`: michelin, guide, awards, nyt, eater, google.
  - `fetch_signals.py`: 311, dob_bis, dob_now, open_rest_insp, nycba, ppp, rrf, dos.
  - `pdftotext` is present for rebny.
- Caveat: only `fetch_dohmh.py` and a few sub-steps (the SLA Wayback cache, PAD, REBNY PDFs, FSQ, DOS cache, Google Local) skip existing files. The gov, signals, ratings and Overture/OSM pulls **re-download and overwrite**, and their live sources will give different counts. Don't rerun them casually; snapshot first if exact reproduction matters.
- Dependency to watch: ratings (`ratings_common` matches against `union_inspections.parquet`) and signals (`camis_bbl`, `closure_tightening`) were built against the 76k-CAMIS union. Rerun the CAMIS matching (`signals_eval.py`, and the ratings match steps) after dohmh/extra finishes.
