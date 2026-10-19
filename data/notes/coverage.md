# Coverage gaps and fills (2026-10-18)

Reproduce: `.venv/bin/python pipeline/fetch_coverage.py [snap dcwp_tob agm_rfs agm_insp cb gaps]`.
Code: `fetch_coverage.py` (runner), `coverage_common.py` (schema, PAD geocoding, the single rate-limited
archive.org client, manifest), `coverage_sources.py`, `coverage_cb.py`, `coverage_gaps.py`.
Outputs: `data/raw/coverage/` (550 MB, 539 MB of it `_cache/` raw copies). `manifest.json` lists rows,
date ranges and BBL fill for each file. All parquets share the columns `source, source_id, name, legal_name,
address, house, street, zip, boro, category, category_raw, start_date, end_date, first_seen, last_seen, bbl,
bin, lat, lon, nta2020, geo_src, extra`.

The SNAP zip was downloaded by hand with curl into `_cache/snap/`. `snap()` raises an error if it is missing.

## New files

| file | source | rows | dates | BBL |
|---|---|---|---|---|
| `snap_retailers_nyc` | USDA FNS Historical SNAP Retailer Locator 2005-2025 | 41,916 | authorization and end dates, 2005-2025 (authorizations go back to the 1970s; 1930 is a placeholder) | 98% |
| `dcwp_tobacco_nyc` | DCWP cigarette retail dealer licences (m4ph-grrm, 2000-2013) + tobacco and e-cig dealers (w7w3-xahh) | 40,933 | creation and expiry dates | 97% |
| `agm_retail_food_stores_nyc` | NYS Ag&Markets Retail Food Stores 9a8c-vfzj: live pull + 21 Wayback copies 2016-12 to 2026-03 | 27,048 licences | first/last_seen only (the source has no issue date) | 96% |
| `agm_inspections_nyc` | Ag&Markets Food Safety Inspections d6dy-3h7r: live + 10 Wayback copies 2020-01 to 2026-04 | 27,405 | inspection dates | 95% |
| `cb3_sla_items` | Manhattan CB3 full-board minutes, all 250 monthly PDFs, SLA & DCA committee items | 5,024 | 2004-2026, monthly | 99% |

Categories are `bodega_deli`, `bakery`, `coffee_tea_retail`, `grocery`, `specialty_food`, `market`,
`tobacco_retail_other` and `bar_or_restaurant_licensed`. They come from store type, Ag&Markets
establishment code, square footage and name regexes, so they are approximate.

## Gap measurement (`coverage_gaps.py`)

The reference set is Overture 2026-09 places with confidence 0.5 or higher that are not closed (56k). A
place counts as matched if one of our "open now" records (seen on or after 2026-04) lies within 100 m and
the normalized names have Jaro-Winkler 0.85 or higher. Results are in `gap_category.csv` and `gap_nta.csv`.

| category | n | DOHMH | +SLA (before) | +new (after) |
|---|---|---|---|---|
| bodega/deli | 8,226 | 3% | 34% | **51%** |
| bakery | 3,098 | 47% | 49% | 56% |
| dessert | 1,572 | 23% | 24% | 29% |
| juice | 709 | 37% | 37% | 43% |
| food hall/market | 260 | 2% | 10% | 21% |
| coffee/tea | 4,525 | 48% | 50% | 51% |
| bar | 4,816 | 38% | 44% | 45% |
| restaurant | 32,916 | 40% | 44% | 44% |
| all | 56,378 | 35% | 42% | 46% (+2,099) |

- About 50% of Overture places stay unmatched even for restaurants. That share mostly reflects Overture
  noise (stale, duplicate and generic entries; see `crosscheck.md`), not real absences. Read the change
  between columns, not the level.
- **Worst NTAs before the fill** were South Williamsburg (20%, rising to 35% after), South Jamaica,
  Springfield Gardens, East Flatbush, Co-op City, Hunts Point, Midwood and Crotona Park East. These are
  bodega-heavy areas, and the new sources lift most of them by 5-18 points.
- **Year dips.** No NTA-year dips at least 20% below both neighbouring years in DOHMH active CAMIS
  2012-2025 (`dohmh_nta_dips.csv` is empty). The source gaps are known left-censoring: DOHMH before 2009,
  and SLA starts before 2015.
- **Source holes by year** (`inventory_year.csv`):
  - DCWP tobacco drops from 13k to 3k in 2014-2016. The legacy file stops in 2013, and the current file
    holds only licences that survived. SNAP (8.7-12.5k active per year, 2005-2025) is the continuous
    bodega series.
- **Novelty at BBL level** (`novelty.csv`). The share of each source's records at lots never seen in DOHMH
  or SLA:
  - SNAP bodegas: 18% (5,951)
  - DCWP bodegas: 14%
  - Ag&Markets: 19-24%
  - Only about 40% of bodega records sit on a lot that ever had a DOHMH CAMIS. Most of the rest are on lots
    with an SLA grocery beer licence.
- **CB3, 2005-14.** 2,870 geocoded items. 23% (672) sit on lots with no SLA on-premises licence starting
  before 2015. That is new pre-2015 bar evidence for the East Village and Lower East Side. 93% sit on lots
  with a DOHMH CAMIS.

## Caveats

- **SNAP**
  - End dates mark loss of SNAP authorization, not necessarily closure.
  - Stores that never took SNAP are missing: many delis in Midtown and the Financial District, coffee
    retail, and most bakeries.
- **DCWP legacy.** The status is a single last status, and the expiry date is the last licence term.
- **Ag&Markets Retail Food Stores**
  - `first_seen` of 2016-12 is left-censored.
  - Copies from 2016-12 to 2021-01 and from 2023-12 to 2024-09 are far apart.
  - Two Wayback captures (2024-12-15 and 2024-12-16) have broken gzip framing. They were skipped and
    logged.
- **Ag&Markets inspections.** "Current ratings" keeps only the latest inspection, so the dates are sparse.
  The key is name + street + zip, so renames split one store.
- **CB3**
  - The minutes record only items that needed a board vote: new applications, contested renewals,
    alterations and transfers. That is about 15-30 a month, while the committee reviews about 70.
    Unopposed renewals are missing.
  - The dates are the meeting month, not the opening date. About 30% of items were withdrawn
    (`extra.outcome`), so they show intent, not operation.

## Tried / not pulled

- **Other Manhattan CBs**
  - CB2: its nyc.gov pages render through a JavaScript interstitial; I did not bypass it.
  - CB1: its resolution PDFs (`/assets/manhattancb1/downloads/pdf/resolutions/YY-MM-DD.pdf`) now return 404
    on nyc.gov. They are probably available on Wayback, which is the next lead.
  - CB10 (`cbmanhattan.cityofnewyork.us/cb10/resolutions/state-liquor-authority/`) and CB12 publish SLA
    resolution PDFs. These are leads; neither was pulled.
  - CB1, CB4, CB6 and CB7: no archive found on the current site.
- **Brooklyn CB1.** Only current agendas are online.
- **NYSLA weekly "licences issued" lists.** I found no public bulk archive. A FOIL request is still the
  route for bars that opened and closed in 2011-14.
- **Food halls and markets (Urbanspace, Smorgasburg, Chelsea Market).** Not pulled. Stalls in permanent
  halls have DOHMH permits, so they are already CAMIS-covered. Smorgasburg vendors are temporary-event
  permits with no fixed premises. The Overture `food_hall_market` class is mostly farmers markets (260
  places).
- **Ghost kitchens.** DOHMH permits them; there is no separate public registry. Not measurable from
  Overture.
- **Food trucks.** Mobile vendors are out of storefront scope (2% matched).
