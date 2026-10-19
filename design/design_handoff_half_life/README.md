# Handoff: Half-Life — an atlas of NYC restaurant churn

## Overview
A scrolling data story about NYC food-business churn, ending in an explorer, framed in finance terms: each storefront is a loan with a closure rate, a credit spread and a beta. This handoff covers the **approved** pieces only:

- **Hero + always-on controls** (canvas artboard `1a`, "Plaster & Awning")
- **01 Cursed Addresses**: leaderboard + timeline card (`1d`)
- **03 Is the Rent Worth the Risk?**: side panel + scatter + neighborhood relief map (`3a`)
- **Mobile hero + year scrubber** (`1f`) and **mobile tap sheet** (`1g`)

Rejected or not needed: `1b`, `1c` (except as a dark-mode reference, see Tokens), `1e` (superseded by `3a`), and all of Turn 2 (`2a`–`2c`).

Target stack: **Next.js (App Router) + deck.gl + Tailwind**.

## About the design files
`Half-Life Directions.dc.html` is a **design reference built in HTML**: a pan/zoom canvas of artboards. It is not production code. The maps are hand-projected SVG on a **fake NYC outline with fake data** so the look and interactions could be prototyped. Rebuild them in deck.gl on real geography. Open the file in a browser (it needs `support.js` next to it) to see the live interactions. All four artboards share one state, so scrubbing any year scrubber updates every map.

## Fidelity
**High-fidelity** for type, color, layout, copy and interaction. **Low-fidelity** for geography and numbers: every figure, address and business name is a placeholder.

---

## Design tokens

### Color: light (paper), the primary theme
| Token | Hex | Use |
|---|---|---|
| paper | `#F3EEE4` | Page background |
| paper-raised | `#FBF8F2` | Cards, hover card, selected rows |
| ink | `#1C1B18` | Text, 1px rules, strong borders, primary controls |
| ink-2 | `#3F3B35` | Body prose |
| muted | `#5A554C` | Labels, axis ticks, secondary text (passes 4.5:1 on paper) |
| rule | `#CFC6B6` | Hairline dividers |
| rule-soft | `#E4DCCD` | Table row dividers, bar tracks, vacancy hatch |
| awning | `#B8321D` | "Deadly", closings, section kickers, short lifespans |
| deli | `#1E5B3A` | "Safe", openings, long lifespans |
| bodega | `#E2B13C` | Fill only, **never text on paper**. Mid lifespans, cheap & deadly dots |
| bodega-text | `#8F6A12` | When bodega must be text ("Cheap & deadly" label) |
| land | `#E7E0D2` | Map land plate |
| land-edge | `#CEC4B2` | Map plate's extruded edge |
| dead | `#DAD2C3` | A building that is dark (closed) in the scrubbed year |

**Map diverging ramp** (low → high): `#4F7D5E` → `#F4EEE2` → `#C0402A`, interpolated linearly in RGB through the middle stop. Flat-mobile variant middle: `#E8E1D3`. The legend shows 5 discrete chips: `#4F7D5E #A9B8A0 #F4EEE2 #DC9A82 #C0402A`.

**Quadrant colors** (scatter dots / map blocks):
- cheap & safe: `#1E5B3A`
- expensive & safe: `#1C1B18`
- cheap & deadly: `#E2B13C` (dot gets a 1px ink ring for contrast)
- expensive & deadly: `#B8321D`

Unhovered relief-map blocks are the quadrant color mixed toward `#F4EEE2`: 50% for most quadrants, 30% for expensive & safe. The hovered block is the full quadrant color. Blocks filtered out are `#E2DACB`.

### Color: dark mode
Not yet designed as a 1a variant. Use artboard `1c` as a reference: ground `#161826`, surface `#1F2233`, text `#E9E9ED`, lit-window yellow `#E8C46A`, accent `#9184D9`. Keep awning, deli and bodega as hues, lifted to meet 4.5:1 on the dark ground. **Open item, confirm with the designer.**

### Typography
- **Display / prose:** Newsreader (Google Fonts; opsz 6–72; weights 400 and 500; italic 400).
- **Numbers / labels / controls:** IBM Plex Mono 400/500. Use `font-variant-numeric: tabular-nums` on changing numbers (year, counts).

| Role | Font | Size / line-height | Notes |
|---|---|---|---|
| Hero H1 | Newsreader 400 | 62px / 1.02, ls −0.02em | Second sentence italic, awning color. Mobile: 38px |
| Section H2 | Newsreader 400 | 40–44px / 1.04, ls −0.015em | |
| Prose | Newsreader 400 | 17–18px / 1.45, `text-wrap: pretty` | color ink-2 |
| Kicker | Plex Mono | 11px, ls 0.1em, UPPERCASE | awning. Format: `03 — Is the rent worth the risk?` |
| Label | Plex Mono | 10px, ls 0.06–0.08em, UPPERCASE | muted |
| Stat value | Plex Mono 400 | 22–30px | |
| Body UI / table | Plex Mono | 11–13px | |
| Entity names (addresses, businesses, neighborhoods) | Newsreader | 15–19px in lists; 28–44px as titles | |
| Quadrant labels | Newsreader *italic* | 21–26px | quadrant color |

### Shape and spacing
- **Square corners everywhere** (radius 0). The only round things are scatter dots and quadrant swatches.
- Borders are 1px: ink for containers and control groups, rule for dividers.
- No shadows. Depth comes only from the map relief.
- Desktop gutter 40px, mobile gutter **16px**. Section padding 56px vertical.
- Spacing steps in use: 4, 6, 8, 12, 14, 16, 20, 24, 28, 32, 36, 48.

---

## Screens

### A. Hero (1a), desktop 1280×820 artboard
Full-bleed paper.
- **Top bar** (56px, bottom border rule): "Half-Life" (Newsreader 500, 22px) + label "An atlas of NYC restaurant churn, 2012–2026". On the right, section links: `01 Cursed addresses · 02 Half-life · 03 Rent vs risk · 04 Beta · 07 Pitch yours` (Plex 11px uppercase, muted).
- **Map** fills the right ~80% (in the mock: 1020×610 starting at x=260, y=110), overlapping under the headline column.
- **Headline column** (left 40px, top 96px, 440px wide): kicker `00 — The city eats its restaurants`; H1 `85,000 places opened. 31,000 are still here.`; prose `Every column is a building that has housed a restaurant, bar, café, bakery or bodega since 2012. Height is how many have come and gone.`; then a top-ruled stat row: `OPEN IN {year}` → live count, and `MEDIAN LIFESPAN` → `4.1 yrs`.
- **Legend** (top right, right-aligned): title changes with the view (Churn → "Tenant turnover", "Few tenants"/"Many"; Lifespan → "Median lifespan", "Long-lived"/"Short"; Risk → "3-yr closure odds", "Safe"/"Deadly"; Rent → "Rent per sq ft", "Cheap"/"Expensive"). Below it: a 160×8 five-chip ramp, the lo/hi labels, and a `Dark this year` chip (`#DAD2C3`).
- **Hover card** (252px, paper-raised, 1px ink border, no radius): a 9px ink square marks the hovered building, with a 28px ink leader line to the card. Card header: address (Newsreader 19) + `NEIGHBORHOOD · N TENANTS SINCE 2012`. Body: up to 3 most recent tenants (name left; lifespan right; the current one in deli as `open · 2.3y`), then `+ N earlier · median 1.2y`. Footer 2-col: `3-YR CLOSURE` (awning) and `RENT / SQ FT`.
- **Control bar** (bottom, 100px, top border ink):
  - **View**: segmented control of 4 buttons in one 1px ink box with ink dividers. Active is ink fill with paper text. `Churn / Lifespan / Risk / Rent`.
  - **Category**: 6 separate bordered buttons `All / Restaurant / Bar / Café / Bakery / Bodega`. Inactive border is rule; active is ink fill.
  - **Year scrubber** (fills the remaining width): 40×40 ink-outlined play/pause button (Phosphor `ph-play`/`ph-pause`); the year at 30px; then a **butterfly bar chart**, 15 bars for 2012–2026: openings above a 1px ink baseline in deli (22px max), closings below in awning (22px max). Bars after the current year drop to 25% opacity. Below that: a native range input (2012–2026, step 1, `accent-color: ink`), and tick labels `2012 · ▲ openings · ▼ closings · 2020 shock · 2026`.

### B. Cursed Addresses (1d), desktop
Grid `400px | 1fr`, gap 48.
- **Leaderboard** (left): kicker, H2 `The storefronts that can't keep a tenant.` Header row grid `28px 1fr 56px 56px`: `# / Address / Tenants / Median`. Each row is a full-width button: rank (muted), address (Newsreader 17) over neighborhood (10px uppercase muted), tenant count (18px), median life (awning, `2.1y`). Rows have a bottom rule. **Selected row:** paper-raised background + 3px awning bar on the left (inset box-shadow).
- **Timeline card** (right): paper-raised, 1px ink border, padding 28.
  - Header: `RANK 1 · LOWER EAST SIDE` label, address in Newsreader 44px. Four stats on the right: Tenants, Median life (awning), Time vacant (%), Area median (muted).
  - **Strip**: a 34px band with ink top and bottom borders, spanning 2012.0–2026.8. Each tenant is an absolutely positioned bar (`left` and `width` in % of the span), its lifespan printed in the middle (11px). Gaps show a **vacancy hatch** (`repeating-linear-gradient(135deg, #E4DCCD 0 1px, transparent 1px 6px)`). Bars are separated by a 1px paper-raised inset on their right edge.
  - Bar color by lifespan: **< 1.5y awning**, **1.5–3y bodega** (ink text), **> 3y deli**. Text is paper on red and green.
  - **Name labels alternate** above and below the strip (even index above, odd below) to avoid collisions. Each has a 1px ink left tick at the bar's start, the name (Newsreader 14), and the cuisine (10px muted).
  - Year axis below: 2012…2026 every 2 years.
  - Legend: the three lifespan colors + Vacant.
  - Table: `# / Business / Cuisine / Price / Years / Lifespan`, grid `28px 1.6fr 1fr 60px 110px 70px`. The current tenant's lifespan reads `open · 2.3y` and its years `2024–now`.

### C. Rent vs Risk (3a), desktop 1440 artboard
Header grid 2 cols: kicker + H2 `Expensive streets aren't the safe ones.` on the left; prose on the right (`One dot per neighborhood. Across: average asking rent. Up: the odds a new place closes within three years. On the map, each neighborhood is one block, raised by its closure odds.`).
Body grid: `280px | minmax(0,500px) | 1fr`, gap 36, top-aligned.

**Side panel** (top border ink; sections separated by rule; all values follow the hovered neighborhood):
1. Quadrant label (quadrant text color) + neighborhood name (Newsreader 30).
2. 2×2 stats: Rent / sq ft, 3-yr closure (awning), Places, Median life.
3. **Against the city median**: two 8px bars on rule-soft tracks with a 1px median tick. Rent bar is ink on a 0–$260 scale, tick at $100, label like `+60%`. Closure bar is awning on a 20–65% scale, tick at 40%, label like `+15 pts`.
4. **Risk-adjusted rent** = `rent / (1 − closure3y)`, shown as `$356` plus `rank N of 32` (1 = best value). Caption: `Rent divided by the odds of making year three. Lower is better value.`
5. **Cheaper and safer**: up to 3 neighborhoods with lower rent AND lower closure (they dominate the current one), sorted by risk-adjusted rent. Each row is a button (name Newsreader 15 + `$85 · 28%`); hover or click selects it. If none: `Nothing beats it on both rent and risk.` in deli.
6. **Filter by quadrant**: 4 toggle buttons (swatch, name, count). Active is paper-raised with an ink border. A `Show all` link appears when a filter is on. Filtering fades other dots to 15% and flattens the other map blocks.

**Scatter** (plot height 480): x = rent $30–260 (ticks $50…$250), y = closure 20–65% (ticks 20…60%). Ink left and bottom axes. City medians are 1px dashed ink lines at $100 and 40%. Quadrant names in the four corners (Newsreader italic 21px). Dots: circle, diameter `sqrt(places)/3.2 + 4`, fill by quadrant. Hovered dot gets a double ring `0 0 0 2px paper, 0 0 0 3.5px ink`. A few labels are always on (SoHo, Midtown, LES, Flushing, Bushwick, UWS, Sunset Park) and the hovered one is labelled too (13px), all on a paper background. Watch for collisions: Mott Haven was dropped because it overlapped Bushwick.

**Neighborhood relief map**: same plaster style and camera as the hero, but **one extruded block per neighborhood** (all of LES is one piece), not per building. Block height = 3-yr closure odds. Neighborhoods are separated by flat land "streets". Hovering a block selects that neighborhood in the panel and scatter, and vice versa. The selected block gets a callout: a small ink square on its top, a vertical ink leader, and the name in Newsreader with a paper halo. Borough labels are in Plex uppercase. Caption row below: `Block height = 3-yr closure odds · Colour = quadrant`.

### D. Mobile hero + scrubber (1f), 390 wide, 16px gutter, no horizontal scroll
- 52px header: "Half-Life" + 44×44 menu button (`ph-list`).
- Kicker, then H1 at 38px.
- View toggle: 4-column grid, each button 44px tall.
- **Flat map** (no 3D on small screens): hex bins on the land plate, square aspect (358×372 in the mock), followed by a 5-chip ramp legend and the caption `Flat map on small screens. Tap a hex for its buildings.`
- **Sticky bottom scrubber** (paper, top border ink, padding 10/16/14): 44×44 ink-filled play button; year at 28px over `N open`; a mini butterfly chart (18px each side); a full-width range input 28px tall; then a horizontally scrolling chip row of categories (36px tall; the row bleeds to the screen edges with -16px margins and 16px padding).

### E. Mobile tap sheet (1g)
Tapping replaces hover. The map dims to 55% and a bottom sheet (paper-raised, top border ink) rises with: a drag handle (36×3 rule); a label `NEIGHBORHOOD · RANK N`; the address (Newsreader 28); a 44×44 close button (`ph-x`); a 3-col stat row (Tenants, 3-yr close, Rent/sqft); a mini timeline strip (22px, same colors and hatch as 1d) with an axis `2012 · 2019 · 2026`; the last 3 tenants as 44px-min rows; and a `Full timeline →` 44px outlined button.

---

## Map spec (deck.gl)
- **Zoom ≤ ~12 (city):** `HexagonLayer` / H3 bins, extruded, elevation = businesses since 2012 (or the active metric).
- **Zoom > ~12 (neighborhood):** `ColumnLayer` or extruded building footprints (`PolygonLayer`/`GeoJsonLayer` with `extruded: true`), one per building, elevation = number of businesses since 2012.
- **Rent-vs-risk map:** extruded neighborhood polygons (NTA boundaries), elevation ∝ (closure3y − 20%).
- **Camera:** pitch ~45–50°, bearing ~-20°. Light: `LightingEffect` with soft ambient (~0.9) + one directional light from the west/north-west. Material `{ambient: .6, diffuse: .5, shininess: 0, specularColor: [0,0,0]}` for a matte plaster look, with no gloss. The side faces in the mock are the top color × 0.70–0.84 depending on orientation.
- **Basemap:** none or minimal. Draw land as a flat `#E7E0D2` polygon on the paper background, with water as the paper itself. No labels except borough names.
- **Year scrubber:** filter on `open_year ≤ year < close_year` (plus a COVID temporary-closure window if the data has one). Closed or not-yet-open buildings stay visible in `#DAD2C3` so the city keeps its shape. Use `updateTriggers` on `getFillColor` keyed by `[year, view, category]`, and animate color with `transitions: {getFillColor: 300}`.
- **Category filter:** non-matching buildings drop to ~15% elevation and the dead color.
- **Mobile (< 768px):** pitch 0, no extrusion, hex bins only; tap opens the sheet.

## Interactions and state
Global (shared across sections, e.g. Zustand or URL search params):
- `year: 2012–2026` (default 2026); `playing: boolean`. Play advances 1 year per **650ms**, stops at 2026, and restarts from 2012 if pressed at the end.
- `view: 'churn' | 'lifespan' | 'risk' | 'rent'`; `category: 'all' | 'restaurant' | 'bar' | 'cafe' | 'bakery' | 'bodega'`.
- `hoveredBuildingId` (desktop hover / mobile tap).

Section-local:
- Cursed Addresses: `selectedAddressId` (default rank 1).
- Rent vs Risk: `selectedNeighborhood` (default Lower East Side), `quadrantFilter: null | 'cs' | 'es' | 'cd' | 'ed'`. Quadrants split at the city medians (rent $100, closure 40% in the mock). Compute these from the data.

All interactive elements need `:focus-visible` (2px ink outline, 2px offset), a hover tint (paper-raised), and keyboard support on the range input. Touch targets on mobile are ≥ 44px.

## Data contract (suggested)
- `businesses`: id, name, building_id, lat/lng, open_date, close_date|null, cuisine, price_tier, chain bool, category.
- `buildings`: id, address, neighborhood_id, footprint/centroid, tenant_count.
- `neighborhoods`: id, name, borough, polygon, rent_psf, closure_3y, places, median_life, survival_curve[].
- `yearly`: year, openings, closings (for the scrubber's butterfly chart).

## Assets
- Fonts: Newsreader, IBM Plex Mono (Google Fonts).
- Icons: Phosphor (`ph-play`, `ph-pause`, `ph-list`, `ph-x`, `ph-arrow-right`).
- No images.

## Files
- `Half-Life Directions.dc.html`: the full design canvas. Approved artboards: **1a, 1d, 1f, 1g, 3a**. Open it with `support.js` in the same folder. The canvas chrome (dark background, badges) loads the `_ds/` stylesheet, which isn't included and doesn't matter. The artboards themselves are fully inline-styled.
- `support.js`: runtime for the HTML file (reference only).
