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
| `tlc_taxi_dropoffs` | Yellow + green only (consistent series across 2011–2025). |
| `tlc_night_share`, `tlc_wkdy_eve_share` | Share of dropoffs 8 pm–4 am (any day), or Mon–Fri 5–11 pm. |
| `jobs`, `jobs_km2`, `jobs_food_accom` (CNS18), `jobs_retail` | LODES8 WAC, all jobs. `jobs_year_used` = 2023 for 2024–25. |
| `residents`, `residents_km2` | ACS 5-yr total population (year = end of window). 2025 uses 2024. |
| `citibike_trips_w400` | Citi Bike annualized starts+ends, same 400 m kernel. **Not in the index.** |
| `z_subway`, `z_tlc`, `z_jobs`, `z_residents` | z-score of log1p(component), using the **2019** tract mean/sd. |
| `fti` | Foot traffic index = mean of the four z's. Comparable across years (2020 shows as a drop). |
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
- duckdb reads the CloudFront parquet files remotely; no trips are stored.
- **Sampled:** Jan/Apr/Jul/Oct of each year, scaled ×3 (`annual_scale`). Reading every month in parallel got this machine's IP blocked (HTTP 403) twice. So reads are now sequential with 20 s pauses and 10-minute retries.
- TLC has back-filled zone IDs into the 2011–16 yellow files, so no lat/lon→zone step was needed. Only 2009–10 still have coordinates, and those years are outside the panel.
- Caveats:
  - **The taxi→rideshare shift:** Uber/Lyft appear only from 2015 (FHV) and 2019-02 (HVFHV). So `tlc_dropoffs` before 2015 misses rideshare; use `tlc_taxi_dropoffs` for a consistent series.
  - FHV before 2019 mostly lacks dropoff zones, so pickups stand in for dropoffs (`do_proxy`).
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
