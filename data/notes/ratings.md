# Ratings, critics and buzz

Status 2026-10-18. Reproduce: `.venv/bin/python pipeline/fetch_ratings.py [michelin guide awards nyt eater google]` (about 25 min). Outputs go to `data/raw/ratings/` (11 MB).

**Matching to DOHMH.** `ratings_common.py` does it two ways:
- **With coordinates:** best normalized-name Jaro-Winkler ≥ 0.85 within 80 m, using the latest coordinates per CAMIS.
- **Name only** (lists without coordinates): an exact match on the normalized, space-free name, or JW ≥ 0.95, or a prefix match ("DEL POSTO" → "DEL POSTO RISTORANTE"). It is limited to the borough and prefers a CAMIS that was being inspected in the list year. A spot check found about 5% false matches (e.g. Juni → JUNZI), so check `match_sim < 1` rows before relying on them.

## Pulled

| file | rows | years | what | CAMIS match |
|---|---|---|---|---|
| `michelin_nyc` | 2,460 (224 starred venues) | guide years 2006–2025 | Wikipedia yearly star table: stars 0–3, `closed`, `temp_closed` | 76% of starred venues (81% of those starred 2012 or later); misses are mostly pre-2011 closures and non-NYC places (Blue Hill at Stone Barns) |
| `michelin_guide_nyc_snapshots` | 4,283 (507 venues) | 18 quarterly snapshots, 2022-07 → 2026-10 | full guide: stars, **Bib Gourmand**, "Selected" (only from 2024-06), price $–$$$$, cuisine, address, lat/lon. From git history of github.com/ngshiheng/michelin-my-maps (MIT); Michelin's description text dropped | 86% (geo) |
| `awards_nyc` | 129 | JBF 2010–2026; 50 Best 2002–2024 | James Beard **winners** in Chef/Restaurant categories (Wikipedia); World's 50 Best ranks 1–50 and 51–100 for NYC (the50.com, one page) | JBF 92%, 50 Best 88% |
| `nyt_reviews` | 539 | mostly 2004–2019 (≈30–42 a year 2011–18) | NYT stars (0.25–0.75 = poor/fair/satisfactory), critic, neighborhood, URL. Metadata only, from github.com/maks-p/nyt_restaurant_reviews_NLP (no license stated; review text not kept) | 88% |
| `eater_lists` | 3,120 (1,166 list-venues) | Eater 38: 45 quarters 2015Q2–2026Q4; Heatmaps: NYC 35 (2017Q4–), Brooklyn 36 (2015Q2–), Queens 32 (2018Q1–) | rebuilt from Wayback captures, latest capture per quarter; four page layouts parsed: name, lat/lon, position, snapshot, wayback_url | 38: 83%; NYC 77%; Brooklyn 78%; Queens 69% (geo) |
| `google_local_nyc` | 35,148 businesses | reviews 2002 → 2021-09 (most 2016–21) | UCSD Google Local 2021, NY state, cut to NYC ZIPs + food categories. `avg_rating`, `num_of_reviews`, `price` ($–$$$$ for 22k), hours, category, `state` (**6,116 "Permanently closed", 1,035 "Temporarily closed"** as of the 2021 crawl), plus our **first_review / last_review / p05 / p95** from 8.57M rated reviews | 58% (64% of "restaurant" categories) |
| `google_local_nyc_yearly` | 219k | | business × year: review count and mean rating. Gives a popularity curve over time | via gmap_id |

## Usable for the map now
- **Lifespans of acclaimed places.**
  - Of 170 matched Michelin-starred venues, 61% are still in live DOHMH. Wikipedia marks 28% closed, and only 5% disagree with DOHMH.
  - About 70–75% of places on an Eater 38 or Heatmap list are still open.
- **Buzz timeline.** Each venue's quarters on Eater lists, years on Michelin, plus JBF and NYT years give "acclaimed in year X". Use these to compare survival against similar unlisted places.
- **Review-based proof of life** (Google Local; check the DOHMH join before using):
  - For DOHMH closures before 2021, the last Google review falls a median 357 days after the last inspection. Half are within a year of it, so it narrows closure dates.
  - The first review is often *before* the first DOHMH inspection (median 288 days). This is likely because Google reuses a place for a successor business. Treat `first_review` as an upper bound on the opening only when it agrees with DOHMH.
  - Of "Permanently closed" places matched to DOHMH, 27% are still in DOHMH after 2022. Some are stale Google flags; others are wrong matches.
- **Price level.** Google 2021 has `$`–`$$$$` for about 22k places; Michelin has it for guide places.

## Needs a key or money
- **NYT Article Search API.** Free key: developer.nytimes.com → create account → Apps → New App → enable Article Search → put it in `.env.local` as `NYT_API_KEY`. Reported limits are 5 requests/min and 500/day.
  - Try `fq=section_name:("Food") AND type_of_material:("Review")` and confirm with one test call.
  - The response has no stars field, so it gives URLs, dates and headlines only. Stars would mean reading paywalled pages, which we don't do.
- **Foursquare Places API.** It has rating, popularity, price, hours, stats and tips.
  - Pricing: about 500 free calls (Foursquare also says 10k), then $15 per 1,000 Pro calls and $18.75 per 1,000 Premium. Rating, popularity and stats are Premium fields.
  - The open FSQ OS Places (Apache-2.0, already in `data/raw/poi/`) has none of these fields.
- **Yelp Places API.** $229–643 a month, with a 30-day trial of 5,000 calls. Content may be cached for 24 h only; only business IDs can be kept. Not storable.
- **Google Places (New).** Rating, user rating count and price are Enterprise SKUs at $20 per 1,000 calls. Only `place_id` may be stored (lat/lng for 30 days). Not storable.
- **Tripadvisor Content API.** 5k free calls a month, with a card on file and required attribution. Caching terms are unclear, and the legacy API was reportedly being replaced in 2026.
- **OpenTable:** partners only. **Resy:** no public API; unofficial endpoints break its terms.

## Beli: how to get your own data
Beli has no public API, partner program or in-app export. Its terms ban scraping and storing content.
1. Email **support@beliapp.com** from your account's address. Subject: "Data access / portability request". The privacy policy, effective 2024-03-05, lists access and portability ("machine-readable copy").
2. Ask for CSV or JSON of your ranked list with scores and rank order, notes, visit dates, and your want-to-try list.
3. Answer their identity check. The policy states no deadline. Cite CCPA (45 days) if you're in California, or GDPR (1 month) if you're in the EU, and follow up.
4. When the file arrives, drop it in `data/raw/ratings/beli/` and match it with `ratings_common.match_name`.

## Ruled out
- **Yelp Open Dataset:** no NYC.
- **Kaggle "yelp-nyc-labelled"** (YelpNYC spam corpus): unknown license, redistributed Yelp content, anonymized business IDs.
- **NYPL "What's on the Menu?"** (CC0): downloaded and checked. Only 39 menus date from 2000 or later; it is a pre-1990 collection. Not kept.
- **No open NYC menu-price dataset** found for 2011 or later.
- **The Infatuation, Pete Wells' top-100 lists, current NYT stars, Resy and OpenTable lists:** only available by scraping against site terms or past paywalls. Not pulled. Wayback snapshots of the Infatuation guides would be the legitimate route if needed.
- **Michelin 2026 NYC guide:** not yet on Wikipedia. The snapshot file has the live guide.
- **World's 50 Best 2025:** not on the previous-lists page.
- **Google Local** is a research dataset; the lab asks for citation: Li et al., UCTopic, ACL 2022; Yan et al., Personalized Showcases, SIGIR 2023. Keep it out of anything commercial.
