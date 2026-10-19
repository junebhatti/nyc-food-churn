# Official-statistics benchmark (CBP/ZBP, QCEW, BDS, BED, Nonemployer)

Status 2026-10-18. Computed on the union as rebuilt at 22:11: 85,237 CAMIS, 881 of them synthetic. Reproduce with `BENCH_DL=<scratch dir> .venv/bin/python pipeline/fetch_benchmarks.py` (`fetch`, `compare` or `all`). Fetching takes about 12 minutes; `compare` takes about 2 seconds. Outputs are in `data/raw/benchmarks/` (about 0.6 MB). Source zips are deleted after filtering.

## Sources pulled

| file | source | coverage |
|---|---|---|
| `cbp_county_nyc.parquet` | Census CBP county files (`cbpYYco.zip`, www2.census.gov) | 2010–2023, 5 counties, NAICS 72/722/7221/7222/7224/7225/6-digit 7225x, 311811, 445291/445298 |
| `zbp_detail_nyc.parquet` | ZBP detail (`zbpYYdetail.zip`), establishments plus size-class counts | 2010–2023, 302 NYC ZIPs |
| `qcew_nyc_quarterly.parquet` | BLS QCEW: CSV slice API for 2014+, plus member range-reads of `YYYY_qtrly_by_area.zip` for 2010–13 | 2010Q1–2026Q1, own 1/5, 722, 7225, 6-digit, 7224, 311811, 445291 |
| `bds_*.parquet` | Census BDS 2023 release: county×sector, state×sector, US×sector, NY-metro×sector, US NAICS4 (`vcn4`) | 2005–2023 |
| `bed_openings_closings.parquet` | BLS BED via public API v1 (no key): openings (03) and closings (06), rates and levels, SA | 2010Q1–2025Q4 |
| `nonemp_county_nyc.parquet` | Census Nonemployer county files | 2010–2024 **except 2017** |

Release and access notes:
- **Census Data API needs a key now.** Every keyless call 302s to `missing_key.html`. Nothing here uses the API; the bulk files need no key.
- **Latest releases.** CBP/ZBP 2024 have not been released (404). BDS stops at 2023.
- **Nonemployer 2017 is missing.** census.gov's WAF answers `nonemp17co.zip` with a 200 "Request Rejected" HTML page, every time. `download()` validates the zip and logs the skip.
- **BED series IDs.** The format is BD+S+area(10)+industry(6)+…; `bed_series.json` lists them. Industry `300722` is NAICS 722, which is national only. States only have supersectors, so NY uses `200070`, leisure and hospitality. BLS flat files (download.bls.gov) return 403 to scripts.
- **NYS DOL QCEW was not pulled.** It is the same QCEW microdata, and BLS already gives county × 6-digit NAICS.

## Definitional differences (read before using the ratios)

- **CBP/ZBP** counts *employer* establishments as of the March-12 pay period. **QCEW** counts UI-covered establishments, a quarterly average. Neither includes nonemployers; NYC has 16–23k food-service nonemployers, mostly in 7223 (vendors and caterers).
- **DOHMH CAMIS** is one per permit. It includes 7223-type places (cafeterias, caterers), delis and cafés with food-service permits (some delis are 4452 in CBP), and permits with no employees. An ownership change gets a new CAMIS. Every chain location counts, same as CBP.
- **QCEW has a step in 2017.** NYC 7225 jumps from 18.2k to 21.0k (+15%) between 2016 and 2017, a break CBP does not show. Treat `cov_qcew` across 2016/17 with care.
- **"Active in year Y"** follows the spec: start ≤ Dec 31 and last seen ≥ Jan 1. Start is the first real inspection or the first snapshot; last seen is the last snapshot containing the CAMIS. It counts everything open at any point in the year, so it exceeds a point stock by roughly the churn. `cov_cbp_pt` uses a point stock on Mar 12 instead, which matches the CBP reference date. That stock uses `end_mid`, the midpoint between the last sighting and the next full copy (PARTIAL/DERIVED copies ignored).

## Coverage: DOHMH real CAMIS active in year ÷ CBP (7225+7224)

(`compare_borough_year.csv`; 881 synthetic `X` ids excluded; borough from `boro`, else the ZIP prefix)

| yr | BX | BK | MN | QN | SI | NYC | NYC pt-stock | ÷QCEW |
|---|---|---|---|---|---|---|---|---|
| 2012 | 1.58 | 1.42 | 1.23 | 1.43 | 1.45 | 1.36 | 1.19 | 1.48 |
| 2014 | 1.61 | 1.41 | 1.31 | 1.41 | 1.44 | 1.38 | 1.20 | 1.50 |
| 2016 | 1.55 | 1.34 | 1.34 | 1.38 | 1.37 | 1.37 | 1.15 | 1.52 |
| 2017 | 1.48 | 1.28 | 1.29 | 1.34 | 1.33 | 1.31 | 1.13 | 1.32 |
| 2019 | 1.44 | 1.32 | 1.36 | 1.34 | 1.30 | 1.35 | 1.15 | 1.38 |
| 2021 | 1.55 | 1.40 | 1.46 | 1.45 | 1.42 | 1.45 | 1.30 | 1.45 |
| 2023 | 1.54 | 1.35 | 1.39 | 1.38 | 1.33 | 1.39 | 1.24 | 1.40 |
| 2025 | – | – | – | – | – | – | – | 1.49 |

Every year is in the CSV.

How to read it:
- **No borough-year undercounts.** DOHMH is at least 1.23× CBP everywhere.
- **2017–18 is the weakest stretch: 1.31–1.32, point stock 1.13–1.16, against 1.37–1.38 in 2013–16.** CBP grew faster than the DOHMH stock there, partly through 722515 snack/coffee (2.0k → 3.1k). Short-lived CAMIS may also have been lost in the 2016-04 → 09, 2017-10 → 2018-02 and 2018-11 → 2019-05 gaps, each more than 110 days. The 22:11 union rebuild already lifted 2019 from 1.31 to 1.35 and 2023 from 1.35 to 1.39.
- **2020–22 are inflated.** COVID closures stayed on the DOHMH list with no inspections and were purged later.
- **The Bronx runs highest (about 1.5).** It has many small delis and takeout places with few employees.

**SLA bars.** The SLA `bar_tavern` premises count is 1.6–1.75× CBP 7224 from 2015 onward. Before 2015 it is undercounted, because SLA end and start dates are only reliable from 2015/2017 onward (see gov.md). Many bars hold restaurant-class licenses, and CBP codes bars that serve food as 7225, so this ratio is not a coverage test.

## ZIP shortfalls (`zip_shortfalls.csv`, `compare_zip_year.parquet`)

DOHMH ≥ ZBP in almost every ZIP. A shortfall is therefore measured against *expected* = ZBP × that borough-year's ratio.
- **A. Persistent low relative coverage, 0.75–0.85×.** These are the dense immigrant restaurant districts: 10002 LES/Chinatown (−157/yr against expected), 10013 Chinatown/Tribeca (−117), 11211 Williamsburg (−83), 11355 Flushing (−66), 10021 UES (raw 0.98, rel 0.75), 11220 Sunset Park, 11106 Astoria, 10463 Kingsbridge. They are the best candidates for missing CAMIS or mis-ZIPped records. Raw ratios are still about 1.0–1.1.
- **B. Year dips below the ZIP's own median, under 0.8×.** These are few: 10039 in 2021–23 (Harlem, 0.63 rel), 10030 in 2020–23, 11426/11427 in 2014, 10471 in 2015. Flagged ZIP-years run 37–50 a year for 2012–16 and 13–20 a year from 2017, so early-year ZIP coverage is less even.
- **C. Zero DOHMH with ZBP ≥ 5.** Only 10166 (the MetLife building ZIP).

## Closure rates (`closure_rates.csv`)

Exit = CAMIS absent from the latest pull, dated by `end_mid`. Denominator = mean of the Jan-1 stocks of Y and Y+1. `exit_rate_adj` excludes re-permits: same name+building+ZIP with a new CAMIS starting within 400 days (6.7k CAMIS).

| | ours raw | ours adj | BDS sector 72, NYC counties | BDS NY metro | BDS US 7225 | BED US 722 (Σ4q closings) |
|---|---|---|---|---|---|---|
| 2013–19 mean exit % | 15.5 | 13.5 | 11.9 (12.2 if lagged 1y) | 11.2 | 8.8 | 14.4 |
| 2013–19 mean entry % | 16.5 | – | 14.3 | – | – | 14.9 (Σ4q openings) |
| 2020–23 mean exit % | 11.4 | 10.3 | 13.6 | | | |

- **Before COVID, our adjusted exit rate is about 1.5 pts/yr above BDS.** That is expected, because DOHMH includes nonemployer and very small permits, which churn more. The borough pattern matches (BK/QN highest, MN lowest).
- **Single years swing widely.** 2014 is 18.6 and 2015 is 10.4. Those swings come from purge batches and the copy gaps. Use rates pooled over 2–3 years.
- **2012 (3.4%) is not usable.** It is left-censored, because copies start in 2012-07.
- **2020 (3.0%) is not usable.** There are no copies or inspections; COVID closures land in 2021–22.
- **For 2020–23, ours undercounts exits by about 3 pts/yr against BDS.** This is the stale-listing problem.
- **BED closings include temporary closures.** A unit goes to zero employment for one quarter, so annual sums overstate permanent exits. Use BDS for levels and BED for 2024–25 direction only.
