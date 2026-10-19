# DOHMH gap filling (2014-08 → 2015-09 and 2017-08 → 2018-07)

Status 2026-10-18. Ten extra copies, all recovered from **GitHub git history** (blobs at old commit SHAs, one Git LFS object, R data files, one SQLite DB). They live in `data/raw/dohmh/extra/` (116 MB) and are registered in `manifest.csv` with ids `extra/<name>`. `pipeline/dohmh_extra.py` re-creates them; `dohmh_profile.py` then picks them up unchanged.

Re-running `dohmh_sources.py` drops the `extra/` manifest rows. Re-run `dohmh_extra.py` after it. The `.rda`/`.RData` converters need `rdata`, which is not in `.venv`; see the script docstring.

## Copies added

| id | pull date | rows | CAMIS | kind |
|---|---|---|---|---|
| gh_datacomputing_20141009 | 2014-10-09 | 531,420 | 25,369 | full WebExtract (coded boro/cuisine), from `Violations.rda` |
| gh_akkaluzny_20141102 | 2014-11-02 | 167,180 | 24,513 | **derived**: one row per inspection, no violations |
| gh_vsm1013_20150212 | 2015-02-12 | 44,633 | 10,134 | **partial**: only inspections dated 2014-11-01..2015-01-31 |
| gh_bethannezink_20150301 | ≈2015-03-01 | 506,781 | 25,718 | full, but the source had **no CAMIS** (see below) |
| gh_compjour_20150802 | 2015-08-02 | 492,964 | 25,371 | full; the source stored it as 58 per-month files, concatenated here |
| gh_smach_20170605 | 2017-06-05 | 415,587 | 26,443 | full (bonus: falls inside the 04-21 → 08-28 gap) |
| gh_ldgarber_20170908 | 2017-09-08 | 398,928 | 26,493 | full (Git LFS) |
| gh_p8105_20171019 | 2017-10-19 | 397,584 | 26,639 | full (Columbia P8105 course copy, same as `p8105.datasets::rest_inspec`) |
| gh_miguel75an_20180301 | 2018-03-01 | 115,048 | 23,717 | **partial**: about 30% of rows, but 89% of CAMIS |
| gh_ccw2145_20180406 | 2018-04-06 | 375,307 | 26,371 | full (R data.frame) |

**Partial and derived copies.** A CAMIS missing from a partial or derived copy does **not** mean it had closed. `dohmh_profile.py` treats every copy as a snapshot. So use `n_snapshots` and `last_snapshot` from these copies only as evidence that a restaurant was *present*.

**bethannezink CAMIS recovery.** The Rails app's SQLite DB keeps restaurant ids in the source CSV's row order, which is CAMIS order. CAMIS were assigned in two passes, checked against the 2014-08 through 2015-09 copies:
1. Phone or name+zip candidates, scored by shared inspection dates. Each CAMIS was assigned to at most one restaurant (greedy).
2. Position: the CAMIS must fall between the neighbouring restaurants' matched CAMIS.

Results:
- 24,837 of 25,718 restaurants were matched.
- The matched sequence is monotonic in 24,824 of 24,836 steps.
- **881 restaurants got synthetic CAMIS `X<rowid>`:** 381 with real inspections and 500 never inspected. No free CAMIS exists in their range in any nearby copy, so they appear nowhere else. They are exactly the "opened and closed inside the gap" restaurants. Do not try to join them to other CAMIS-keyed data. The pull date 2015-03-01 is approximate: the latest inspection is 2015-02-27 and the commit is 2015-03-04.

## Effect on the union

- Distinct CAMIS rose from 76,395 to **77,632**: 881 synthetic `X…` CAMIS plus about 356 real CAMIS never seen before.
- (camis, inspection_date) rows rose from 628,166 to about 635,700.
- `last_snapshot` became more precise for about 7,700 CAMIS, which were previously dated only to the far side of a gap.

**Gap 1: 2014-08-28 → 2015-09-07 (375 d) is now covered by:**
- 2014-10-09
- 2014-11-02 (derived)
- 2015-02-12 (partial)
- 2015-03-01
- 2015-08-02

The largest remaining hole is **154 d, 2015-03-01 → 2015-08-02**. Counting only full copies, the gaps are 42 / 143 / 154 / 36 d.

**Gap 2: 2017-08-28 → 2018-07-27 (333 d) is now covered by:**
- 2017-09-08
- 2017-10-19
- 2018-03-01 (partial)
- 2018-04-06

The largest remaining hole is **133 d, 2017-10-19 → 2018-03-01**, or 169 d to 2018-04-06 counting only full copies. After that, 2018-04-06 → 2018-07-27 is 112 d.

Known quirk: DuckDB in `dohmh_profile.py` (strict_mode=false) silently reads 531,000 of the 531,420 rows in gh_datacomputing. Python's csv module parses all of them.

## Tried, nothing usable

**GitHub, other repos and leads.** Repo search unauthenticated, about 4,000 repos across windowed queries; commit search, roughly 650 commits. Blobless clones and history listings of about 110 relevant repos. Rejected:
- mariavasilkin 2014-09-16: no inspection date column.
- mendoncakr WebExtract3 2014-09-22: Excel-mangled and redundant.
- KevinW2020: duplicate of vsm1013.
- official71: one-hot transformed, no CAMIS.
- linearyuhan 2017-05-18: hashed ids.
- michaelcwang2 2018-06-20: a 1 MB subset.
- dariashifrina and jiehuan: no CAMIS or dates.
- ccw2145 2018-04-01: redundant with 04-06.
- ldgarber @81d9e8c: truncated.

**Search services:**
- **grep.app:** blocked by a Vercel bot checkpoint, which I did not bypass.
- **Sourcegraph:** only popular repos are indexed. It surfaced smach/R4JournalismBook (used) and PacktPublishing (aggregated, unusable).

**Kaggle.** The list API has about 310 datasets. Range-peeked the zips of the unchecked NYC ones: tikummacmillianngu (311 data, 2024), yunyiaveryliu (2019+ subset), chuklook (2022), shivanielakurthy (2021). Nothing has a pull date in the windows. Kaggle datasets start in 2016.

**Data repositories:**
- Zenodo: the API errored.
- figshare: only a 2016 PLOS paper's figures.
- Harvard Dataverse, Hugging Face, OSF: nothing.
- archive.org item search: noise.

**data.world snapshots on archive.org (15,318 items).** File-name scan reached only agents a…an before I stopped it. Hits so far are non-NYC: Austin, Anchorage, FDA. The scan can be resumed with the `dw.py` logic: grep each item's `/metadata/<id>/files`.

**Common Crawl index:** CC-MAIN-2014-41 … 2018-26, prefix queries on `api/views/43nn-pn8j/`, `resource/43nn-pn8j`, and `nycopendata.socrata.com`. Nearly every request returned 502/504. The one answer was an xx67-kt59 attachment. CC also truncates bodies at about 1 MB, so it is low-value anyway.

**Wayback CDX:** nyc.gov `html/doh/downloads/` (PDFs only) and Yelp `healthscores` feeds (IA was offline).

## Leads not yet exhausted

- Authenticated GitHub code search (`gh` CLI with a token) for `CAMIS,DBA,BORO` and `RECORD DATE` in 2015-03..07 and 2017-11..2018-03 commits.
- Finish the data.world snapshot scan.
- Columbia EDAV spring 2018 and NYC Data Science Academy 2015 student repos (bootcamp blog posts link GitHub).
- Retry Common Crawl when the index is up.
