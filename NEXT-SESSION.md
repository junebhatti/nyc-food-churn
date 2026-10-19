# Next session

## What this is
**Half-Life**, an atlas of NYC food & drink churn, live at https://half-life-nyc.vercel.app.
- Repo: github.com/junebhatti/nyc-food-churn (private). `data/raw/` and `data/processed/` are gitignored.
- Vercel project `half-life-nyc`, connected to GitHub with Root Directory = `web`. Every push to `main` auto-deploys.
- Design source: `design/design_handoff_half_life/` (Claude Design). Notes on every data source and analysis: `data/notes/`.

## State (2026-10-19)
Data gathering, merge, analysis and the site are all done and live. Nothing is running or paused.

**Site features**
- Hero map (deck.gl):
  - Opens flat and north-up, with water gaps, parks and borough outlines.
  - Rotate/tilt/2D-3D/compass controls.
  - Trackpad: pinch zooms; click the map, then swipe pans and shift+swipe rotates/tilts.
  - View, category, year and neighbourhood filters (`?n=<NTA>`); hover card; click opens the address page.
- Sections:
  - 01 Cursed Addresses
  - 02 Half-life
  - 03 Rent vs Risk
  - 04 Beta
  - 05 Cursed spot test
  - 06 2020 shock
  - 07 Pitch yours (Cox model)
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
- Send sections 02 and 04–07 to Claude Design for a polish pass (built in the design system, never drawn by the designer).
- Dark mode: done 2026-10-19 and follows the system setting (no toggle). Tokens live in `web/app/globals.css`, the map palette in `DARK` in `web/lib/color.ts`, and the two must stay in sync. The dark colours are my reading of the handoff's 1c reference, so confirm them with the designer.
- Check: the mobile flat map rendered blank in the in-app browser's 375px emulation, on both localhost and production, in light and dark. This may only be an emulator quirk; try it on a real phone.
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
