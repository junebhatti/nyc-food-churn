"use client";

import { useState } from "react";
import type { BetaData, BetaRow } from "@/lib/types";
import Section from "./Section";

const TABS = [
  { id: "nta2020", label: "Neighborhood" },
  { id: "family_top", label: "Cuisine" },
  { id: "boro", label: "Borough" },
] as const;

/** City exit rate by year: the "market" that beta is measured against. */
function CityRate({ city }: { city: BetaData["city"] }) {
  const W = 420, H = 150, P = { l: 30, r: 8, t: 10, b: 22 };
  const max = Math.ceil(Math.max(...city.map((c) => c.city_exit_pct)) / 5) * 5;
  const bw = (W - P.l - P.r) / city.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Citywide closure rate by year">
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
  );
}

function BetaBars({ rows }: { rows: BetaRow[] }) {
  const sorted = [...rows].sort((a, b) => b.beta - a.beta);
  const lo = Math.min(0, ...sorted.map((r) => r.beta));
  const hi = Math.max(2, ...sorted.map((r) => r.beta));
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  return (
    <div>
      <div className="label mb-2 grid grid-cols-[minmax(0,200px)_1fr_48px_70px_70px] gap-3 border-b border-ink pb-2">
        <span>Group</span><span>Beta (1 = moves with the city)</span><span className="text-right">β</span>
        <span className="text-right">Spread</span><span className="text-right">2019–21</span>
      </div>
      <div className="max-h-[520px] overflow-y-auto">
        {sorted.map((r) => (
          <div key={r.level} className="grid grid-cols-[minmax(0,200px)_1fr_48px_70px_70px] items-center gap-3 border-b border-rule py-1.5"
            title={`${r.label}: baseline closure rate ${r.baseline_exit_pct.toFixed(1)}%/yr (2013–17), ${r.avg_at_risk} places in a typical year`}>
            <span className="truncate text-[15px]">{r.label}</span>
            <div className="relative h-3">
              <div className="absolute inset-y-0 w-px bg-ink" style={{ left: `${x(1)}%` }} />
              <div className="absolute inset-y-0" style={{
                left: `${x(Math.min(r.beta, 1))}%`, width: `${Math.abs(x(r.beta) - x(1))}%`,
                background: r.beta > 1 ? "var(--awning)" : "var(--deli)",
              }} />
            </div>
            <span className="mono tnum text-right text-[13px]">{r.beta.toFixed(2)}</span>
            <span className={`mono tnum text-right text-[12px] ${r.spread_bp > 0 ? "text-awning" : "text-deli"}`}>{r.spread_bp > 0 ? "+" : ""}{r.spread_bp} bp</span>
            <span className="mono tnum text-right text-[12px] text-muted">{r.covid_excess_pts > 0 ? "+" : ""}{r.covid_excess_pts.toFixed(1)} pts</span>
          </div>
        ))}
      </div>
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
      intro={<>A stock&rsquo;s beta says how hard it swings with the market. Here the market is the citywide closure rate, and each neighborhood or kind of place gets a beta: above 1 amplifies the city&rsquo;s bad years, below 1 shrugs them off. With one shock this size, beta is mostly a measure of 2020. <b>Spread</b> is the normal-year closure rate above or below the city&rsquo;s, in basis points.</>}
    >
      <div className="grid gap-12 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div>
          <div className="label mb-2">Citywide closure rate, share of open places closing each year</div>
          <CityRate city={data.city} />
          <p className="mt-4 text-[15px] leading-snug text-ink-2">
            Office, tourist and commuter districts like the Financial District, Tribeca and Chinatown amplified the 2020 shock;
            residential Queens (Sunnyside, Astoria) barely moved. Delis and cafés, which live on the office lunch, swing hardest.
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
