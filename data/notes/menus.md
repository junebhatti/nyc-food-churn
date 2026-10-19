# Menus, menu prices and price tiers

Reproduce: `.venv/bin/python pipeline/fetch_menus.py [cdx select fetch build proxies tiers]`, plus `pipeline/menus_guides.py cdx|fetch <zagat|nymag>` and `menus_guides.py build`. Every archive.org step is **one client making one request at a time**. `get()` honours `Retry-After` and otherwise backs off exponentially. The fetch steps resume from the JSONL files in `data/raw/menus/_wayback/`.

## Outputs (`data/raw/menus/`)
| file | what |
|---|---|
| `menupages.parquet` | One row per MenuPages restaurant capture: name, address, lat/lon, snapshot_date, price_level ($–$$$$$), median_main_price, n_items_priced, camis, match_method |
| `menupages_items.parquet` | Every priced item: slug, ts, section, item, price (the highest price on the row) |
| `guides.parquet` | Zagat (cost per person, Food/Decor/Service scores) and NY Mag ($–$$$$), matched to CAMIS |
| `camis_proxies.parquet` | Per CAMIS: liquor class, cuisine (old numeric codes mapped to names), chain_n, fast_food, OSM brand |
| `camis_price_tier.parquet` | Per CAMIS: tier and tier_source |
| `tier_source_by_open_year.csv` | Share of CAMIS by tier_source for each first-inspection year |

## MenuPages (Wayback)
- **Scope.** `www.menupages.com/restaurants/<slug>/` and `/menu` cover NYC only, because other cities used subdomains. The CDX index has 154 pages and 199k status-200 rows, all harvested with none missing. That gives **25.2k slugs**, of which 16.4k have a `/menu` capture in 2011–19. Captures are concentrated in 2013, 2015 and 2017; NYC MenuPages ended in 2018. Rows from 2019 on are mostly the Grubhub-era redirect, so I skipped them.
- **Choice of capture.** For each slug I take the latest `/menu` capture in 2011–19. The page carries the header too: name, address, ZIP, lat/lon, cuisine, and the $ key. MenuPages' own $ key is the average dinner entrée price: $ <7, $$ 7–12, $$$ 12–18, $$$$ 18–25, $$$$$ >25.
- **median_main_price.** The median of item prices in sections that are not appetizers, sides, drinks, desserts, breakfast or lunch, and so on, counting only prices from $4 to $250, and only when there are at least 3 such items. It tracks the $ key monotonically, though the spread is wide.
- **Sitemaps.** These are 2022+ Grubhub-era captures, so they don't shortcut the 2011–18 pages.

## Matching to CAMIS (`menus_match.py`)
The DOHMH CAMIS table includes about 21k CAMIS from before 2019 that had no coordinates; I geocoded those with the PAD matcher. Rules, in order:
1. Same BIN or BBL, and name similarity ≥0.80. Similarity is Jaro-Winkler, or 0.90 when the shorter name is contained in the longer.
2. Name similarity ≥0.88 within 80 m.

Ties go to the CAMIS whose inspection years cover the snapshot year. Interim MenuPages match rate is 71% (2,010 of 2,821). By year: 75% for 2017 captures, 62% for 2015, about 0% for the few 2013–14 captures, which are mostly restaurants that had closed by 2011.

## Proxies
- **Liquor.** The NYSLA on-premises license is matched to a CAMIS by the same rules (24.1k of 31.8k licenses, 76%). The class comes from `snap_type`, or from LAMP classes mapped to the most common type seen.
- **Chain.** The normalized DBA appears at 3+ CAMIS; 29% of CAMIS qualify.
- **Fast food.** A quick-service cuisine, a QSR brand regex, or an OSM `amenity=fast_food` match; 27% qualify.
- **OSM.** It has no price tags, but it gives brand and cuisine. The Overture extract kept no brand or price field.

## Tier rule (`menus_tiers.py`)
The first rule that applies wins. Prices are deflated to 2015 dollars with CPI food-away-from-home.
1. A Michelin star, or NYT 3–4 stars → **fine**.
2. MenuPages median main, with ≥5 mains: <$12 cheap, $12–18 mid, $18–30 upscale, ≥$30 fine. A tasting or prix-fixe item ≥$75 also counts as fine.
3. MenuPages $ rating alone: 1–2 cheap, 3 mid, 4–5 upscale.
4. A stated $-level from Google Local (the ratings agent's output) or the Michelin Guide: $ cheap, $$ mid, $$$ upscale, $$$$ fine. Zagat cost and NY Mag $ belong at this level once fetched.
5. Proxy: the modal real tier within the cell fast_food × chain × liquor × cuisine group. Holdout accuracy is about 67%. **Proxies separate cheap from mid only.** They never predict upscale, because even full-liquor, non-chain places are only 18% upscale on menu evidence.

## Ruled out
- **Delivery apps** (Grubhub/Seamless, DoorDash, Uber Eats), **Yelp** and **Google**: excluded by the access rules.
- **Kaggle "Uber Eats USA menus":** a scrape of Uber Eats with an "all rights reserved" license.
- **beridzeg45/nyc-restaurants:** a scrape of Google Maps.
- **Allmenus:** Grubhub-owned, and its terms bar automated access. Archived copies would be allowed, but they would mostly duplicate the MenuPages item prices, so I deferred it.
- **MenuPix:** Cloudflare on the live site, mostly session-ID index pages, and unverified.
- **SinglePlatform:** slugs carry no city.
- **Menuism and Locu:** negligible NYC coverage.
- **Zagat 2019+:** an empty JavaScript shell.
- **NYPL "What's on the Menu?":** CC0, but historic and pre-2011.
- **Yelp Open Dataset:** has no NYC.
