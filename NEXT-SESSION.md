# Next session

## What this is
**Half-Life**, an atlas of NYC food & drink churn, live at https://half-life-nyc.vercel.app.
- Repo: github.com/junebhatti/nyc-food-churn (private). `data/raw/` and `data/processed/` are gitignored.
- Vercel project `half-life-nyc`, connected to GitHub with Root Directory = `web`. Every push to `main` auto-deploys.
- Design source: `design/design_handoff_half_life/` (Claude Design). Notes on every data source and analysis: `data/notes/`.

## State (2026-10-19)
Data gathering, merge, analysis and the site are all done and live. Nothing is running or paused.

**Site features**
- Home `/` is the full-screen map (deck.gl):
  - Opens flat and north-up, with water gaps, parks and borough outlines.
  - Gestures, with no on-map buttons (changed 2026-10-19, `web/lib/useTrackpad.ts`): drag pans, pinch zooms, a two-finger sideways swipe rotates, a vertical swipe tilts (up tilts into 3D), and a mouse wheel zooms. The map takes every wheel event over it.
  - View, category, year and neighbourhood filters (`?n=<NTA>`); hover card; click opens the address page.
- Each story has its own page (split out 2026-10-19). The list is `web/lib/stories.ts`, the frame is `web/components/StoryPage.tsx` (header, then prev/next, then footer), and the header's "Stories" menu (☰ on phones) is `web/components/StoriesMenu.tsx`:
  - `/cursed` 01 Cursed Addresses
  - `/half-life` 02 Half-life
  - `/rent-vs-risk` 03 Rent vs Risk
  - `/beta` 04 Beta
  - `/cursed-spot` 05 Cursed spot test
  - `/2020` 06 2020 shock
  - `/pitch` 07 Pitch yours (Cox model)
- Address pages `/place/<id>` for ~45k buildings: timeline, business cards with DOHMH grades, acclaim and Google/Yelp links, and nearby addresses.
- Search box: addresses, business names, neighbourhoods; NYC GeoSearch fallback.
- Neighbourhood panel under the map when a neighbourhood is selected.
- "Ask about the data" side panel: `web/app/api/ask/route.ts`.
  - `claude-opus-5-5`, low effort, short answers, refusal fallback, input caps, best-effort per-IP limit of 10/hour.
  - Briefing: `web/lib/ask/context.ts` (update its numbers if the pipeline is rerun).
  - Key: `ANTHROPIC_API_KEY` in `web/.env.local` and in Vercel (Production). The user set up an Anthropic workspace with a monthly spend cap (see `docs/anthropic-key-setup.md`).
- Mobile: flat hex map, sticky scrubber within the hero, tap sheet, search, picker.

## Rebuild everything (about 10 minutes, all local)
```
.venv/bin/python -W ignore pipeline/fetch_analysis_inputs.py base cuisine chains operators operators2 storefront size rent age rrf
cd pipeline
../.venv/bin/python -W ignore build_lifespans.py && ../.venv/bin/python -W ignore build_businesses.py && ../.venv/bin/python -W ignore build_bodegas.py
../.venv/bin/python -W ignore build_buildings.py && ../.venv/bin/python -W ignore build_attach.py && ../.venv/bin/python -W ignore build_checks.py
../.venv/bin/python -W ignore analysis_survival.py && ../.venv/bin/python -W ignore analysis_cox.py && ../.venv/bin/python -W ignore analysis_beta.py
../.venv/bin/python -W ignore export_site.py && ../.venv/bin/python -W ignore export_places.py && ../.venv/bin/python -W ignore export_analysis.py
```
Then `cd web && npm run build`, commit and push.

## Open items (none started)
- Design polish: the brief for sections 02 and 04–07 is written, with current screenshots, in `design/polish_brief/`. It hasn't been sent yet: the user takes it to Claude Design, and the returned handoff gets built in code.
- Dark mode: done 2026-10-19 and follows the system setting (no toggle). Tokens live in `web/app/globals.css`, the map palette in `DARK` in `web/lib/color.ts`, and the two must stay in sync. The dark colours are my reading of the handoff's 1c reference, so confirm them with the designer.
- Mobile map (resolved 2026-10-19): it was never broken. The in-app browser pane was hidden, and a hidden page gets no requestAnimationFrame, so deck.gl never measured or drew. Headless Chrome renders the map fine. The same investigation found a real bug: the mobile neighbourhood `<select>` grew to its longest option (487px) and widened the page to 503px. Fixed with `min-w-0`.
- Mobile map: no rotate/tilt controls (flat by design).
- Optional data: Zagat/NY Mag archived menus (stages exist in `pipeline/menus_wayback.py`; never run). Foursquare releases after 2025-02 need an HF_TOKEN.
- Optional: point a subdomain of junaidrbhatti.com at the site. (It is already linked from junaidrbhatti.com/projects, pushed 2026-10-19.)
- Backup: `data/raw` (3.0 GB, 2,996 files) was zipped on 2026-10-19 to iCloud Drive `Backups/half-life-data-raw-2026-10-19.zip` (2.3 GB). `unzip -t` passed and the file counts match. Make a new one if raw data is added.
- Repo size: decided 2026-10-19 to keep `web/public/data/places/` in git. It has been committed once and the whole `.git` is 22 MB because the JSON compresses well. Moving it to Blob would add a token, an upload step and a second service. Revisit if `.git` grows past a few hundred MB.

## Constraints
- Raw data includes research-only sources (UCSD Google Local, the NYT reviews copy). Publish derived stats only, with credit. No review text or ratings on the site; link out instead.
- Keep files under about 400 lines (`pipeline/dohmh_extra.py` is 562; split it when touched).
- `.env.local` (root) holds GITHUB_TOKEN; `web/.env.local` holds ANTHROPIC_API_KEY and VERCEL_OIDC_TOKEN. Never print them.
- `web/` is Next.js 16 with Cache Components: anything reading the URL needs a Suspense boundary, and dynamic routes need at least one `generateStaticParams` entry. Read `web/node_modules/next/dist/docs/` before using unfamiliar APIs.
