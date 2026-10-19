# Analysis inputs (readiness check, 2026-10-18)

Outputs: `data/raw/analysis_inputs/` (125 MB, `manifest.json`, `readiness_coverage.csv`).
Run: `.venv/bin/python pipeline/fetch_analysis_inputs.py`. Cleaning rules live in the `pipeline/ai_*.py` docstrings.
(Written from the agent's report; its own write of this file was blocked.)

## Readiness
| Analysis | Variable | Coverage | Source |
|---|---|---|---|
| all | survival / opening date / NTA | 100 / 87.6 / 97.1% | DOHMH union; local geocoder raised BBL from 65% to 98% |
| A | cuisine family (22 + other) | 86.1% | official DOHMH code list + a second numbering system decoded from the data |
| A | price tier: any / observed | 91 / 17.8% | menus area (mostly estimated) |
| A | chain vs independent | 98.2% (19% chains) | Wikipedia chain lists + NYC brands with 3+ concurrent locations |
| A | first-time vs multi-unit operator | 40.2% (legal entity found: 30%) | entity names from SLA, Open Restaurants, PPP, RRF, DCWP; shared DOS filing addresses |
| A | prior tenants / predecessor lifespan and gap | 99.4 / 41.2% | DOHMH history at the same address (visible from ~2011) |
| A | registry vacancy before opening | 39.6% of 2020+ openings | storefront registry |
| A | age: exact / earlier bound for pre-2011 | 63.8 / 17.7% | DOHMH; SLA, DOS formation, Google first review |
| A/B | building retail area / outdoor seating | 94.9 / 27.4% (2021 cohort) | PLUTO; Open Restaurants |
| B | rent by NTA-year, either measure | 92.2% (2011–25) | registry rent 2019–24 (87.5%); DOF market value/sqft (r = 0.71 with registry) |
| B | corridor rents | Manhattan 17 corridors 2010–25; Brooklyn 18 corridors 2015–25 | REBNY |
| C | tract jobs / subway within 800 m | 97.1 / 82% | traffic area |
| D | RRF recipient | 13% of 23,969 alive in May 2021 | 3,329 of 5,553 NYC recipients linked |
| D | unfunded applicant | 0% | none public |
| E | critic acclaim / Google rating | 1.5% (1,263) / 24.1% | ratings area |

## Added
- One row per permit with life window and geography.
- Cuisine code list, crosswalk and family map (also fixes text-encoding errors in older copies).
- Chain flags, legal-entity links, operator groups. Business entities only: sole proprietors dropped, filing addresses stored as hashed group IDs.
- Storefront history before each opening, size proxies, age evidence.
- Rent tables by tract and NTA; REBNY Brooklyn corridors; DOF borough retail rental income/sqft for filing years 2012–2024.
- RRF table with calibration totals (`camis_rrf_design.parquet`).

## Still missing
- Per-restaurant seat counts (FDNY assembly permits are building-level).
- Corridor rents for Queens, Bronx, Staten Island (never published; fall back to borough income).
- Observed price tier for most places.
- Operators using one LLC per location look like first-timers, so first-time operators are overcounted. The DOS entity file is active-only, which biases toward survivors.

## RRF natural experiment (analysis D)
Not feasible as a true experiment: no business-level list of approved-but-unfunded or rescinded applicants exists publicly (SBA/FOIA/journalist releases are recipients only; court records name plaintiffs only).
- SBA report through 2021-06-30: New York had 27,643 applications, 9,775 approvals.
- GAO-22-105442 (read by a subagent, not verified here): 150,166 eligible applicants unfunded nationwide; 2,964 approved priority awards rescinded.
- Fallback: recipients vs all other eligible restaurants alive in May 2021, with PPP second-draw loans as an applicant marker. Real controls would need a FOIA request to the SBA.
