# Polish brief: sections 02, 04, 05, 06, 07

**For:** Claude Design · **Project:** Half-Life, an atlas of NYC food & drink churn (live at https://half-life-nyc.vercel.app)

## Context
The first handoff (`../design_handoff_half_life/README.md`) designed the hero map, section 01 (Cursed Addresses), section 03 (Rent vs Risk) and the mobile hero. Sections 02 and 04–07 were then built straight in code from that design system, with no artboards of their own. They work and the numbers are real, but they read as "engineer-built". This brief asks for one consistent pass that brings them up to the level of 01 and 03.

Screenshots of the current state (light, 1440 wide) sit next to this file: `02-half-life.jpg`, `04-beta.jpg`, `05-cursed-test.jpg`, `06-covid.jpg`, `07-pitch.jpg`.

## Ground rules
- **Use the existing design system and nothing new:** the tokens, type scale, square corners, 1px ink/rule borders and no shadows from the first handoff. A new token is fine only if it fixes a real problem; say why.
- **Keep the copy, the data and what each section argues.** Headlines, intros and stats are real and checked. Suggest copy edits separately; don't change the copy in the artboards.
- **Charts stay hand-drawn SVG in the site's style** (no charting-library look). Lines, bars, ticks and labels follow the type table: Plex Mono for numbers and labels, Newsreader for entity names.
- **Every section shares one frame,** shown in the screenshots: ink top rule, then kicker + H2 on the left and intro prose on the right, then content. Keep that frame unless it's the problem.
- **Deliver both themes.** The site now has a dark theme that follows the system setting: ground `#161826`, surface `#1F2233`, ink `#E9E9ED`, muted `#9A9CAB`, rule `#3A3E52`, awning `#E8644C`, deli `#5DB585`, bodega `#E8C46A`, violet `#9184D9`. These are an engineering reading of artboard 1c, so please confirm or correct them.
- **Desktop 1440 and mobile 390** (16px gutter, no horizontal scroll) for each section.

## What I'd like per section

### 02 — Half-life (`02-half-life.jpg`)
Survival curves (share still open by years since opening) split by Borough / Cuisine / Chain / Year opened, plus a sortable table. Clicking a row toggles its line (up to 5).
- When the curves are close together (boroughs especially), the lines turn to mush. We need a way to pick out one line: a hover or selected state, end-of-line labels, or fading the others.
- The series colours (ink, awning, deli, bodega-text, violet, muted) were picked ad hoc. Please give a proper 5-series set for both themes.
- The headline breaks as "5.9 / years". Fix the wrap or the measure.
- The table's right columns sit under the floating "Ask about the data" tab at the right edge (a problem on every section). Suggest how that tab and the content should share the edge.

### 04 — Beta (`04-beta.jpg`)
A small citywide closure-rate bar chart (2020 highlighted), plus a long diverging-bar list of beta per neighbourhood / cuisine / borough (1 = moves with the city), with spread (bp) and 2019–21 excess columns.
- The list scrolls inside a 520px box on a page that also scrolls. Find a better pattern: top and bottom 10 with "show all", search, or something else.
- Long neighbourhood names truncate ("Financial District-Battery Par…").
- The 1.0 reference line is barely visible, and with bars that start at 1 the list reads as "all red". Make "above vs below the city" obvious at a glance.
- The citywide chart on the left is small and its labels are tiny. It's the "market" that the section is about.

### 05 — The cursed spot test (`05-cursed-test.jpg`)
Left: survival curves for fresh storefronts vs 1–2 vs 3+ earlier tenants. Right: hazard-ratio bars by age band (Year 1 … Years 6–10) with a 1× line.
- The value labels collide with the 1× line ("0.9×" on Years 4–5).
- The olive (`bodega-text`) and red bars are too close in weight. The two series should be distinguishable without the legend.
- The story is "the gap closes by year four", but the layout doesn't show that. Consider tying the two charts together, for example shading years 1–3 on the curve chart.

### 06 — The 2020 shock (`06-covid.jpg`)
A butterfly bar chart, openings above and closings below, every six months from 2017 to 2023, with 2020 shaded and a stat column.
- The y-axis shows "2.6k" at both ends with no sign. Label the axis properly.
- This is the most finished of the five, so a light pass is enough. Match the scrubber's butterfly chart in the hero so the two feel related.

### 07 — Pitch yours (`07-pitch.jpg`)
A form (cuisine, neighbourhood, brand, service, storefront history) drives a predicted survival curve against the typical NYC opening, plus four stats.
- This should feel like the payoff of the page: a playful, tactile "build your restaurant" without breaking the system.
- The stats row has no visual hierarchy. "Odds of reaching year 3" is the headline number.
- The neighbourhood context line (rent, area closure) is buried under the chart.
- On mobile, the form needs a pattern that keeps the chart in view while you change inputs.

## Deliverable
The same format as the first handoff: an HTML artboard file plus a README addendum with exact values (sizes, colours, spacing, states) for each section, in light and dark, desktop and mobile. Any new interactions (hover, selection, show-all) should be prototyped in the artboards.
