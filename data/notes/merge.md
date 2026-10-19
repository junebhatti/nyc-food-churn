# Merge pipeline (2026-10-19)

Rebuild everything (about 2 minutes, all local):
```
.venv/bin/python -W ignore pipeline/fetch_analysis_inputs.py base cuisine chains operators operators2 storefront size rent age rrf
.venv/bin/python -W ignore pipeline/build_lifespans.py
.venv/bin/python -W ignore pipeline/build_businesses.py
.venv/bin/python -W ignore pipeline/build_buildings.py
.venv/bin/python -W ignore pipeline/build_attach.py
.venv/bin/python -W ignore pipeline/build_checks.py
```
Outputs are in `data/processed/` (gitignored, 22 MB): `permits.parquet`, `businesses.parquet`, `buildings.parquet`, `checks.json`.

## Steps
1. **build_lifespans.py:** one row per DOHMH permit (85,259).
   - Opening = earlier of first listing and first inspection.
   - Closure = L + k·(U − L), with k 0.30 for 2016–18 and 0.37 otherwise.
   - L is raised by named proof of life (PPP, RRF, Open Restaurants, research check-ins; 311 skipped as unreliable).
   - Placeholder inspection dates before 2005 are ignored.
   - Lot-centroid coordinates fill pre-2019 permits (98% have coordinates).
2. **build_businesses.py:** permits → businesses.
   - 7,211 permits listed and dropped without ever being inspected are flagged `likely_never_opened` and excluded.
   - Permits with the same or a fuzzily similar name on the same tax lot (BBL, not street text, which is spelled differently across eras) merge when the gap is ≤ 365 days. Result: 67,059 DOHMH businesses, 8,521 of them multi-permit.
   - 645 businesses flagged as relocated (non-chain, same name at a new lot within a year).
   - Plus 2,107 NYSLA bar/tavern/club premises with no DOHMH match within 60 m by name. Total: 69,166.
3. **build_buildings.py:** building = BIN, else BBL, else street text; bars snap to the nearest lot within 40 m.
   - 39,605 buildings. 992 are multi-tenant (4+ businesses open at once).
   - 504 non-multi-tenant buildings have had 5+ businesses since 2012 (max 9).
   - Each business gets its prior-tenant count, the predecessor's lifespan, and the vacant gap.
4. **build_attach.py:** joins on the latest permit.
   - Coverage: cuisine family 95%, price tier 92% (22% from menus or stated prices; the rest are proxies), chain flags, operator, size, RRF/PPP.
   - Acclaim: Michelin, NYT, Eater, awards; 1,396 businesses.
   - Rent: neighbourhood rent in the opening year, 94%.
   - Foot traffic joins once `traffic_by_tract_year.parquet` exists (not yet).
5. **build_checks.py:** results below.

## Validation (checks.json)
- **Integrity:** 0 duplicate ids, 0 negative lifespans, 98% with coordinates.
- **Exit rate vs Census BDS (NAICS 72, NYC counties):**
  - Close for 2013–17: 12.1/12.0, 11.7/12.6, 11.1/12.1, 10.9/11.2, 10.2/11.5.
  - Low for 2018–19 (10.0, 7.6): long COVID-era windows push those closures into 2020 (15.7).
  - Low for 2022–25 (about 8%): recent closures aren't purged from DOHMH yet (right edge).
  - Use 2013–17 for level comparisons, and treat 2018–21 as one pooled period.
- **Closure dates vs 901 dated closing posts:**
  - Our estimate is nearly unbiased (median 17 days late).
  - Median absolute error is 96 days, against 92 for the plain window midpoint. The k rule fixes bias, not spread.
  - So dates are good to about a quarter: analyse lifespans in years, not days.

## Known caveats
- `multi_unit_operator` is False by default; a real entity link exists for about 40% of permits.
- Price tier: proxies separate cheap from mid but never predict upscale. Use menu/stated tiers for the cheap-vs-fine analysis.
- Pre-2012 openings are left-censored (`left_censored`); `known_open_by` has the earliest independent evidence (OATH back to 1997).
