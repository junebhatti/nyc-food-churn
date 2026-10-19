# Foot traffic (subway, taxi/FHV, jobs, residents, Citi Bike, pedestrian counts)

Reproduce: `.venv/bin/python pipeline/fetch_traffic.py [lodes acs ped subway tlc citibike bid build]`.
Outputs are in `data/raw/traffic/`; `manifest.json` lists rows and fields. Monthly API/TLC
results are cached in `_tmp/` so reruns resume (delete `_tmp/` to refetch). The slow steps are
`subway` (Socrata, ~2 h) and `tlc` (CloudFront throttling, see below).

## Main product: `traffic_by_tract_year.parquet`
One row per 2020 tract (`geoid`, 2,325) x year 2011–2025. Components:

| column | definition |
|---|---|
| `subway_entries_w400` | Annual subway entries, distance-weighted: for each PLUTO lot, sum over station complexes of entries x max(0, 1 − d/400 m); then the mean over the tract's lots (tracts with no lots use a representative point). |
| `subway_eve_entries_w400` | Same, using weekday 5–11 pm entries only. |
| `subway_nearest_m_mean` | Mean lot distance to the nearest complex (static). |
| `tlc_dropoffs`, `tlc_dropoffs_km2` | Yellow + green + FHV + HVFHV dropoffs per year (4 sampled months × 3), allocated from taxi zone to tract by area share; airport zones (EWR, JFK, LGA) excluded. |
| `tlc_taxi_dropoffs` | Yellow + green only (the most consistent series; green has no files before 2014, it began 2013-08). |
| `tlc_night_share`, `tlc_wkdy_eve_share` | Share of dropoffs 8 pm–4 am (any day), or Mon–Fri 5–11 pm. |
| `jobs`, `jobs_km2`, `jobs_food_accom` (CNS18), `jobs_retail` | LODES8 WAC, all jobs. `jobs_year_used` = 2023 for 2024–25. |
| `residents`, `residents_km2` | ACS 5-yr total population (year = end of window). 2025 uses 2024. |
| `citibike_trips_w400` | Citi Bike annualized starts+ends, same 400 m kernel. **Not in the index.** |
| `z_subway`, `z_tlc`, `z_jobs`, `z_residents` | z-score of log1p(component), using the **2019** tract mean/sd. |
| `fti` | Foot traffic index = mean of the four z's. Comparable across years from 2019 on (2020 shows as a drop). Before 2019 `z_tlc` is pulled down by missing rideshare coverage (no FHV before 2015, partial 2015–18): the citywide mean of `z_tlc` is −1.9 in 2011 vs 0 in 2019, mostly a coverage artifact. For pre-2019 comparisons use `fti_within_year`. |
| `fti_within_year` | Same, with z-scores taken within each year (purely cross-sectional rank). |
| `fti_pctile` | Percentile of `fti` within the year. |

Per km² uses the tract polygon area; tracts are clipped to the shoreline, so this is close to
land area. The weights are equal and deliberately simple. For survival models, enter the
components separately (or `fti_within_year`) as well as the composite.

**Building-level helper:** `pipeline/traffic_access.py: station_access(lats, lons, year=None)`
returns the nearest complex, its distance, its entries that year (default: 2017–19 mean), and
the 400 m kernel sum. `subway_access_lot.parquet` precomputes the nearest complex and distance
for every BBL; join it to `subway_station_year` to get entries by year.

## Components and their caveats
**Subway (`subway_station_year`: 428 complexes x 2011–2026).**
- 2017+: hourly ridership (data.ny.gov t69i-h2me, wujg-7c2s, 5wq4-mkjj), summed on the server in 7-day chunks (whole-month queries time out). `subway_hourly_profile` keeps complex x month x dow x hour.
- 2011–16: MetroCard History (v7qc-gwpn), weekly swipes per remote unit. These are turnstile entries without the counter differencing.
  - Remote units are mapped to complexes by fuzzy name and route matching, plus 13 hand overrides (`subway_remote_complex_map`).
  - Each complex is scaled by its own hourly/MetroCard ratio on 2017–18 (median 1.13, IQR 1.09–1.20).
- Totals match MTA's published figures: 2015 1.79B, 2019 1.70B, 2020 0.64B, 2023 1.16B, 2025 1.30B.
- Weekday-evening share before 2017 comes from turnstile audits.
  - Sample: 4 weeks a year, with counters differenced and outliers dropped (see `traffic_turnstile.py`).
  - 2014–19 come from data.ny.gov. 2011–13 come from MTA's retired weekly files on the Wayback Machine; some captures are truncated, so the largest one is used.
  - Calibrated per complex on 2017–19: the raw and true shares correlate at 0.99.
- Caveats:
  - The 2020 collapse (−62%) and partial recovery (2025 is still −23% vs 2019).
  - OMNY is included in the hourly data but not in MetroCard History, which doesn't matter before 2019.
  - Complex coordinates are a single point, so big complexes like Times Sq or Fulton look farther away from some lots than they are.
  - Turnstile data ends in 2022 (not needed here).
  - Fare evasion is not counted (it rose sharply after 2020).
  - Briarwood has no MetroCard remote mapped (2011–16 missing). 2.3% of swipes sit on unmapped remotes: PATH, AirTrain, tram before the override.

**TLC (`tlc_zone_year`, `tlc_zone_tract_weights`).**
- Sources by period:
  - Yellow 2011–18, green 2014–18, FHV 2015–18: CloudFront parquet, read remotely with duckdb (no trips stored).
  - Yellow, green and HVFHV 2019+: TLC's monthly zone counts on NYC Open Data (c5iv-bn4s), every month.
  - Yellow's evening/night shares come from the parquet samples in every year.
- **Sampled:** Jan/Apr/Jul/Oct of each year, scaled ×3. Reading every month in parallel got this machine's IP blocked (HTTP 403) twice, so reads are sequential with 20 s pauses.
- **Missing files:** CloudFront answers 403 both for a missing file and when it throttles. `_month_retry` HEADs the file and a known-good file: 403/404 while the known file loads means "not published", so the month is logged and skipped. Anything else (block, 5xx, timeout, reset) is retried at most 4 times (5, 10, 15 min), then it fails loudly. duckdb also has `http_timeout=120`.
- **Missing for good:** green 2013 (service began 2013-08; TLC's green files start 2014-01, so 2013-08…12 all return 403). All other sampled months 2011–2026-07 exist. HVFHV files start 2019-02 (2019-01 is in c5iv-bn4s).
- TLC has back-filled zone IDs into the 2011–16 yellow files, so no lat/lon→zone step was needed. Only 2009–10 still have coordinates, and those years are outside the panel.
- Caveats:
  - **The taxi→rideshare shift:** Uber/Lyft appear only from 2015 (FHV) and 2019-02 (HVFHV). So `tlc_dropoffs` before 2015 misses rideshare; use `tlc_taxi_dropoffs` for a consistent series.
  - FHV 2015–18 files hold Uber/Lyft/Via under their base numbers but have no company field, so there is no Uber/Lyft split before HVFHV (2019-02). Dropoff zones are mostly blank, so pickups stand in for dropoffs (`do_proxy`).
  - Not covered: non-high-volume FHV 2019+ (black cars, liveries; a few %), hourly shares for HVFHV and for green 2019+ (night/evening shares use yellow, green ≤2018 and FHV ≤2018).
  - Annual totals (M dropoffs): yellow 171 (2011) → 84 (2019) → 48 (2025); FHV 220 (2018); HVFHV 249 (2019), 233 (2025).
  - Area allocation spreads a zone's dropoffs evenly over its tracts.
  - The Manhattan congestion charge (2025-01) adds a 2025 shift.

**LODES8 WAC 2010–2023** (`lodes_wac_tract_year`): 2020 blocks for all years, so no crosswalk is needed. Caveats:
- Jobs are counted where the employer reports them. HQ effects inflate some Midtown tracts.
- Remote work since 2020 means jobs ≠ people present.
- 2024–25 are carried forward.

**ACS 5-yr pop 2011–2024** (`acs_pop_tract_year`):
- The Census API now needs a key, so this reads the bulk summary files instead.
- Windows ending 2011–19 are on 2010 tracts, split to 2020 tracts by land-area share (`geo_basis`).
- 5-year windows smooth out short-run change.

**Citi Bike** (`citibike_station_year`, 2013–2026):
- May + Oct sampled and annualized. This overstates annual totals by about 20–25%.
- Starts and ends are summed, so each trip counts twice.
- Kept out of the index because the system grew from 330 to about 2,400 docks: zeros mean "no dock yet", not "no people".

**Point series (not in the index):**
- `dot_ped_biannual`: DOT Bi-Annual counts, 114 locations, 2007–2026. Weekday AM/midday/PM counts each spring and fall. 2019 has only 150 rows and 2020 is partial.
- `dot_counters_year`: automated counters per sensor/mode/year: 9 pedestrian, 37 bike, 1 scooter, 2012–26, plus the Brooklyn Bridge 2017–19 demo. Check `coverage`; some sensors appear twice with identical counts.
- `bid_ped_counts`, from BID PDFs (text layer; older reports via Wayback):
  - Garment District Alliance: weekly/daily camera counts, 2016–2026, 161 weeks.
  - Grand Central Partnership: monthly, 9–11 counters, 2018-11 → 2022-08.
  - Times Square Alliance: monthly average daily pedestrians, 2022-05 → 2026-08. A method change in 2024 likely creates a break.
- Nothing machine-readable was found for these BIDs:
  - Flatiron/NoMad and 34th St: PDFs whose charts and tables don't parse.
  - Downtown Alliance: image PDFs.
  - Union Sq, Bryant Park, Hudson Yards, Lincoln Sq, Meatpacking, DUMBO, Downtown Brooklyn, Hudson Sq, Fulton Mall: no data at all.

## Paid / restricted (not pulled)
- **Placer.ai:** POI and area visits, 2017+. Custom pricing (one public contract was about $52k/yr). No academic program.
- **Advan (ex-SafeGraph Patterns) via Dewey:** monthly/weekly visits per POI, about 2019+. Free if your university licenses Dewey.
- **SafeGraph's free COVID-era releases** (Weekly Patterns, Social Distancing Metrics 2019–21): the program has ended and no public archive was found.
- **Unacast:** about $38k/yr. **Replica:** sold to agencies. **StreetLight:** discounted academic licences.
- **Free and coarse:** Google Community Mobility, county-level daily, 2020-02 → 2022-10 (gstatic.com/covid19/mobility/). Apple Mobility Trends has been taken down; only mirrors remain.

## Status (2026-10-19): done
All outputs are built, including `tlc_zone_year`, `tlc_zone_tract_weights` and `traffic_by_tract_year` (2,325 tracts × 2011–2025, no missing z's).
- **Green 2013-10 loop:** the file doesn't exist (all of green 2013 returns 403). The old retry loop treated every HTTP error as transient. Fixed as described under TLC above.
- **FHV Socrata hang:** dataset am94-epxh (2018) is still valid. But the server-side group-by takes ~70 s for one week of 2018, a month times out (>120 s), and the whole-year query never returned (the old 600 s read timeout × 4 tries looked like a hang). FHV 2015–18 now comes from the CloudFront FHV parquet files (same quarterly sampling as yellow); `fhv_pickups()` is removed.
- **Sanity check:** the 2019 top 10 are all Midtown/Times Square, Flatiron, Murray Hill-Kips Bay, Turtle Bay and FiDi. The best Downtown Brooklyn tract ranks #65.
