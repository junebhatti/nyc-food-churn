"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { CurveRow, PitchData } from "@/lib/types";
import SurvivalChart, { Legend, type Series } from "../charts/SurvivalChart";
import Section, { Stat, pct } from "./Section";

const BORO_KEY: Record<string, string> = { Brooklyn: "boro_BROOKLYN", Queens: "boro_QUEENS", Bronx: "boro_BRONX", "Staten Island": "boro_STATEN ISLAND" };
const SPOTS = [
  { id: "fresh", label: "Fresh storefront" },
  { id: "1-2", label: "1–2 earlier tenants" },
  { id: "3+", label: "3+ earlier tenants" },
] as const;

interface Choice {
  cuisine: string;
  hood: string;
  chain: boolean;
  counter: boolean;
  spot: (typeof SPOTS)[number]["id"];
}

const PRIOR_KEYS = ["prior_1_2", "prior_3plus"];
const PRIOR_FADES_AT = 3; // years; the cursed spot test (/cursed-spot) shows the storefront-history penalty is gone by years 4-5

/** Cox model prediction, S(t) = S0(t) ^ exp(sum((x - mean) * coef)), except that the storefront-history
 *  terms only apply in the first PRIOR_FADES_AT years (the model's proportional-hazards fit would
 *  otherwise carry the early penalty for all ten years, which the data says it doesn't). */
function predict(p: PitchData, c: Choice): number[] {
  const n = p.neighborhoods.find((h) => h.id === c.hood);
  const x: Record<string, number> = {
    chain: c.chain ? 1 : 0,
    limited_service: c.counter ? 1 : 0,
    prior_1_2: c.spot === "1-2" ? 1 : 0,
    prior_3plus: c.spot === "3+" ? 1 : 0,
    nbhd_value_z: n?.valueZ ?? 0,
    foot_traffic_z: n?.trafficZ ?? 0,
  };
  if (c.cuisine !== "american") x[`cuisine_${c.cuisine}`] = 1;
  if (n && BORO_KEY[n.boro]) x[BORO_KEY[n.boro]] = 1;
  const lp = (withPrior: boolean) =>
    Object.entries(p.coef).reduce((s, [k, b]) => {
      const xi = !withPrior && PRIOR_KEYS.includes(k) ? (p.means[k] ?? 0) : (x[k] ?? 0);
      return s + (xi - (p.means[k] ?? 0)) * b;
    }, 0);
  const early = Math.exp(lp(true));
  const late = Math.exp(lp(false));
  const k = p.grid.findIndex((t) => t >= PRIOR_FADES_AT);
  const sK = Math.pow(p.baseline[k], early);
  return p.baseline.map((s0, i) => (i <= k ? Math.pow(s0, early) : sK * Math.pow(s0 / p.baseline[k], late)));
}

const at = (grid: number[], curve: number[], t: number) => curve[grid.findIndex((g) => g >= t)] ?? curve[curve.length - 1];

export default function Pitch({ data, city }: { data: PitchData; city: CurveRow }) {
  const defaultHood = data.neighborhoods.find((h) => h.name.startsWith("East Village"))?.id ?? data.neighborhoods[0].id;
  const [c, setC] = useState<Choice>({ cuisine: "italian", hood: defaultHood, chain: false, counter: false, spot: "fresh" });
  const curve = useMemo(() => predict(data, c), [data, c]);
  const hood = data.neighborhoods.find((h) => h.id === c.hood);
  const s3 = at(data.grid, curve, 3), s5 = at(data.grid, curve, 5);
  const halfIdx = curve.findIndex((s) => s < 0.5);
  const half = halfIdx > 0 ? data.grid[halfIdx] : null;
  const series: Series[] = [
    { label: "Your place", values: curve, color: "var(--awning)", strong: true },
    { label: "Typical NYC opening", values: city.curve, color: "var(--ink)", dashed: true },
  ];
  const set = <K extends keyof Choice>(k: K, v: Choice[K]) => setC({ ...c, [k]: v });
  const field = "mono h-11 w-full border border-ink bg-paper-raised px-3 text-[12px]";

  return (
    <Section
      id="pitch"
      kicker="07 — Pitch yours"
      title={<>Open a restaurant. See your odds.</>}
      intro={<>Pick what you&rsquo;d open and where. The estimate comes from a survival model fit on {data.fit.n.toLocaleString()} places that opened in {data.fit.opened}, controlling for cuisine, borough, chain status, service style, the storefront&rsquo;s history, local property values and foot traffic. A storefront&rsquo;s history only counts for the first three years, as <Link href="/cursed-spot" className="underline decoration-rule underline-offset-2 hover:decoration-ink">the cursed spot test</Link> shows. It&rsquo;s a base rate, not a forecast: food, money and luck aren&rsquo;t in the data.</>}
    >
      <div className="grid gap-10 lg:grid-cols-[320px_minmax(0,1fr)]">
        <form className="space-y-5 border-t border-ink pt-4" onSubmit={(e) => e.preventDefault()}>
          <label className="block">
            <span className="label">Cuisine</span>
            <select className={`${field} mt-1`} value={c.cuisine} onChange={(e) => set("cuisine", e.target.value)}>
              {data.cuisines.map((q) => <option key={q.id} value={q.id}>{q.label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="label">Neighborhood</span>
            <select className={`${field} mt-1`} value={c.hood} onChange={(e) => set("hood", e.target.value)}>
              {data.neighborhoods.map((h) => <option key={h.id} value={h.id}>{h.name} · {h.boro}</option>)}
            </select>
          </label>
          <Toggle label="Brand" options={[["Independent", false], ["Chain", true]]} value={c.chain} onChange={(v) => set("chain", v)} />
          <Toggle label="Service" options={[["Sit-down", false], ["Counter", true]]} value={c.counter} onChange={(v) => set("counter", v)} />
          <div>
            <span className="label">The storefront</span>
            <div className="mt-1 grid grid-cols-3 border border-ink">
              {SPOTS.map((s, i) => (
                <button key={s.id} type="button" aria-pressed={c.spot === s.id} onClick={() => set("spot", s.id)}
                  className={`mono min-h-11 px-1 text-[10px] uppercase tracking-[0.04em] ${i ? "border-l border-ink" : ""} ${c.spot === s.id ? "bg-ink text-paper" : "hover:bg-paper-raised"}`}>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </form>
        <div>
          <div className="mb-6 grid grid-cols-2 gap-6 border-t border-ink pt-3 md:grid-cols-4">
            <Stat label="Odds of reaching year 3" value={pct(s3)} tone={s3 < at(data.grid, city.curve as number[], 3) ? "red" : "green"} />
            <Stat label="Year 5" value={pct(s5)} />
            <Stat label="Your half-life" value={half != null ? `${half.toFixed(1)} yrs` : "10+ yrs"} />
            <Stat label="Neighborhood beta" value={hood?.beta != null ? hood.beta.toFixed(2) : "—"} tone="muted" />
          </div>
          <SurvivalChart grid={data.grid} series={series} height={300} label="Predicted survival for your restaurant" />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <Legend series={series} />
            <span className="label">
              {hood?.name}: rent {hood?.rent != null ? `$${Math.round(hood.rent)}/sq ft/yr` : "n/a"} · area 3-yr closure {hood?.closure3y != null ? pct(hood.closure3y) : "n/a"}
            </span>
          </div>
        </div>
      </div>
    </Section>
  );
}

function Toggle<T>({ label, options, value, onChange }: { label: string; options: [string, T][]; value: T; onChange: (v: T) => void }) {
  return (
    <div>
      <span className="label">{label}</span>
      <div className="mt-1 grid grid-cols-2 border border-ink">
        {options.map(([text, v], i) => (
          <button key={text} type="button" aria-pressed={value === v} onClick={() => onChange(v)}
            className={`mono h-11 text-[11px] uppercase tracking-[0.06em] ${i ? "border-l border-ink" : ""} ${value === v ? "bg-ink text-paper" : "hover:bg-paper-raised"}`}>
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
