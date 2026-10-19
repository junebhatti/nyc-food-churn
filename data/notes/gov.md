# Gov / storefront / rent / geo / geocoding

Reproduce: `.venv/bin/python pipeline/fetch_gov.py`. Outputs are in `data/raw/gov/`; `manifest.json` lists each one's id, rows, date range and fields.

## Liquor licenses (NYSLA)
- **Why active licenses start in 2020.** NYSLA moved to a new system (LAMP) in mid-2023, which resets the original issue date. Almost all dates are 2023 or later; 2020-08-03 is one outlier.
- **Older data recovered from the Wayback Machine.** The retired datasets are now private (HTTP 403):
  - hrvs-fxs2, active licenses (2017, 2021, 2022 captures): true original dates back to 1933.
  - i594-5w3n, inactive licenses with "Date Inactive" (2021–23).
  - wzgj-tb42, expired licenses.
  - These join to the current data through `legacyserialnumber`.
- **`sla_licenses_nyc`** has 58.9k licenses, 31.8k of them on-premises.
  - 19.4k have a true start date and 19.3k have an end date.
  - `category` works across both class-code systems.
  - LAMP issues a new serial on class changes and "Additional Bar" licenses, so count premises with `premise_key` (name + address) or BBL, not by serial.
- **Coverage.** Start dates are good for any license active in 2017 or later. End dates exist only from 2015.
- **Gap: bars that opened and closed in 2011–2014.** I found no capture before 2017 after:
  - every Wayback URL variant;
  - the other private ids;
  - GitHub, Kaggle and data.gov mirrors;
  - opengovny (HTTP 403).
  - Options left: a FOIL request to NYSLA, or DOHMH inspection data.

## City datasets
- **Storefront registry (92iy-9c3n):** 481k rows, 2019/20–2025, with BBL, vacancy and activity ("FOOD SERVICES" is 55k rows). Lease expiry is filled almost only for 2023.
- **Storefront rent stats (dxru-eun8, x3n4-h56k):** cleaned to numbers; "*" means suppressed. Rent is $/sq ft/**month** by tract (~1.3k), council district and borough, 2019–2024. Tract medians are often whole dollars.
- **Outdoor dining:**
  - Open Restaurants: 14.4k, 2020–23, with SLA serial and BBL.
  - Dining Out NYC: 2.5k, from 2024.
  - Historical sidewalk café: only 324 rows.
- **DCWP licenses:**
  - Legacy sidewalk café, cabaret and catering licenses and applications, 1984–2015.
  - Current: stoop-line stands only.
- **Rent proxy (`dof_commercial_values`):** DOF market values for commercial and mixed-use lots, FY2011–19 and FY2023–27. FY2020–22 are not published.
- **REBNY (`rebny_manhattan_corridor_rents.csv`):**
  - 17 Manhattan corridors, 2010–2025, average ground-floor asking rent, parsed from PDFs.
  - QA: 98% agree with the next report's prior-year column.
  - Check 2023+ by hand.
- **Not available:** Commercial Rent Tax by area, lot-level income and expense data, CBRE (behind registration), BID storefront surveys.

## Geography
- GeoJSON: 2020 NTAs, 2020 tracts, boroughs, BIDs.
- Tract → NTA equivalency.
- `pluto_slim`: 858k lots, with ct2020 and nta2020.

## Geocoding recommendation
**Use the local PAD/SND matcher (`gov_geocode.PadGeocoder`) first, and send its misses to GeoSearch.** PAD/SND are the address files behind Geosupport.

| Test | PAD matcher | GeoSearch |
|---|---|---|
| 200 tricky addresses, BBL or ≤100 m | 100% | 98% |
| Same, "1/2" addresses | 100% | 60% |
| Held-out sample | 99.5% | not run |
| 500 SLA addresses (2017), ≤150 m | 94% | 91% |
| Speed | ~3k/s | ~17 req/s (8 threads) |

- The 200-address set is the one I tuned on.
- Combined, 100k addresses take about a minute.
- Geosupport Desktop has no macOS build and Docker isn't installed, so I didn't test it.
