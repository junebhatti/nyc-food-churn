# Recent cross-check (2026-10-18)

Script: `pipeline/crosscheck_recent.py`. Match = within 80 m and normalized-name Jaro-Winkler ≥ 0.85.

## Open per live DOHMH (30,918 with coords)
| source | matched | says closed |
|---|---|---|
| Overture 2026-09 | 62.0% | 29 |
| Foursquare (≤ 2025-02) | 60.2% | 353 |
| OSM live | 41.7% | — |
| Liquor licenses (on-premises) | 32.9% | 2,695 (older license at same spot) |
| any source | 77.2% | |

Unmatched open places look like real, newer or small businesses (e.g. "AB HOT PIZZA", "KOI SUSHI"), not junk.

## Dropped from DOHMH Jun 2025 – Apr 2026 (4,887)
- Liquor licenses agree it closed for 1,026 of 1,332 matched (77%).
- Overture still says "open" for 2,302 of 2,479 matched (93%), so commercial sources lag closures badly. Use them for presence, not for closure dates.
- Same building now (by BIN):
  - 1,027 (21%): same name, new permit ID. **Not a closure** — merge by name + building, or churn is overstated by ~1/5.
  - 2,587: a different food business in the building now (includes buildings with several places; needs open-after-close check).
  - 1,183: no food business in the building now.

## Reverse: open Overture food places with no DOHMH match
40–65% per category. Expected for bars (no food permit), and Overture carries stale/duplicate entries. The generic "restaurant" category is 86% unmatched, which looks mostly like noise.
