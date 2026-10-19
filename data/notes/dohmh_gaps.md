# DOHMH gap filling: extra copies

Status 2026-10-18 (round 2). There are **25 extra copies** (10 from round 1, 15 from round 2) in `data/raw/dohmh/extra/` (301 MB), registered in `manifest.csv` as `extra/<name>`. `pipeline/dohmh_extra.py` re-creates them, and `dohmh_profile.py` picks them up unchanged. `dohmh_sources.py` now keeps `extra/` rows when it rewrites the manifest. `rdata` is installed in `.venv`.

**Partial and derived copies are presence evidence only.** A CAMIS missing from one of them does **not** mean it had closed. `dohmh_profile.py` treats every copy as a full snapshot, so closure logic should skip copies whose manifest `notes` start with PARTIAL or DERIVED.

## Copies

**Backward, before 2014-05.** Every copy here is new in round 2. They are old WebExtract files (coded boro/cuisine), transcoded from cp1252.

| id | pull | rows | CAMIS | kind |
|---|---|---|---|---|
| gh_ryankanno_20120706 | 2012-07-06 | 523,206 | 24,340 | full (BigApps zip) |
| gh_ryankanno_20121019 | 2012-10-19 | 535,401 | 24,692 | full |
| lehman_ptqi_20121129 | 2012-11-29 | 50,077 | 2,382 | PARTIAL: Bronx only |
| lehman_gqhi_20130329 | ≈2013-03-29 | 24,275 | 24,275 | DERIVED: latest inspection per CAMIS |
| gh_hmason_20130906 | 2013-09-06 | 544,563 | 25,060 | full |
| gh_uncamy_20131121 | 2013-11-21 | 546,812 | 25,244 | full |
| gh_munk_20140213 | 2014-02-13 | 538,930 | 25,213 | full |
| gh_mrsnickers_20140320 | 2014-03-20 | 533,577 | 25,064 | full |

The `lehman_*` copies come from CUNY Lehman's Socrata portal, `bronx.lehman.cuny.edu`. It is still live and needs no Wayback. Their RECORDDATE was Excel-mangled, so it was set to the day after the latest inspection.

**2014-08 → 2015-09** (round 1, plus lehman_mt6q):
- 2014-10-09 gh_datacomputing (full; 2,677 rows misaligned in the source `.rda` were dropped).
- 2014-11-02 gh_akkaluzny (DERIVED, one row per inspection).
- 2015-02-12 gh_vsm1013 (PARTIAL, inspections 2014-11..2015-01).
- ≈2015-03-01 gh_bethannezink (full; CAMIS recovered by matching, 881 unmatched restaurants given synthetic `X<rowid>` ids).
- **2015-07-05 lehman_mt6q** (PARTIAL: Bronx only, 2015 inspections; 2,697 rows, 1,715 CAMIS).
- 2015-08-02 gh_compjour (full).

**2016** (new in round 2):
- **2016-09-27 gh_residentmario:** DERIVED. Every CAMIS in the pull (26,064), each with its initial and latest inspection; 49,261 rows.
- **≈2016-10-07 gh_tzstatsads_20161007:** DERIVED. A CAMIS list only, 25,981 rows, with no inspection dates. The pull was on or before the 2016-10-07 commit.

**2017-08 → 2018-07:**
- From round 1: 2017-09-08 ldgarber, 2017-10-19 p8105, 2018-03-01 miguel75an (PARTIAL), 2018-04-06 ccw2145.
- New: **2018-02-07 gh_tzstatsads_20180208**, full, 385,254 rows, 26,621 CAMIS. Columbia ADS spring-2018 `.xlsx`; Excel serial dates were converted.

**2026-04 → 2026-10** (new): Wayback captures of the new Socrata **v3 export endpoint** (`api/v3/views/43nn-pn8j/export.*`), which the old CDX enumeration never queried:
- 2026-06-04 xlsx: 296,912 rows, 31,188 CAMIS.
- 2026-08-06 csv: 294,619 rows, 31,188 CAMIS.
- 2026-09-24 xlsx: 294,950 rows, 31,335 CAMIS.

Also kept from round 1: 2017-06-05 smach.

## Union

The union has **85,138 distinct CAMIS**: 84,257 real 8-digit CAMIS plus 881 synthetic `X…` ids. Before round 1 it was 76,395, and after round 1 it was 77,632.

Round 2 adds about 7,500 CAMIS, almost all from the **backward** copies. Counting each CAMIS at its earliest new snapshot:
- 2012-07-06: 6,341
- 2012-10-19: 350
- 2013-09-06: 303
- 2013-03-29: 289
- 2013-11-21: 64
- 2014-02-13: 49

These are restaurants that closed before the 2014-05 copy existed. The year 2010 rose from 1.9k to 16.1k CAMIS inspected, and 2011 from 14.9k to 21.2k.

Duplicate check:
- No two CAMIS collapse together after stripping leading zeros or `.0` suffixes.
- Every non-`X` CAMIS is exactly 8 digits.
- Round 2 found and removed 55 garbage "CAMIS", which were date strings coming from misaligned `.rda` rows.

## Gap list now (consecutive snapshot dates; full copies only in brackets)

- 2016-04-07 → 2016-09-27: **173 d**. Was 246 d; 09-27 and 10-07 are derived.
- 2013-03-29 → 2013-09-06: 161 d (the backward range is new).
- 2015-03-01 → 2015-08-02: [154 d]. 07-05 is Bronx-only.
- 2017-10-19 → 2018-02-07: **111 d** (was 133/169 d). Then 2018-04-06 → 2018-07-27: 112 d.
- 2026-04-02 → 2026-10-16: was 197 d; now **63 / 63 / 49 / 22 d**.
- Overall, the largest gaps are now 205 d (2020-11 → 2021-05, when no inspections happened), 174 d (2021-09 → 2022-03) and 173 d (2018-11 → 2019-05 and 2016-04 → 09).

## Bars (NY State Liquor Authority)

`data/raw/gov/extra/sla_bars_nyc_20160219.csv.gz` holds 6,659 NYC ON-PREMISES LIQUOR rows from hrvs-fxs2 (the quarterly active-licence list), as extracted around 2016-02 by a Columbia ADS project. It keeps the original issue, effective and expiration dates. It predates the 2017-04 Wayback copy, but it is **not** a 2011–2014 list.

No 2011–2014 SLA list found:
- data.ny.gov Wayback captures for hrvs-fxs2, i594 and wzgj start in 2017. The large 2011–16 data.ny.gov exports on Wayback are all PDFs.
- Kaggle's NYS SLA datasets are 2017 or later.
- The GitHub code-search hits are 2016 or later.

## Tried, nothing (round 2)

- **GitHub code search (token):** 50 filename, header-string and content queries. It does not index files over 384 KB, so it mainly surfaced repos that *read* the CSV.
- **History walks:** blobless-clone history walks of about 1,100 repos found via code search, repo search (2011–14, 2015, 2016 windows) and course orgs (TZstatsADS 2016, P8105, nycdatasci, stat4701, NYUDataBootcamp). Rejected:
  - ipeirotis 2017-10-30 and stat4701 2014-04-17: too close to existing copies.
  - hmason 2013-09-13: duplicate.
  - agabardo / MongoDB primer JSON: ~2015-01, attribute-only.
  - bkleyn: Excel-edited.
  - dtkaplan: same as DataComputing.
  - nycdatasci bootcamps: only small subsets.
- **P8105:** `p8105.datasets` has only the 2017-10 data (2018 commits) and a 2025 refresh.
- **Common Crawl index:** every query in two sessions returned 502/504 (a 30 s-timeout retry also failed). Recorded as **unavailable**.
- **data.world snapshots on archive.org:** file-name scan reached about 4,100 of 15,318 items (agents a…fns), with one client. The only NYC hit is the city-of-ny item already used. Resume after `data-world-snapshot-20260713-agent-fns`.

## Next leads

- Finish the data.world scan.
- Watch the v3 export endpoint on Wayback: CDX shows captures only from 2026-06 onward.
- More Columbia ADS / EDAV semesters (Spring 2017, Fall 2017).
