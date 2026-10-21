"use client";

import { useState } from "react";
import type { HalfLifeData } from "@/lib/types";
import SurvivalChart, { Legend, SERIES_COLORS, type Series } from "../charts/SurvivalChart";
import Section, { Stat, pct } from "./Section";

const TABS = [
  { id: "boro", label: "Borough" },
  { id: "family_top", label: "Cuisine" },
  { id: "chain", label: "Chain" },
  { id: "cohort", label: "Year opened" },
] as const;
const MAX_LINES = 5;
const yrs = (m: number | null) => (m == null ? "10y+" : `${m.toFixed(1)}y`);
const DATA_END = 2026.8;
/** Years a "Year opened" group has actually been followed (from its first year), or 10 for other tabs. */
const followed = (tab: string, level: string) => (tab === "cohort" ? Math.min(10, DATA_END - Number(level.slice(0, 4))) : 10);
/** Median label: "not yet" when a recent cohort hasn't reached 50% within the years it's been followed. */
const median = (tab: string, level: string, m: number | null) => (m == null && followed(tab, level) < 10 ? "not yet" : yrs(m));

export default function HalfLife({ data }: { data: HalfLifeData }) {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("boro");
  const rows = data.groups[tab].rows;
  const [picked, setPicked] = useState<Record<string, string[]>>({});
  const chosen = picked[tab] ?? rows.slice(0, MAX_LINES).map((r) => r.level);
  const all = data.groups.all.rows[0];

  const toggle = (level: string) => {
    const cur = new Set(chosen);
    if (cur.has(level)) cur.delete(level);
    else if (cur.size < MAX_LINES) cur.add(level);
    setPicked({ ...picked, [tab]: [...cur] });
  };

  const series: Series[] = [
    { label: "All places", values: all.curve, color: "var(--ink)", strong: true, dashed: true },
    ...rows.filter((r) => chosen.includes(r.level)).map((r, i) => ({ label: r.level, values: r.curve.map((s, k) => (data.grid[k] <= followed(tab, r.level) ? s : null)), color: SERIES_COLORS[(i + 1) % SERIES_COLORS.length] })),
  ];

  return (
    <Section
      id="half-life"
      kicker="02 — Half-life"
      title={<>Half of new places are gone in <span className="text-awning">{yrs(all.median).replace("y", " years")}</span>.</>}
      intro={<>Every restaurant, bar, café and bakery that opened since mid-2012, followed until it closed or until today. The curve is the share still open after each year; where it crosses 50% is the half-life.</>}
    >
      <div className="mb-8 flex flex-wrap gap-10 border-t border-ink pt-3">
        <Stat label="Still open after 1 year" value={pct(all.s1)} />
        <Stat label="After 3 years" value={pct(all.s3)} />
        <Stat label="After 5 years" value={pct(all.s5)} tone="red" />
        <Stat label="Places followed" value={all.n.toLocaleString()} tone="muted" />
      </div>
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div>
          <div role="group" aria-label="Split by" className="mono mb-4 inline-grid grid-cols-4 border border-ink text-[11px] uppercase tracking-[0.06em]">
            {TABS.map((t, i) => (
              <button key={t.id} type="button" aria-pressed={tab === t.id} onClick={() => setTab(t.id)}
                className={`h-9 px-3 ${i ? "border-l border-ink" : ""} ${tab === t.id ? "bg-ink text-paper" : "hover:bg-paper-raised"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <SurvivalChart grid={data.grid} series={series} label={`Survival curves by ${tab}`} />
          <div className="mt-2"><Legend series={series} /></div>
        </div>
        <div>
          <div className="label grid grid-cols-[1fr_52px_44px_44px_44px] border-b border-ink pb-2">
            <span>{TABS.find((t) => t.id === tab)?.label}</span><span className="text-right">Median</span>
            <span className="text-right">1y</span><span className="text-right">3y</span><span className="text-right">5y</span>
          </div>
          <div className="max-h-[420px] overflow-y-auto">
            {[...rows].sort((a, b) => (b.median ?? 99) - (a.median ?? 99)).map((r) => {
              const on = chosen.includes(r.level);
              const color = on ? SERIES_COLORS[(rows.filter((x) => chosen.includes(x.level)).indexOf(r) + 1) % SERIES_COLORS.length] : "transparent";
              return (
                <button key={r.level} type="button" onClick={() => toggle(r.level)} aria-pressed={on}
                  className={`mono grid w-full grid-cols-[1fr_52px_44px_44px_44px] items-center border-b border-rule py-2 text-left text-[12px] hover:bg-paper-raised ${on ? "bg-paper-raised" : ""}`}>
                  <span className="flex min-w-0 items-center gap-2 font-serif text-[15px]">
                    <span className="inline-block h-[3px] w-3 shrink-0" style={{ background: color }} />
                    <span className="truncate">{r.level}</span>
                  </span>
                  <span className="tnum text-right">{median(tab, r.level, r.median)}</span>
                  <span className="tnum text-right text-muted">{pct(r.s1)}</span>
                  <span className="tnum text-right text-muted">{pct(r.s3)}</span>
                  <span className="tnum text-right">{pct(r.s5)}</span>
                </button>
              );
            })}
          </div>
          <p className="label mt-3">Tap a row to add or remove it (up to {MAX_LINES}). Recent openings are followed for fewer years.</p>
        </div>
      </div>
    </Section>
  );
}
