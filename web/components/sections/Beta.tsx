"use client";

import { useState } from "react";
import type { BetaData, BetaRow } from "@/lib/types";
import { useWidth } from "@/lib/useWidth";
import Section from "./Section";

const TABS = [
  { id: "nta2020", label: "Neighborhood" },
  { id: "family_top", label: "Cuisine" },
  { id: "boro", label: "Borough" },
] as const;

/** City exit rate by year: the "market" that beta is measured against. */
function CityRate({ city }: { city: BetaData["city"] }) {
  const [box, W] = useWidth(420);
  const H = 150, P = { l: 30, r: 8, t: 10, b: 22 };
  const max = Math.ceil(Math.max(...city.map((c) => c.city_exit_pct)) / 5) * 5;
  const bw = (W - P.l - P.r) / city.length;
  return (
    <div ref={box}>
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block max-w-full" role="img" aria-label="Citywide closure rate by year">
      {[0, max / 2, max].map((v) => (
        <text key={v} x={P.l - 6} y={P.t + (1 - v / max) * (H - P.t - P.b) + 3} textAnchor="end" fontSize={9} fill="var(--muted)" className="mono">{v}%</text>
      ))}
      {city.map((c, i) => {
        const h = (c.city_exit_pct / max) * (H - P.t - P.b);
        return (
          <g key={c.year}>
            <rect x={P.l + i * bw + 2} y={H - P.b - h} width={bw - 4} height={h} fill={c.year === 2020 ? "var(--awning)" : "var(--rule)"} />
            {c.year % 2 === 1 && <text x={P.l + i * bw + bw / 2} y={H - 6} textAnchor="middle" fontSize={9} fill="var(--muted)" className="mono">{String(c.year).slice(2)}</text>}
          </g>
        );
      })}
      <line x1={P.l} x2={W - P.r} y1={H - P.b} y2={H - P.b} stroke="var(--ink)" />
    </svg>
    </div>
  );
}

const SHOW = 15;

/** The three highest- or lowest-beta groups, as "A, B and C" (names cut at their first hyphen). */
function extremes(rows: BetaRow[], group: string, top: boolean): string {
  // Licence-only bars are left out here as in the table (their end dates only exist from 2015).
  const names = rows.filter((r) => r.group === group && r.level !== "bar").sort((a, b) => (top ? b.beta - a.beta : a.beta - b.beta))
    .slice(0, 3).map((r) => r.label.split("-")[0].trim());
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
// Phones: name, bar, beta. From md: plus the normal-year and COVID columns.
const COLS = "grid grid-cols-[minmax(0,1fr)_minmax(80px,1fr)_40px] gap-3 md:grid-cols-[minmax(0,1fr)_minmax(110px,1.3fr)_44px_64px_64px]";
const pts = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)} pts`;

function BetaBars({ rows }: { rows: BetaRow[] }) {
  const [all, setAll] = useState(false);
  const sorted = [...rows].sort((a, b) => b.beta - a.beta);
  const shown = all ? sorted : sorted.slice(0, SHOW);
  const lo = Math.min(0, ...sorted.map((r) => r.beta));
  const hi = Math.max(2, ...sorted.map((r) => r.beta));
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  return (
    <div>
      <div className={`label mb-2 border-b border-ink pb-2 ${COLS}`}>
        <span>Group</span><span className="truncate">Steadier · 1 · harder</span><span className="text-right">Beta</span>
        <span className="hidden text-right md:block">Normal yrs</span><span className="hidden text-right md:block">2019–21</span>
      </div>
      {shown.map((r) => {
        const spread = r.spread_bp / 100;
        return (
          <div key={r.level} className={`items-center border-b border-rule py-1.5 ${COLS}`}
            title={`${r.label}: baseline closure rate ${r.baseline_exit_pct.toFixed(1)}%/yr (2013–17), ${r.avg_at_risk} places in a typical year; normal years ${pts(spread)} vs the city; 2019–21 ${pts(r.covid_excess_pts)}`}>
            <span className="truncate text-[15px]">{r.label}</span>
            <div className="relative h-3">
              <div className="absolute inset-y-0 w-px bg-ink" style={{ left: `${x(1)}%` }} />
              <div className="absolute inset-y-0" style={{
                left: `${x(Math.min(r.beta, 1))}%`, width: `${Math.abs(x(r.beta) - x(1))}%`,
                background: r.beta > 1 ? "var(--awning)" : "var(--deli)",
              }} />
            </div>
            <span className="mono tnum text-right text-[13px]">{r.beta.toFixed(2)}</span>
            <span className={`mono tnum hidden text-right text-[12px] md:block ${Math.abs(spread) < 0.05 ? "text-muted" : spread > 0 ? "text-awning" : "text-deli"}`}>{pts(spread)}</span>
            <span className="mono tnum hidden text-right text-[12px] text-muted md:block">{pts(r.covid_excess_pts)}</span>
          </div>
        );
      })}
      {sorted.length > SHOW && (
        <button type="button" onClick={() => setAll(!all)}
          className="mono mt-3 h-10 border border-ink px-4 text-[11px] uppercase tracking-[0.06em] hover:bg-paper-raised">
          {all ? `Show top ${SHOW}` : `Show all ${sorted.length}`}
        </button>
      )}
      <p className="label mt-3 leading-relaxed">
        The bar grows right of the line for groups hit harder than the city in bad years (<span className="text-awning">red</span>) and left
        for steadier ones (<span className="text-deli">green</span>). Normal yrs: how much more (+) or less (−) often places close here in an
        ordinary year than across the city, in percentage points. 2019–21: the extra closures in the COVID years.
      </p>
    </div>
  );
}

export default function Beta({ data }: { data: BetaData }) {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("nta2020");
  // Licence-only bars are left out: their end dates only exist from 2015, so their beta isn't reliable.
  const rows = data.rows.filter((r) => r.group === tab && !(r.group === "family_top" && r.level === "bar"));
  return (
    <Section
      id="beta"
      kicker="04 — Beta"
      title={<>Who gets hit when the city has a bad year.</>}
      intro={<>When the whole city has a bad year, some places get hit much harder than others. Each neighborhood and type of place gets a score called <b>beta</b> (borrowed from finance). A beta of 1 means its closures rise and fall in step with the city&rsquo;s. Above 1, bad years hit it harder: at 1.8, when the city&rsquo;s closure rate jumps, its jumps about 80% more. Below 1, it barely notices. Because 2020 was by far the worst year, beta is mostly a ranking of who 2020 hit hardest.</>}
    >
      <div className="grid gap-12 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div>
          <div className="label mb-2">Citywide closure rate, share of open places closing each year</div>
          <CityRate city={data.city} />
          <p className="mt-4 text-[15px] leading-snug text-ink-2">
            Hit hardest: {extremes(data.rows, "nta2020", true)}. Steadiest: {extremes(data.rows, "nta2020", false)}. Among kinds of
            place, {extremes(data.rows, "family_top", true)} swing hardest, while {extremes(data.rows, "family_top", false)} hold steadiest.
          </p>
          <p className="label mt-4">Closure dates are good to about a season, and 2018–19 closures partly land in 2020. Read beta as a ranking.</p>
        </div>
        <div>
          <div role="group" aria-label="Group by" className="mono mb-4 inline-grid grid-cols-3 border border-ink text-[11px] uppercase tracking-[0.06em]">
            {TABS.map((t, i) => (
              <button key={t.id} type="button" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}
                className={`h-9 px-3 ${i ? "border-l border-ink" : ""} ${tab === t.id ? "bg-ink text-paper" : "hover:bg-paper-raised"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <BetaBars rows={rows} />
        </div>
      </div>
    </Section>
  );
}
