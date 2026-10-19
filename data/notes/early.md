# Early history (before the 2012-07-06 DOHMH copy)

Status 2026-10-18. Run `.venv/bin/python pipeline/fetch_early.py`. Files are in `data/raw/early/` (26 MB).

## Result in one line

I found no DOHMH inspection copy older than 2012-07-06, so nothing was added to `manifest.csv`. What I did find is the **OATH Health Tribunal case file**: every DOHMH food-safety Notice of Violation that went to a hearing, dated **1997 to now**. It links to CAMIS well and pushes first-seen dates back for 11k restaurants.

## OATH DOHMH-BFSCS cases (NYC Open Data `jz4z-kudi`)

- `oath_bfscs.csv.gz` has 517,124 tickets with `issuing_agency = 'DOHMH - BFSCS'` and violation_date before 2015. Raw API fields, one row per ticket.
  - Each ticket has: violation_date (the inspection date), respondent (the **legal entity** name, not the DBA), premises borough, respondent house number and zip, hearing result, penalty, and up to 10 DOHMH violation codes (04L, 08A, 10F…).
  - Tickets per year: about 20–30k in 1997–2008, 46k in 2009, 39k in 2010, 38k in 2011, 28k in 2012. The street name, block and lot are always blank for this agency.
- **Linking (`early_link.py`).** Step 1 matches a ticket to a CAMIS on the exact same date, borough and house number = DOHMH building, using name-token overlap to break ties. Step 2 propagates the CAMIS to every ticket of the same entity (normalised legal name + borough + house) when at least 80% of that entity's direct matches agree.
  - Direct match rate, where the union is complete: 78% (2012), 75% (2013), 77% (2014). Lower in 2009–2011 (39–71%) and almost 0 before 2008, because the union has few inspections before then.
  - Links: 127,603 tickets by date+address and 99,151 by entity, covering 26,366 CAMIS.
- `oath_bfscs_camis.csv.gz` is the ticket→CAMIS crosswalk (`method` = date_addr | entity). Before 2012-07-06 it has 167,544 linked tickets for 19,799 CAMIS.
- `early_camis_first_seen.csv` has, per linked CAMIS: first OATH date, first DOHMH inspection in the union, and the difference.
  - **11,181 CAMIS** have an OATH date more than 30 days before their first union inspection. The median shift is 4.9 years, and 9,122 of them were already active before 2008.
- **Validation.** CAMIS numbers are issued sequentially. The first OATH year tracks the CAMIS serial monotonically: 403xxxxx gives 1997 (left edge of the data), 408→2002, 410→2005, 412→2007, 414→2010, 416→2012, 500→2014. The 5th percentile never predates the serial's era, so entity links are not grabbing earlier, unrelated owners.
  - **Side finding:** the CAMIS serial is itself an approximate permit-issue date for any CAMIS. This table calibrates it.
- `oath_entities.csv.gz` has 113,886 entities (name + boro + house), each with first and last date and ticket count; 25,518 are linked to a CAMIS.
  - The 86,505 unlinked entities include 64k last seen before 2009. They are restaurants that closed before any DOHMH copy, which gives presence evidence for 1997–2012.
  - **The count overstates distinct businesses.** Legal-name spelling variants split one business into several entities. Unlinked entities have no DBA or street, so geocoding needs house + zip + name.

Caveats:
- Only inspections that produced a tribunal NOV appear, so a clean restaurant can go unseen for years. Treat this as presence evidence (first seen ≤ date), not as an open date or a closure date.
- The respondent zip is sometimes the owner's mailing zip (for example a CT zip on a Manhattan restaurant).
- 1909/1929-style dates are typos. Use 1997 onward.

## What failed (no pre-2012-07 DOHMH copy exists anywhere I could reach)

- **Wayback CDX** (one throttled client, `early_ia.py`):
  - `nyc.gov/html/doh/downloads/zip/bigapps/`: only `dohmh_restaurant-terms.pdf` (2010) was captured, never the `_002.zip`.
  - `nyc.gov/html/datamine/downloads/`: only 14 small `data/` files from 2010–11 (sidewalk cafes.csv, laundromats.csv…), with no restaurant zip.
  - `data.cityofnewyork.us` and `nycopendata.socrata.com` `api/views`, `download`, `file_data` and `assets` before 2014: nothing large.
  - The a816-restaurantinspection detail pages: only 99 captures before 2013.
  - Domain-wide nyc.gov filtered CDX returns HTTP 500.
- **GitHub (authenticated):**
  - Code search for `WebExtract.txt`, `dohmh_restaurant-inspections`, `RI_Webextract` and `CUISINECODE INSPDATE` turned up only repos already used, or repos that download but do not commit the data (RoachMap, donteatat, technickle, drjasondavis 2012-06).
  - Repo search before 2013-07 and commit search before 2012-07 found nothing.
  - ryankanno's first commit is the 2012-07-06 pull.
- **Socrata Discovery** (all domains): the earliest NYC restaurant copies are the Lehman ones already held (2012-11 onward).
- **archive.org item search:** nothing (WebExtract, dohmh, bigapps, datamine).
- **Not tried:** NYMag/MenuPages/Zagat listings on Wayback (a large crawl, metadata only), Google Code archive, NYT/WNYC desk copies (no repos found under the wnyc or newsdev orgs).
