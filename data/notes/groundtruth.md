# Ground truth: dated opening / closing reports (blogs, Eater, Grub Street)

Status 2026-10-18 (about 22:30 EDT). Reproduce:

```
.venv/bin/python pipeline/fetch_groundtruth.py            # blogs wayback match eval manifest
.venv/bin/python pipeline/gt_wayback.py --offline          # re-parse cached CDX pages only
```

Code: `gt_common.py` (HTTP clients, normalisation, event regexes), `gt_blogs.py`, `gt_wayback.py`,
`gt_dohmh.py` (CAMIS / business windows), `gt_match.py`, `gt_eval.py`, `fetch_groundtruth.py`.
Output is in `data/raw/groundtruth/` (29 MB): parquet files, `summary.json`, `manifest.json`, and `_cache/` (feed pages and CDX pages, metadata only).

**Only metadata is stored:** title or URL slug, date, URL, labels/tags, and the extracted name. No article text is stored, and blog summaries are dropped on fetch.

## Sources and access

| source | how | posts | dates | used for events |
|---|---|---|---|---|
| EV Grieve | Blogger JSON feed (every post: title, date, labels) | 42,303 | 2007 → 2026-10 | title + labels ("restaurant closings", "closings 20xx", "new restaurants", per-venue labels) |
| Jeremiah's Vanishing NY | Blogger JSON feed | 3,209 | 2007 → 2021 | titles (few name venues) |
| West Side Rag | WordPress REST, categories OPEN/CLOSED + FOOD | 2,594 | 2011 → 2026 | titles |
| Tribeca Citizen | WordPress REST, category Restaurant/Bar News | 6,271 | 2009 → 2026 | titles |
| Greenpointers | WordPress REST, Eat & Drink + Local Business | 2,697 | 2010 → 2026 | titles |
| Eater NY | **Wayback CDX URL index only**: post date and headline slug from the URL | 8,467 candidate URLs | 2005 → 2025-06 | slugs |
| Grub Street | Wayback CDX URL index only | 97 | 2006 → 2009 | not usable yet |

**robots.txt.** It was checked on 2026-10-18.
- **ny.eater.com, grubstreet.com, brownstoner.com:** they disallow Claude agents (`ClaudeBot`, `Claude-User`, `Claude-Web`), and brownstoner also disallows `archive.org_bot`.
  - **Eater and Grub Street:** none of their pages, live or archived, were fetched. The pipeline reads only archive.org's CDX URL index. Eater URLs carry the day (`/YYYY/M/D/id/slug`) or the month (`/archives/YYYY/MM/slug.php`, dated by its first capture). Grub Street URLs carry the month.
  - **Brownstoner:** skipped.
- **Sunnyside, Astoria, LIC and Jackson Heights Post:** they block Claude, so they were skipped.
- **Bowery Boogie:** now a static placeholder; skipped.
- **Ditmas Park Corner:** its API returned nothing; skipped.
- **Bushwick Daily:** allows Claude, but its API did not answer; not pulled.

**archive.org.** There is one client (`gt_common.ia_get`). It waits at least 2.5 s between requests and honours Retry-After, with exponential backoff on 429 and 5xx. IA returned 503 for most of the evening, so the crawl ran slowly. **`www.grubstreet.com/20*` is unfinished: 2 of 172 CDX pages done.** Rerunning `gt_wayback.py` resumes from the cache. Eater's 85 pages are complete.

## Method
- **Events** come from regexes on the title or slug (`gt_common.EVENT_RE`), checked in this priority order: notclose › reopen › relocate › temp › close › for_rent › open. "Coming soon" and future-dated openings ("opens in September", "bringing", "giving way") become `coming`. Temporary closures (renovation, fire, DOH or SLA, "still closed") become `temp`.
  - EV Grieve's closing and new-restaurant labels add events when the title is neutral.
  - Roundups are flagged and excluded from accuracy: "Seen & Heard", "The Shutter", "… and more", three or more commas.
- **Names** are found by dictionary lookup. Every 1–6-word n-gram of the title (and each label whose distinctive word also appears in the title) is looked up in DOHMH name variants: the full name, the name without generic suffixes like RESTAURANT/BAR/CAFE, and the first two words of names of three or more words. Dropped as generic:
  - single dictionary words;
  - place names;
  - names in more than 40 titles;
  - chains with more than 8 businesses, unless a street in the title pins down a single location.
- **Location.** The neighbourhood blogs are limited to their ZIPs (EV 10003/09/02/12, UWS, Tribeca/FiDi, Greenpoint/Williamsburg). Eater and Vanishing NY are citywide and need a unique name. A street named in the title must match the business's street; a mismatch is flagged and excluded. Title addresses go through PadGeocoder (362 geocoded, used to break ties).
- **Time plausibility** (necessary, and it truncates errors beyond 3 y):
  - close: F ≤ post + 30 d and L ≥ post − 3 y.
  - open: last listed ≥ post − 30 d and |F − post| ≤ 3 y.
- **Coverage cutoff.** Posts before 2011-07 are not matched, because DOHMH has almost none of those businesses.
- **Business, not CAMIS.** CAMIS with the same name core at the same building and street are merged. On the current union, CAMIS-level closures number 53,683 and business-level closures 47,984. So about 11% of CAMIS "closures" are permit changes.
- **Window** (`gt_dohmh.py`): L is the last real inspection. U is the first FULL copy after the last listing. Partial or derived copies (akkaluzny, vsm1013, miguel75an, kylewbrown, lehman_*, residentmario, tzstatsads, and any with PARTIAL/DERIVED in its notes) count only as presence.
- **Precision.** Hand checks of 40 blog matches and 25 Eater matches found about 88–92% correct. Errors are name reuse (Billy's Antiques → BILLY'S BAKERY; since fixed), list posts and same-name successors.

## Results (union and manifest re-read at 22:2x; 85,237 CAMIS → 79,076 businesses)

**Match rate** (non-roundup open and close posts from 2011-07 on): **35%** match a DOHMH business (6,417 posts).
- Neighbourhood blogs (close posts): Greenpointers 56%, Tribeca Citizen 45%, West Side Rag 31%, EV Grieve 23%. EV Grieve covers every kind of shop.
- Eater: 32%.
- Another 4–13% match only an SLA on-premises licence (bars without a food permit).

**Closures**: 1,027 businesses with a closing post; 905 of them are DOHMH-closed.

| period of post | n | inside [L,U] | ±60 d | post < L | median window | median rel. position | median err L / mid / U (d) |
|---|---|---|---|---|---|---|---|
| all | 905 | **85%** | 88% | 12.5% (7% by >1 y) | 428 | **0.37** | −148 / **+44** / +254 |
| 2015-03..08 | 27 | 93% | 93% | 7% | 265 | 0.48 | −112 / +4 / +139 |
| 2016-04..12 | 49 | 86% | 90% | 14% | 345 | 0.33 | −108 / +51 / +211 |
| 2017-10..2018-07 | 86 | 81% | 87% | 16% | 370 | 0.29 | −79 / +49 / +178 |
| COVID 2020-03..2021-06 | 94 | 93% | 93% | 7% | 777 | 0.40 | −282 / +58 / +394 |
| 2011–14 | 199 | 73% | 75% | 25% | 346 | 0.27 | −78 / +60 / +242 |
| 2022–26 | 187 | 94% | 97% | 4% | 513 | 0.50 | −231 / 0 / +238 |

The median absolute error of the midpoint is 93 d, against 181 d for L and 259 d for U.

**False closures**
- 7.2% of DOHMH-closed businesses that have a closing post later got a reopen or relocate post: 5.9% reopen, 1.9% relocate.
- Among all 1,773 DOHMH-closed businesses matched by any post, 183 (10%) have a reopen or relocate post after L.
- 12% of closing posts match a business that DOHMH still lists. 80 of those 122 were inspected more than 180 d after the post, so they reopened or the report was wrong.

**Missed businesses** (food closing posts, not roundups, 2011-07 on, no DOHMH match):
- No match: 40–55% by source.
- Still unmatched under a loose test (any distinctive title word against a business in the area and time): **24% EV Grieve, 29% Greenpointers, 33% West Side Rag, 38% Tribeca Citizen, 27% Eater.**
- This is an upper bound. It includes shops, food halls, bars without a permit, and names the extractor cannot parse.

**Openings**: 730 businesses, posts from 2012 on.

| | n | F − post (median, IQR) | within 90 d | first listed − post (median) | abs err | within 90 d |
|---|---|---|---|---|---|---|
| all | 730 | **+75** (−4..+231) | 45% | **−4** | 50 | **68%** |
| 2011–14 | 158 | +12 | 63% | −13 | 46 | 69% |
| 2015–19 | 285 | +58 | 54% | +3 | 43 | 74% |
| 2020–21 (COVID) | 96 | **+346** | 8% | +17 | 100 | 47% |
| 2022–26 | 191 | +136 | 36% | −17 | 43 | 68% |

"First listed" = min(first copy that lists the CAMIS, often with a 1900-01-01 "not yet inspected" row; F). Since 2020, new places sit in the dataset for months before their first inspection.

## Recommended pipeline corrections
1. **Closure date: use L + 0.37·(U − L), not L or U.** The midpoint is about 6 weeks late on median and is fine for 2022+.
   - In the 2016–18 gap periods, closures fall earlier in the window (0.29–0.33).
   - Report the window as the uncertainty.
2. **Opening date: use the first listing (min with the first inspection), not the first inspection.** The first inspection lags by 2–5 months normally, and by about a year for 2020–21 openings.
3. **Merge same-name, same-address permits before counting churn** (−11% closures).
4. **Trust 2011–14 closures less.** 25% of reports predate L, from name reuse and reincarnations.
   - Gap-period closures are not less accurate in hit rate (81–93% inside), but their windows are longer, so their point estimates are less certain.
   - COVID windows are about 2 years long. Narrow them with PPP/RRF/311 (see signals.md).
5. **Flag closures followed by a same-name reappearance nearby** (relocations: about 2% of closures) and treat "reopened" closures (about 6%) as interruptions.

## Files
- `posts_blogs.parquet`, `posts_wayback.parquet`: raw post metadata.
- `events.parquet`: posts with an event, plus:
  - flags: `roundup`, `pre_coverage`, `food_post`, `street_conflict`;
  - the match: `matched_name`, `biz`, CAMIS list, F / first_seen / L / U;
  - `sla_name`, `loose_dohmh_name`.
- `eval_closures.parquet`, `eval_openings.parquet`: one row per business, from its earliest post.
- `summary.json`: every metric above, including by source.
- `manifest.json`.

## Caveats and next steps
- Name extraction from headlines is the main source of misses. Eater roundups ("The Shutter", weekly closings lists) carry names only in the body, which we do not fetch.
- The time-plausibility filter caps errors at 3 y. Match precision is about 90%, so some "post < L" cases are wrong matches.
- Next steps:
  - finish the `www.grubstreet.com` CDX pages (`gt_wayback.py` resumes);
  - try Bushwick Daily again, since its robots.txt allows us;
  - add Gothamist, whose robots.txt has no Claude block, possibly via its sitemaps.
