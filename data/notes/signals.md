# Proof-of-life and open/close signals

Status 2026-10-18. Reproduce:

```
.venv/bin/python pipeline/fetch_signals.py      # all sources (~15 min; DOS is ~10 of it)
.venv/bin/python pipeline/signals_eval.py       # the numbers below (log: data/raw/signals/_logs/eval.log)
```

Code: `fetch_signals.py` (runner), `signals_common.py` (schema, PAD geocoding, manifest),
`signals_city.py` (NYC Open Data), `signals_state.py` (data.ny.gov), `signals_eval.py`.
Every pull is a SoQL-filtered Socrata query, run one after another. Output is 72 MB.

## Files (`data/raw/signals/`)

Each file has the same columns: `source, source_id, event_date, event_type, name, legal_name, address, house, street, boro (1-5), zip, bbl, bin, lat, lon, geo_src, detail`, plus a few columns specific to that source. `geo_src` says where the BBL came from: `source` (the dataset had it) or `pad` (filled by `PadGeocoder`). `manifest.json` lists rows, dates and event types for each file.

| file | dataset | rows | dates | events | BBL |
|---|---|---|---|---|---|
| `sr311_food` | 311, 76ig-c548 (2010–19) + erm2-nwe9 (2020–) | 591k | 2010-01 → now | complaint_noise / food / outdoor_dining / drinking / smoking | 92% |
| `dob_bis_food` | BIS job filings ic3t-wcy2 | 67k rows, 30k jobs | 2000 → 2021 | dob_filing / dob_permit / dob_signoff | 99.8% |
| `dob_now_food` | DOB NOW filings w9ak-ipjd | 31k rows, 14k jobs | 2017-11 → now | same | 99.9% |
| `open_restaurants_insp` | Open Restaurants inspections 4dx7-axux | 82k | 2020-07 → 2024-05 | outdoor_dining_inspection (DBA + legal name) | 94% |
| `nyc_business_acceleration` | SBS NYC Business Acceleration 9b9u-8989 | 3.8k | 2010 → 2019 | opened (**actual opening date**, DBA) | 95% |
| `sba_ppp_food` | SBA PPP, NYS extract y8zq-jmz6 | 27k loans | 2020-04 → 2021-06 | loan_approved, loan_forgiven | 91% |
| `sba_rrf` | SBA Restaurant Revitalization Fund 3pjx-bgty | 5.6k | 2021-05 → 06 | grant_approved | 90% |
| `nys_dos_entities` | NYS DOS all filings 63wc-4exh | 46k formed, 6k ended | 1995 → now | entity_formed / entity_ended | none (join on `name_key`) |
| `_dos_formations_nyc` | cache: every NYC-county formation 1995+ | 2.68M | | | |
| `camis_bbl`, `closure_tightening` | eval outputs: CAMIS → BBL and life window; per closed CAMIS, the old and new last-seen date and its source | | | | |

**Filters**
- **311:** `location_type` is Restaurant/Bar/Deli/Bakery, Club/Bar/Restaurant, Restaurant, Catering Service or Food Establishment or Vendor, plus every Outdoor Dining SR. 311 never gives the business name. `resolution_closed` (47 rows) marks SRs whose resolution says the place was closed or out of business.
- **DOB:** server-side LIKE, then a word-boundary regex: restaurant, eating and drinking, cafe, bar, pub, pizza, bakery, deli, kitchen exhaust/hood, Ansul, grease trap, and similar. A negative regex drops cafeteria, grab bar, rebar, residential lounge and school hits. The `name` field is the owner's business, usually the landlord.
- **PPP:** NAICS 722xxx or 311811, project county in NYC.
- **DOS:** Formations (certificate of incorporation, articles of organization, application of authority) whose principal-office county is in NYC, matched on normalized name (suffixes and punctuation stripped) to SLA, PPP and RRF legal names. End filings (dissolution, surrender, annulment) are then pulled by corpid. 44k of 55k target names matched.

## Usefulness (signals_eval.py)

**Closure dates.** A closed CAMIS's closure lies between its last inspection L and the first full copy U that lacks it (the median window is 443 d). A signal counts toward a CAMIS (is "attributable") when it sits at the same BBL inside (L, U) and either:
- its name matches the DBA (named sources only), or
- no other CAMIS or SLA on-premises licence was plausibly at that BBL then.

DOB filings and "opened" events are excluded here, because after L they are mostly the next tenant's buildout.

| closures whose window overlaps (and is >120 d) | n | tightened | median gain | median share of window removed |
|---|---|---|---|---|
| all closures (any window) | 38,696 | 15% | 337 d | 52% |
| 2015-03..08 | 4,539 | 5% | 150 d | 36% |
| 2016-04..12 | 5,069 | 6% | 178 d | 44% |
| 2017-10..2018-07 | 5,613 | 6% | 144 d | 40% |
| COVID 2020-03..2021-06 | 8,006 | **37%** | 536 d | 59% |

- **By source** (CAMIS with a >120 d window that get at least one attributable signal):
  - 311: 3,342
  - Open Restaurants: 1,634
  - PPP: 1,431
  - RRF: 399
- **311 placebo.** 9.4% of closed CAMIS have an attributable 311 signal in the 365 d before L, when they were known open. Only 2.8% have one in the 365 d after U, when they were known gone. The "after" hits are neighbours or not-yet-inspected successors. So treat a 311 last-seen as roughly 70% reliable. Name-matched sources (PPP, RRF, Open Restaurants) are much cleaner.
- **PPP in the COVID gap.** 7.7k loans show that 3.8k CAMIS were alive after their last inspection.

**PPP and RRF vs DOHMH and SLA** (same BBL, CAMIS plausibly open at the loan date):

| | records | matches a CAMIS | name also agrees | SLA on-premises only | neither | not geocoded |
|---|---|---|---|---|---|---|
| PPP | 27.0k | 65% (restaurants, NAICS 72251x: 87%) | 29% | 2% | 24% | 9% |
| RRF | 5.6k | 81% | 39% | 2% | 7% | 10% |

- **PPP "neither"** is mostly not storefronts:
  - At BBLs that never had a CAMIS: 69–75% of caterers, food-service contractors and mobile vendors, but only 11% of restaurants.
  - Sole proprietors (personal names, often home addresses) make up 66% of it.
- **New businesses DOHMH lacks.** About 2.4k PPP restaurant/bar loans and 0.3k RRF grants sit at BBLs that never had a CAMIS. That is an upper bound: some are owner or HQ addresses. Low name agreement is expected: PPP and RRF carry the legal name, DOHMH the DBA.
- **Bars (NAICS 7224).** 75% match a CAMIS (bars that serve food); 4% match SLA only.

**Openings.**
- **NYC Business Acceleration actual opening dates** (2.7k matched by BBL and name) validate DOHMH: the first inspection minus the opening date is a median of −3 d (IQR −10..+16). The DOHMH first inspection is a good opening proxy.
- **DOB food jobs** precede the first inspection by a median of about 1 year (IQR 0.5–2 y). They are useful as a "buildout started" bound and for the 10k left-censored CAMIS (first inspection in the data before 2011-07): 1.4k of those have a DOB job, median year 2009.

**SLA on-premises bars** (bar, tavern, club; 6,642 premises; 2,397 have a known start before 2015):
- **Located evidence before 2015.** 64% of premises have a pre-2015 311 or DOB signal at their BBL. For 2,408 of them, that evidence is new: they have no known pre-2015 start. This is address-level evidence of *a* bar or restaurant there, not necessarily this licensee.
- **DOS legal entity.** Found for 71% of premises, and formed before 2015 for 33%. That is new pre-2015 evidence for 608 premises.
- **DOS-to-SLA lag.** The median lag from DOS formation to SLA original issue is 481 d (IQR 263–1133). So formation is an upper bound on the opening date, not a proxy for it.

## Ruled out or not pulled

- **DOS name matching to DOHMH DBAs.** 34% of CAMIS have a DBA equal to exactly one NYC entity name. But the formation-to-first-inspection lag has an IQR of 129–2507 d: many are homonyms ("JOES PIZZA"). Use DOS only through legal names (SLA, PPP, RRF).
- **DOS "Active Corporations" n9v6-gdp6.** Active entities only (survivor bias). The all-filings dataset supersedes it. DOS addresses are service-of-process addresses, not premises.
- **Certificates of Occupancy** (bs8b-p36w, pkdm-hqz6). They have no use or description field. **DOB permit issuance ipu4-2q9a** has no description; BIS filings cover the same jobs.
- **FDNY** (kfgh-h6re, itd7-gx3g, ssq6-fkht). Building-level only: no occupancy type and no business name. BFP-historical has a single last-visit date. Place of Assembly permits appear as BIS job type PA (316 jobs, included).
- **DCWP inspections and charges** (jzhd-m6uv): 2023+ only, with 2.6k restaurant rows, so no gap value. Other DCWP licence data is already in `data/raw/gov`.
- **NYS sales tax Certificates of Authority.** No public business-level data, only aggregate taxable sales. The same goes for DOF business filings and Commercial Rent Tax.
- **SBS certified and EO 50 business lists.** Certification rosters, not storefronts. Commercial Lease Assistance has no public dataset. Storefront surveys are already in `gov` (LL157 registry, MBPO 2020).
- **NYC Restaurant Week participants (Wayback).** Only the 2014 season is captured in bulk (about 170 slugs). Other years have fewer than 5, and the `nycgo.com/restaurants/` captures are the general directory. These are names only and mostly long-lived high-end places, so the marginal value is low.
- **DOHMH closure orders.** Already in the inspection data (action "Establishment Closed by DOHMH"). There is no separate dataset.

## Caveats

- **311 sees nuisances, not businesses.** Complaint volume grows over time, from 25k/yr in 2010 to 54k/yr in 2024. Attribution assumes one occupant per BBL. In malls and big buildings, the "alone" rule usually refuses to attribute.
- **Open Restaurants inspections.** Rows with `skipped=True` ("No Seating" and similar) are not counted as proof of life.
- **PPP dates.** The `loan_forgiven` date is evidence about the owner, not the premises, and is excluded from the evaluation. Second-draw (PPS) loans in 2021 are the strongest evidence of survival through the COVID gap.
