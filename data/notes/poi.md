# Non-government POI sources (NYC food & drink)

Reproduce: `.venv/bin/python pipeline/fetch_poi.py [fsq overture osm ohsome combine]` (about 1 h, 161 MB). Every file has the same columns and is clipped to the boroughs (`extra.borough`). `other_food` holds delis, bodegas, grocery, liquor stores and food trucks; filter on `category_raw` to narrow it.

| file | rows | rest / bar / cafe / bakery / other |
|---|---|---|
| fsq_all (4 releases, 2024-11 → 2025-02) | 133,799 | 64k / 22k / 10k / 10k / 27k |
| overture_2026-09-23.0 (24 releases kept, 2024-02 → 2026-09) | 65,645 | 35k / 6k / 6k / 5k / 13k |
| overture_all (linked across releases) | 91,209 | 48k / 9k / 7k / 7k / 20k |
| osm_overpass (live) | 24,011 | 13k / 2k / 3k / 1k / 5k |
| osm_ohsome (history 2008 → 2026-07) | 33,639 tenures | 19k / 3k / 4k / 2k / 6k |

## Dates and closure signals
- **Foursquare:** 35.9k places have `date_closed`, about 1.2–3.6k a year from 2011 to 2024. It is the date Foursquare *flagged* the closure: the 901 places closed between releases got dates inside that window. So it lags reality by an unknown amount. `date_created` is the date the venue was added to Foursquare (62% fall in 2009–13), not an opening date. Of the 97.7k "open" places, 41.6k were last refreshed before 2020 and are likely partly dead.
- **Overture:** no dates. `operating_status=permanently_closed` appears only from 2026-05 on (2.2k now). Places that disappear between releases give 27k "gone", but this is noisy: ids were reset in 2024-09, 2025-03 and 2025-06. I relink them through meta, Microsoft and Foursquare record ids, but spikes at the resets are artifacts. Releases 2024-09 through 2025-01 are identical. 21k places carry `extra.fsq_ids`.
- **OSM history (ohsome): the best free turnover signal.** One row = one element under one name. 4.2k tenures ended by a rename at the same node (a new business), 5.0k by deletion or retag, and 1.5k carry `disused:`/`was:` tags. Dates are edit dates, so they lag. Coverage grows from 639 POIs (2012) to 26k (2026), so counts before about 2018 reflect mapping effort, not growth.
- **OSM live:** `start_date` on 113 places, `end_date` on 0, `check_date` on 3.5k (proof the place was open on that date), 819 lifecycle-tagged.

## Not obtained
- **FSQ releases after 2025-02** (monthly + `deltas`): gated on Hugging Face or on Foursquare's portal. To get them, accept the terms, put `HF_TOKEN` in `.env.local`, and rerun (untested).
- **Missing Overture releases:** 2024-04..07, 2025-07/08, 2026-06/07 aren't mirrored (the official bucket keeps only the last 3). `changelog/` (added/removed ids per release) is untapped.
- **Yelp Open Dataset:** no NYC. **Google Places:** paid, storing results is forbidden, no dates. **SafeGraph/Advan:** paid or via institutional Dewey access. **Data Axle:** library lookup only.

## Quality
- About 240 FSQ duplicates by name and address; Overture fuzzy duplicates come from merged sources.
- One Overture cluster over-merges 269 ids, though 99% of clusters hold 6 or fewer.
- FSQ "bar" includes lounges, hookah bars and night clubs.

## Recommended use
DOHMH stays the backbone. Use osm_ohsome for turnover at the same address and for closures of bars that don't serve food. Use FSQ `date_closed` to cross-check closure years and to cover bars. Use Overture to check recent presence and closures (2024–26). Treat non-government dates as bounds, never exact.
