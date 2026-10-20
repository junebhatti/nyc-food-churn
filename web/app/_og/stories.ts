import type { CovidData, HalfLifeData } from "@/lib/types";
import covidJson from "@/public/data/covid.json";
import halflifeJson from "@/public/data/halflife.json";

// Share text for each story: the kicker and headline as the section prints them (the two
// data-driven headlines are worked out the same way as in HalfLife.tsx and Covid.tsx), plus the
// page description.
const median = (halflifeJson as unknown as HalfLifeData).groups.all.rows[0].median;
const covid = covidJson as CovidData;
const i2020 = covid.periods.indexOf("2020H1");
if (i2020 === -1) throw new Error("covid.json has no 2020H1 period");
const sum2020 = (xs: number[]) => xs.slice(i2020, i2020 + 2).reduce((a, b) => a + b, 0);

export const STORY_SHARE: Record<string, { title: string; kicker: string; headline: string; description: string }> = {
  cursed: {
    title: "Cursed addresses — NYC Turnover",
    kicker: "01 — Cursed addresses",
    headline: "The storefronts that can’t keep a tenant.",
    description: "The NYC storefronts that have churned through the most restaurants, bars, cafés and bodegas since 2012, tenant by tenant.",
  },
  "half-life": {
    title: "Half-life — NYC Turnover",
    kicker: "02 — Half-life",
    headline: median == null ? "Half of new places are gone in 10+ years." : `Half of new places are gone in ${median.toFixed(1)} years.`,
    description: "How long NYC food and drink businesses last: survival curves by category, cuisine, price and year opened, since 2012.",
  },
  "rent-vs-risk": {
    title: "Rent vs risk — NYC Turnover",
    kicker: "03 — Is the rent worth the risk?",
    headline: "Pricier streets are a little safer. Rent isn’t why.",
    description: "Do pricier NYC neighbourhoods keep restaurants open longer? Retail rents set against three-year closure rates, and what actually explains the gap.",
  },
  beta: {
    title: "Beta — NYC Turnover",
    kicker: "04 — Beta",
    headline: "Who gets hit when the city has a bad year.",
    description: "Which kinds of NYC food businesses close fastest when the whole city has a bad year: each category’s closure rate against the citywide swing.",
  },
  "cursed-spot": {
    title: "The cursed spot test — NYC Turnover",
    kicker: "05 — The cursed spot test",
    headline: "A storefront’s past barely predicts its next tenant.",
    description: "Does a storefront’s history predict whether the next restaurant there survives? Testing the “cursed spot” idea against every NYC opening since 2012.",
  },
  "2020": {
    title: "The 2020 shock — NYC Turnover",
    kicker: "06 — The 2020 shock",
    headline: `In 2020 the city lost ${sum2020(covid.close).toLocaleString("en-US")} places and opened ${sum2020(covid.open).toLocaleString("en-US")}.`,
    description: "What the pandemic did to NYC’s restaurants, bars, cafés and bodegas: openings, closures and places open, half-year by half-year.",
  },
};
