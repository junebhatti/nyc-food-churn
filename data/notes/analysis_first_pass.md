# First analysis pass (2026-10-19)

Scripts: `pipeline/analysis_common.py`, `analysis_survival.py`, `analysis_cox.py`, `analysis_beta.py`.
Outputs are in `data/processed/analysis/` (gitignored; rerun the scripts after `build_*`).
Run time is under 2 minutes in total.

**Cohort:** 44,754 businesses opened since 2012-07-06 (start observed), with 20,438 closures.
Relocations count as censored, not as failures. Closure dates are good to about a quarter (merge.md),
so everything below is in years.

## Headline findings

**1. The cursed spot is real, and it fades with age.** (cursed_by_age.csv)
Normal storefronts opened 2015+. Closure hazard per year of age, relative to a fresh spot:

| Spot | Year 1 | Year 2 | Year 3 | Years 3–5 | Years 5–10 |
|---|---|---|---|---|---|
| fresh (hazard) | 7.3% | 11.3% | 10.8% | 10.8% | 8.3% |
| 1–2 prior tenants | 2.2× | 1.8× | 1.4× | 0.9× | 0.75× |
| 3+ prior tenants | 4.5× | 3.4× | 2.9× | 1.6× | 1.8× (n small) |

A newcomer at a churned storefront is far likelier to die young, but survivors converge with
everyone else by about years 3–5. This matches the "hard to build traction where places keep
failing" hypothesis.
Cox model, controlling for cuisine, borough, chain and rent: 2.8× and 3.9× on average. That figure is
weighted toward early ages, because the effect is not proportional over time.

**2. What predicts closure, all else equal.** (cox_hazard_ratios.csv; opened 2015+, stratified by cohort; concordance 0.62)
- **Chains:** 0.67× (a third less likely to close).
- **Riskiest kinds of place:** juice/beverage 1.51×, café/coffee/tea 1.47×, pizza 1.32×, deli/sandwich 1.31×, Middle Eastern/Mediterranean 1.22× (vs American).
- **Safest kinds of place:** Italian 0.88×, Japanese/Korean 0.92×.
- **Neighbourhood value per sq ft is barely protective** (0.97 per SD, p≈0.05). Expensive areas are not meaningfully riskier or safer.
- **Foot traffic (tract index, opening year) slightly *raises* risk:** 1.04 per SD (p=0.01). Busy blocks don't keep places alive; they churn a little more, likely through more competition and entry.
- **Boroughs barely differ,** except Staten Island at 1.13×.

**3. Acclaim helps, measured fairly.** (observed_since.csv)
Survival counted from the first critic mention (Michelin/NYT/Eater/award), against
unacclaimed places alive on the same date at a similar age:
- 3 years after: 89% vs 71%.
- 5 years after: 79% vs 60%.

**4. The missing middle.** Survival 5 years after a price tier was observed (menu/Google/Michelin):
fine 83%, upscale 75%, cheap 74%, **mid 70%**. The gaps are small and still need confidence intervals.

**5. Beta: who gets hit when the city has a bad year.** (beta_by_group.csv)
Annual exit rates 2013–25 regressed on the citywide rate, so this mostly measures the 2020 shock.
- **Highest beta (amplifiers):** Ridgewood 1.8, Chinatown-Two Bridges 1.7, Bed-Stuy (West) 1.6, Sunset Park (Central) 1.6, Financial District 1.57, Tribeca 1.55, West Village 1.55. Office, commuter and tourist areas.
- **Lowest beta (defensive):** Sunnyside ~0, Astoria (Central) ~0, Carroll Gardens 0.46, Forest Hills 0.60, Jackson Heights 0.65. Residential Queens and Brooklyn.
- **By kind of place:** deli/sandwich 1.34 and café/coffee 1.31 (the office-lunch trade); Italian 0.63 is the most defensive.
- **By borough:** Manhattan 1.11, Brooklyn 1.07, Queens 0.85, Bronx 0.70.
- **Baseline exit rates ("spreads" vs the city's 10.9%):** chains −309 bp, bars −374 bp, latin/caribbean +251 bp, Middle Eastern +264 bp.

**Other survival numbers** (survival_by_group.csv): the median restaurant lasts 5.8 years; 88% survive year 1, 67% year 3, 54% year 5.
- Manhattan has the longest median, 6.4 years. Staten Island has the shortest, 4.8.
- Chains have a median of 8.5 years, against 5.1 for independents.

## Caveats and next steps
- **Bars' (NYSLA-only) beta is unreliable (−0.13):** licence end dates only exist from 2015, and renewals drive the dates.
- **Beta covers only 44 neighbourhoods** (those with ≥150 businesses open in a typical year). Lower the threshold, or pool to community districts, to fill the map.
- **Price tiers:** add confidence intervals, and rerun after the menu download finishes (more menu-based tiers).
- **Foot traffic** is in the Cox model now. Next: try components (subway vs jobs vs residents) and an evening/night share for bars.
- **Cox proportional hazards:** the prior-tenant terms violate it. Consider age-split terms (prior × age<3y) in the next pass.
- **Recent cohorts (2022+)** have under-detected closures (DOHMH purge lag), so their survival looks better than it is.
