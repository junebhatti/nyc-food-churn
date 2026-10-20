# Next Session — NYC Turnover (2026-10-20)

## Where things stand
NYC Turnover (formerly Half-Life) is live at https://half-life-nyc.vercel.app; every push to `main` auto-deploys (Vercel project `half-life-nyc`, root `web/`). Everything is committed and pushed; nothing is running. Seven QA agents tested the live site on 2026-10-20: it's solid as a portfolio link, but has 5 launch blockers (below) to fix before posting to Reddit/HN or pitching press. Home `/` is the map alone; the six stories are separate pages (`web/lib/stories.ts`); ~35k address pages at `/place/<id>`; Ask panel at `web/app/api/ask/route.ts` with its briefing in `web/lib/ask/context.ts`.

## Done this session (2026-10-19/20)
- Linked from junaidrbhatti.com/projects (personal-site repo, entry "NYC Turnover").
- Renamed to NYC Turnover; dark mode (`web/app/globals.css` + `DARK` in `web/lib/color.ts`, keep in sync).
- Trackpad gestures, no map buttons — `web/lib/useTrackpad.ts`; height follows the view — `web/lib/metrics.ts`.
- Stories split into pages; Stories menu + Ask button in header — `web/components/TopBar.tsx`; Pitch yours removed.
- Streets at building zoom — `pipeline/export_streets.py`, `streets.json`; one-row-per-business timelines — `web/components/cursed/Timeline.tsx`.
- Cursed addresses map (fly-to, hover, pinch, streets) — `web/components/cursed/CursedMap.tsx`; 2020 as candlesticks — `web/components/sections/Covid.tsx`.
- 7 research agents → "Deeper findings" in the Ask briefing; data fixes (bar neighbourhoods, cuisine synonyms, 2026 bodegas).
- data/raw backed up to iCloud Drive `Backups/half-life-data-raw-2026-10-19.zip`; Claude Design brief in `design/polish_brief/` (not sent; mentions the removed Pitch yours).

## Next steps (in order)
**Launch blockers**
1. DONE 2026-10-20: split addresses. `building_key()` in `pipeline/build_buildings.py` gives lot/text-keyed businesses a BIN via PAD address match or single-building lot; duplicates 3,437 → 76 (37 are two BINs at one address, left so `b…` ids stay stable); address pages 45,288 → 35,278 and ~3k old `l…` links now 404. Side effect: the "cursed spot" effect was mostly a keying artifact (DOHMH places without a BIN are 91% closed, 40% in year 1); year-1 risk for 3+ prior tenants fell from 3.0× to 1.1× (Cox 2.9 → 1.3). `/cursed-spot` copy, its share headline and the Ask briefing now match. Cursed top 12 is all new (#1 109-11 Farmers Blvd, 9 tenants) and includes some two-storefront buildings (120 Macdougal, 153 Centre St); consider tightening `conc <= 2` in `export_site.cursed()`.
2. DONE 2026-10-20: bars reconciled. The Half-life row is now "Bar (licence only)" (`FAMILY_LABEL` in export_site.py), the briefing explains both figures, and the Manhattan median says 6.5.
3. DONE 2026-10-20: laptop widths. The home control bar wraps below 1280px; Rent vs risk goes 3-column only from 1360px (the map spans below); Cursed list 320px plus a compact table; Beta columns reworked with "Show all"; header no longer wraps.
4. DONE 2026-10-20: share previews. Site and per-story OG/Twitter tags and images (`web/app/_og/`, `opengraph-image.tsx` per route), robots and sitemap, per-address titles, descriptions and images (`web/app/place/[id]/data.ts`); unknown ids 404.
5. DONE 2026-10-20: phones. Charts draw at measured width (`web/lib/useWidth.ts`); on the Cursed map one finger scrolls the page and pinch zooms; a row tap scrolls the map into view; copy says tap; 2020 candles are tappable with a readout; tap targets are at least 40px.

**Polish**
- Ask: DONE ("the site's data" wording, 30 s timeout with 1 retry, `maxDuration`, Escape closes, focus moves in and out). Still open: tell visitors there's no follow-up memory.
- Stories menu: return focus on Escape, close when focus leaves.
- `?n=` deep link doesn't fly on first load (`HeroMap.tsx` fly effect runs on first DeckGL mount); hover card doesn't clamp at edges (`HoverCard.tsx`); pinch zooms to centre not cursor (`useTrackpad.ts`); "Median lifespan 5.9" is static (`Hero.tsx`).
- Timelines: DONE (closed rows with no close date end at open + life; labels go inside the bar when there's no room on either side).
- A11y: story pages have no h1; maps need `role="img"` + label; light `--bodega-text` 4.29:1 (→ ~#856210) and `--bodega` marks 1.72:1; no `prefers-reduced-motion`.
- Cursed map: hover card sticks after a fly; overlapping dots (3/12, 9/11) at city zoom.
- `/half-life` Year-opened curves extrapolate to 10y for recent cohorts; `/beta` prose vs Ridgewood; `/cursed-spot` 1× line cuts labels; candles off by 2–13 places per period.
- Search: GeoSearch takes the first result with no quality check; "katz" ranks Jeffrey Katz first; "NA" business names; mixed "2nd Ave"/"2 Avenue".
- Add `nycturnover.vercel.app` in Vercel → Settings → Domains (user's step), then switch the personal-site link.

- Address redirects: `web/public/data/aliases.json` maps 13,069 old address ids (renamed by the 2026-10-20 merge) to their new page; `/place/<old>` sends a 308 (`missing()` in `web/app/place/[id]/page.tsx`). It's a one-time map, so keep it; reruns keep `b…` ids stable.
- Story 05 now says the "cursed spot" is mostly a myth (1.1× year-1 risk after 3+ failures); its 45%/26% predecessor figures are hardcoded in `CursedTest.tsx` and the briefing, so update them if the pipeline is rerun.
- Left from the data-fix session (needs a full rerun): bars have no census tract or BIN; about 110 DOHMH rows have borough "0"/"MISSING".

## Decisions made (and why)
- Pending, user's call: headline survival 89/67/55% (5.9y) is generous vs 84/64/52% (5.4y) timed from first inspection — switch or footnote before press.
- Places data stays in git — `.git` is ~22 MB; Blob adds a service for no gain yet.
- "Half-life" stays as story 02's name — it's the statistic, not the brand.

## Ideas (from the ideas agent; ranked by impact for effort)
- Features: OG share card per address ("Here lies 214 Bedford Ave: 6 tenants"); "What survives here?" odds on address pages; neighbourhood vs neighbourhood; time-lapse video export; monthly "newly closed" feed + RSS; embed widgets; "Survivors" hall of fame (Nathan's 1934).
- New data: DOB sidewalk sheds; marshal commercial evictions (6z8x-wfk4); ACS income/education change by tract; rezonings (ZAP hgx4-8ukb); certificates of occupancy; rodent inspections; congestion-zone entries (2025); BID boundaries.
- Launch: lead with one finding (not the "3× cursed spot", which was an artifact; candidates: chains about a third less likely to close, or the last tenant's lifespan predicting the next, 45% vs 26% 3-year closure) to Eater NY/Gothamist/The City/Viewing NYC; r/nyc + r/dataisbeautiful time-lapse; Show HN on rebuilding a deleted dataset; BetaNYC Open Data Week (March); one-page methods note for recruiters/VCs.

## Gotchas
- Dev server (`web` in `.claude/launch.json`, port 3007) sometimes serves stale modules after edits — restart it if a change doesn't show.
- The in-app browser pane only renders deck.gl while visible; for reliable checks use headless Chrome over CDP (template: session scratchpad `agents/qa/cdp-template.mjs`, may be gone — rewrite from `node` + `--remote-debugging-port`).
- Rebuild order: `pipeline/fetch_analysis_inputs.py` → `build_lifespans, build_businesses, build_bodegas, build_buildings, build_attach, build_checks` → `analysis_survival, analysis_cox, analysis_beta` → `export_site, export_places, export_analysis` (`export_streets` only for street refreshes); run with `../.venv/bin/python -W ignore` from `pipeline/`, then `cd web && npm run build`.
- Next.js 16 + Cache Components: URL-reading code needs Suspense; dynamic routes need a `generateStaticParams` entry; read `web/node_modules/next/dist/docs/` first.
- Secrets: root `.env.local` (GITHUB_TOKEN), `web/.env.local` (ANTHROPIC_API_KEY, VERCEL_OIDC_TOKEN) — never print. No review text or ratings on the site (research-only sources). Ask API costs money and is limited to 10/hour per IP.
