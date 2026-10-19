# Research datasets: dated venue activity (check-ins, reviews)

Status 2026-10-18. Reproduce: `.venv/bin/python pipeline/fetch_research_poi.py [gl2018 tsmc msteps lbsn match]` (about 45 min). Code: `fetch_research_poi.py` (runner), `rpoi_common.py` (HTTP, remote-zip streaming, filters, writer), `rpoi_googlelocal2018.py`, `rpoi_foursquare.py`, `rpoi_match.py`. Output is `data/raw/research_poi/` (10 MB). The big global files are streamed and filtered on the fly, so nothing global is stored.

Each source has two files:
- `<src>_venues.parquet`: venue_id, name, lat, lon, category, first_date, last_date, n_activity, n_days
- `<src>_yearly.parquet`: venue × year activity count

`rpoi_venue_match.parquet` adds `camis` (JW ≥ 0.85 within 80 m) and `sla_premise_key`. `rpoi_closure_evidence.parquet` has one row per closed CAMIS.

## Pulled

| src | dataset | activity dates | NYC food/drink venues | license |
|---|---|---|---|---|
| `gl2018` | UCSD Google Local, 2018 release (places + 11.4M reviews worldwide) | 2002 → 2014-03 (placeholder 1990 dates dropped) | 16,572 (from 37k NYC places) | research use; cite He et al. RecSys'17, Pasricha & McAuley RecSys'18 |
| `tsmc2014` | Dingqi Yang, NYC check-ins (TSMC 2015) | 2012-04 → 2013-02 | 11,670 (94% named) | no license; citation requested |
| `lbsn2vec` | Yang et al., LBSN2Vec++ raw set (90M check-ins), 4TU | 2012-04 → 2014-01 | 23,198 (89% named) | CC BY 4.0 |
| `msteps` | Massive-STEPS New York (HF), built from the CC0 Semantic Trails | 2012-04 → 2013-09 and **2017-10 → 2018-10** | 16,904 (7.0k active 2017–18) | Apache-2.0 (upstream CC0) |

- The Foursquare sets carry legacy 24-hex venue IDs. Names come from our FSQ OS Places copy (`poi/fsq_all.parquet`), which keeps those IDs. Unnamed venues can't be name-matched.
- Food/drink is decided by the category regex in `rpoi_common.FOOD`. Google Local 2018 places have no category, so the categories on their reviews are used. The output is clipped to the five boroughs.

## Matching

| src | in DOHMH | in SLA | either | named venues not in DOHMH (restaurant-like / other) |
|---|---|---|---|---|
| gl2018 | 75.9% | 39.6% | 80.2% | 3,070 / 919 |
| lbsn2vec | 66.9% | 34.6% | 72.0% | 4,623 / 2,244 |
| msteps | 73.8% | 42.2% | 78.8% | 2,942 / 1,486 |
| tsmc2014 | 74.7% | 41.2% | 79.7% | 1,962 / 823 |

- In total, 20,556 distinct CAMIS are matched.
- Across the FSQ-ID sources, 6,922 of 21,015 named venues are not in DOHMH, and 1,072 of those are in SLA.
- About 18–21% of matches have similarity below 1. A spot check looked right, but chain branches (CHOP'T, Outback) can grab the wrong permit.
- **Pre-2019 DOHMH copies have no coordinates.** I used `analysis_inputs/camis_base` (DOHMH coordinates, or else the PAD lot centroid). Without it, no CAMIS that closed before 2019 can be matched.

## Closure dates

DOHMH closure window = (last snapshot listing the CAMIS, next non-PARTIAL snapshot). There are 52,393 closed CAMIS with coordinates, and 14,664 have a research match.

| verdict | CAMIS |
|---|---|
| research date after the last snapshot, inside the window | **507** (median +50 d) |
| after the last inspection, before the last snapshot | 1,624 |
| no later evidence | 11,554 |
| after the window (contradicts) | 979: chain branches, successors, late reviews |

- Together, **2,131 CAMIS get a later last-seen-open date than their last inspection** (median +125 d). By year of the new date: 2012: 462, 2013: 1,011, 2014: 339, 2017: 94, 2018: 222.
- Snapshots listing a CAMIS often lag its last inspection by months, so the "after last inspection" cases are real gains.
- **Gap periods.** Only **2018-04..07** is reached:
  - 11 closures got a date after the last snapshot.
  - 53 got a date after their last inspection.
  - 97 new last-seen dates fall inside the gap.
- The 2015, 2016, 2018-11..2019-05, COVID and 2021-22 gaps get nothing, because no open dataset found covers 2014-04 → 2016-12 or 2018-11 onward.
- Earlier opening evidence: 3,683 closed CAMIS have research activity before their first DOHMH inspection (median 618 d). Treat this as an upper bound on the opening only when the name agrees, since the venue may be a predecessor.

## Ruled out
- **Semantic Trails, direct.** The figshare ndownloader returns HTTP 500, and figshare.com sits behind a WAF bot challenge (not bypassed). Massive-STEPS NYC already holds its NYC rows with names.
- **Global-scale check-in set (TIST2015, 2012-04 → 2013-09).** It is a subset of the LBSN2Vec++ raw set, so I skipped it.
- **NYC Restaurant Rich (ubicomp 2013).** Anonymized venue IDs, no timestamps, no coordinates. Deleted.
- **Gowalla and Brightkite (SNAP).** Location ID and coordinates only, with no names or categories, so they can't be tied to a CAMIS. The Weeplaces and Gowalla-spots host (yongliu.org) is now a spam domain.
- **Foursquare 2016–19 user-venue sets.** No public release found; the papers say "contact the authors".
- **Yelp Open Dataset:** no NYC.
- **YFCC100M:** about 100M rows of Flickr metadata (tens of GB), and its places are localities, not venues. Impractical.
- **Instagram and Twitter dumps:** not openly licensed.
- **Citi Bike and other mobility data:** no venue names.
