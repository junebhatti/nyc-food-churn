# Design brief: "Half-Life", an atlas of NYC restaurant churn

Reference for tone and build: https://oil-visualizer.vercel.app/ (Pump Price Atlas). Match its editorial calm: paper background, ink text, serif display type, monospace numbers, hairline rules, square corners, numbered sections, matte 3D relief that reads like a plaster model on paper, not a glossy WebGL demo. Give this project its OWN identity, not a reskin. One idea: a palette from NYC storefronts (awning red, deli green, bodega yellow) on warm off-white.

## What it is
An interactive data story about how fast NYC eats its restaurants: which storefronts churn, how long places survive, and whether the rent is worth the risk. It's for a personal portfolio site, aimed at curious readers plus finance/VC people. The angle is finance: each storefront is treated like a loan, with a closure rate, a "credit spread" and a "beta".

## Data
About 85,000 food and drink businesses (restaurants, bars, cafés, bakeries, bodegas), 2012 → 2026, each with location, open and close dates, cuisine, price tier (cheap / mid / upscale / fine), chain vs independent, and building. Plus rent per sq ft by neighborhood, a foot-traffic index, Michelin/Eater acclaim, and per-neighborhood survival curves.

## Page structure (a scrolling story that ends in an explorer)
0. **Hero:** full-bleed 3D NYC. Each building with a food business gets a column whose height = number of businesses there since 2012. Headline stat above it (e.g. "85,000 places opened. 31,000 are still here.").
1. **Cursed Addresses:** leaderboard of the highest-churn storefronts. Clicking one shows a horizontal timeline of every business that occupied it (name, cuisine, lifespan bars laid end to end).
2. **Half-Life:** survival curves (share still open after X years) by borough, cuisine and price tier. The map switches to median lifespan by neighborhood.
3. **Is the Rent Worth the Risk?:** scatter with one dot per neighborhood, rent/sq ft on x and 3-year closure odds on y, split into four labeled quadrants (cheap & safe, expensive & safe, cheap & deadly, expensive & deadly).
4. **Beta:** which neighborhoods and kinds of restaurants swing hardest when the city has a bad year (COVID as the shock). A ranked bar chart or slope chart.
5. **The Cursed Spot Test:** two survival curves, fresh storefront vs one with 3+ previous tenants, showing how the gap changes with age.
6. **COVID shock:** monthly openings vs closings, 2019–2022.
7. **Pitch Your Restaurant:** a small form (cuisine, price, neighborhood, chain y/n, fresh or cursed spot) that returns your survival curve, odds of reaching year 3 and 5, your beta, and local rent.
8. **Methods and caveats,** kept short and honest.

## Always-available controls
- View toggle: Churn / Lifespan / Risk / Rent
- Category filter: restaurant, bar, café/coffee, bakery/dessert, bodega/deli
- Year scrubber 2012 → 2026 (places light up and go dark): the signature interaction
- Hover card on any building: address, list of past businesses, neighborhood odds

## Map behavior
Hexagon bins when zoomed out to the whole city, individual building columns when zoomed in to a neighborhood. Tilted camera, soft directional light.

## Constraints
Next.js + deck.gl + Tailwind. Must work on mobile: a 16px gutter and no horizontal scroll, with the 3D map falling back to a flat map on small screens. Accessible color contrast in both light and dark.

## What I'd like from you
- 2–3 visual directions for the hero and overall system: type pairing, palette, map styling.
- A layout for the Cursed Address timeline card.
- A layout for the rent-vs-risk quadrant.
- A mobile version of the hero plus the year scrubber.

---
*Title is a placeholder (alternatives: Turnover, Cursed Addresses, The Restaurant Index). Headline numbers are close but not final until the merge.*
