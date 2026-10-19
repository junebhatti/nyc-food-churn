# Next session

## Goal
A Next.js + deck.gl atlas of NYC food & drink churn, styled like the oil visualizer (github.com/Dario-Soatto/oil-visualizer) with its own palette. A scrolling story that ends in an explorer:
- 3D churn map: column height = businesses per building since about 2011
- Survival curves and median lifespan by neighborhood
- Neighborhood risk "spreads" vs storefront rent
- Beta by group and neighborhood (the user's favourite)
- Survival by group: cuisine, cheap → fine, chain vs independent, first-time vs multi-unit operator, storefront history ("cursed spot" × Lindy/age)
- Later: a "pitch your restaurant" tool
Standalone project deployed to Vercel and linked from the personal site. Repo: github.com/junebhatti/nyc-food-churn (private; data/raw is gitignored).

## State (2026-10-18)
Data gathering is done. Every source has a note in `data/notes/`; start with `audit.md`, `analysis_inputs.md` and `groundtruth.md`.
- DOHMH union: `data/raw/dohmh/union_inspections.parquet`, 85,259 CAMIS, built from 76 copies 2012-07 → 2026-10. OATH tickets add ages back to 1997 (`data/raw/early/`).
- Benchmarks: 1.3–1.45× Census CBP counts everywhere; exit rate 13.5%/yr vs BDS 11.9%.
- Ready-made analysis inputs: `data/raw/analysis_inputs/` (cuisine families, chains, operators, storefront history, rent by NTA-year, RRF design).

## Paused on purpose (resume these first, in parallel)
1. **Menu download** (archive.org MenuPages): 16,439 of ~25,200 restaurants fetched, records verified clean. The tuning agent found **4 workers runs at ~4.6 pages/s with 0% errors** (vs 1.2/s with 1 worker). Resume with:
   `cd pipeline && ../.venv/bin/python -u menus_wayback.py fetch 0 4 >> ../data/raw/menus/archive_run.log 2>&1`
   That's ~35 min for the rest. Then the Zagat/NY Mag CDX + fetch stages (see data/notes/menus.md). Then rebuild the tiers:
   `.venv/bin/python pipeline/fetch_menus.py build tiers && .venv/bin/python pipeline/menus_guides.py build && .venv/bin/python pipeline/fetch_menus.py tiers`
   Drop to 3 workers if anything else is hitting archive.org; back off on any 429/503.
2. **Taxi + Uber/Lyft foot-traffic data:** the user asked for an agent to dig into these errors and get them right (details in data/notes/traffic.md, "Status when paused"):
   - green cab 2013-10 returns 403 and the retry loop never skipped it
   - the FHV (Uber/Lyft) Socrata query hung
   Fix both, finish `pipeline/traffic_tlc.py` run(), then build `data/raw/traffic/traffic_by_tract_year.parquet` (the composite foot-traffic index). Subway, jobs, Citi Bike and DOT pieces are already done.

Stopped for diminishing returns: bars (data/notes/bars.md) and DOHMH gaps round 3 (dohmh_gaps2.md).

## Site (2026-10-19)
- Live: https://half-life-nyc.vercel.app (Vercel project `half-life-nyc`, team junaidbhatti). Connected to GitHub with Root Directory = `web`: every push to `main` auto-deploys to production, and other branches get preview URLs.
- Data: `pipeline/export_site.py` writes `web/public/data/`. Rerun it after any `build_*` change, then commit and push to redeploy.
- Built sections: hero map + controls, 01 Cursed Addresses, 03 Rent vs Risk, mobile. Not designed yet: 02 Half-life, 04 Beta, 07 Pitch yours, and dark mode.
- The Rent vs Risk headline was changed to match the data: pricier areas are a little safer, but rent doesn't predict closure once other factors are controlled for.

## Next steps
0. **Merge pipeline is BUILT** (2026-10-19): see data/notes/merge.md for commands, outputs (data/processed/) and validation. 69,166 businesses, 39,605 buildings. Rerun build_attach.py + build_checks.py after the menu tiers and traffic index finish.
1. Rerun a quick audit over everything (data/notes/audit.md lists what to check), then commit and push.
2. Offer the user a backup zip of `data/raw` (about 2.5 GB, not in git).
3. (done) Build the merge pipeline into one business table, applying the corrections in groundtruth.md:
   - merge same-name, same-address permits (−11% closures)
   - closure date = L + 0.37·(U − L) (≈0.3 for 2016–18)
   - opening = earlier of first listing (incl. 1900-01-01 rows) and first inspection
   - flag reopenings and relocations
   - use PARTIAL/DERIVED copies only as proof of life
   - normalize `boro`; drop (0,0) coordinates
   - correct the 2020–23 delayed purges
   - rerun signals/ratings CAMIS matching on the 85k union
4. (done 2026-10-19, see data/notes/analysis_first_pass.md) First analysis pass: Kaplan-Meier survival by group, Cox model, cursed-spot × age, beta by group and neighborhood. Pick the 3–4 strongest findings, then design the page.

## Constraints
- Raw data includes research-only sources (UCSD Google Local, the NYT reviews copy). Publish derived stats only, with credit.
- Keep files under about 400 lines (`pipeline/dohmh_extra.py` is 562; split it when touched).
- `.env.local` holds GITHUB_TOKEN (read-only, public repos); never print it.
