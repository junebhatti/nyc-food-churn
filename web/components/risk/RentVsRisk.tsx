"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { useLand, useNeighborhoods } from "@/lib/data";
import { QUADRANT_COLOR, QUADRANT_NAME, QUADRANT_TEXT, type Quadrant } from "@/lib/color";
import { dominating, riskHoods, type RiskHood } from "@/lib/quadrants";
import { useIsMobile } from "@/lib/useIsMobile";
import Scatter from "./Scatter";

const RiskMap = dynamic(() => import("./RiskMap"), { ssr: false });
const DEFAULT = "Lower East Side";

export default function RentVsRisk() {
  const hoods = useNeighborhoods();
  const land = useLand();
  const mobile = useIsMobile();
  const data = useMemo(() => (hoods.data ? riskHoods(hoods.data) : null), [hoods.data]);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Quadrant | null>(null);

  if (!data) {
    return (
      <section id="rent-risk" className="border-t border-ink px-4 py-14 md:px-10">
        <p className="label">{hoods.error ? `Neighborhood data failed to load: ${hoods.error}` : "Loading neighborhoods…"}</p>
      </section>
    );
  }
  const { rows, rentMed, closeMed } = data;
  const sel = rows.find((r) => r.id === selected) ?? rows.find((r) => r.name.startsWith(DEFAULT)) ?? rows[0];
  const better = dominating(sel, rows);
  const counts = Object.fromEntries((["cs", "es", "cd", "ed"] as Quadrant[]).map((q) => [q, rows.filter((r) => r.quadrant === q).length]));

  return (
    <section id="rent-risk" className="border-t border-ink px-4 py-14 md:px-10">
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <p className="kicker">03 — Is the rent worth the risk?</p>
          <h1 className="mt-3 text-[34px] leading-[1.04] tracking-[-0.015em] md:text-[44px]">Pricier streets are a little safer. Rent isn&rsquo;t why.</h1>
        </div>
        <p className="prose-hl self-end">
          One dot per neighborhood. Across: storefront rent per square foot per year. Up: the odds a new place closes within three years.
          In the priciest third of neighborhoods 31% of new places close by year three, against 37% in the cheapest third. But once cuisine,
          chains and a storefront&rsquo;s history are accounted for, rent stops predicting closure at all.{mobile === false && <> On the map, each neighborhood is one
          block, raised by its closure odds.</>}
        </p>
      </div>

      {/* Three columns only where the map gets real width; below that it spans the row under the panel and scatter. */}
      <div className="mt-10 grid items-start gap-9 lg:grid-cols-[280px_minmax(0,1fr)] min-[1360px]:grid-cols-[280px_minmax(0,500px)_1fr]">
        <Panel sel={sel} rows={rows} rentMed={rentMed} closeMed={closeMed} better={better} counts={counts}
          filter={filter} setFilter={setFilter} onSelect={setSelected} />
        <Scatter rows={rows} rentMed={rentMed} closeMed={closeMed} selected={sel.id} filter={filter} onSelect={setSelected} />
        {mobile === false && land.data && (
          <div className="lg:col-span-2 min-[1360px]:col-span-1">
            <div className="relative h-[480px]" role="region" aria-label="3D map: one block per neighborhood, raised by its 3-year closure odds; the same data is in the scatter plot."><RiskMap rows={rows} land={land.data} selected={sel.id} filter={filter} onSelect={setSelected} /></div>
            <p className="label mt-2">Block height = 3-yr closure odds · Colour = quadrant</p>
          </div>
        )}
      </div>
    </section>
  );
}

interface PanelProps {
  sel: RiskHood;
  rows: RiskHood[];
  rentMed: number;
  closeMed: number;
  better: RiskHood[];
  counts: Record<string, number>;
  filter: Quadrant | null;
  setFilter: (q: Quadrant | null) => void;
  onSelect: (id: string) => void;
}

function Panel({ sel, rows, rentMed, closeMed, better, counts, filter, setFilter, onSelect }: PanelProps) {
  const rentDiff = Math.round((sel.rent / rentMed - 1) * 100);
  const closeDiff = Math.round((sel.closure3y - closeMed) * 100);
  const maxRent = Math.max(...rows.map((r) => r.rent));
  const maxClose = Math.max(...rows.map((r) => r.closure3y));
  return (
    <div className="border-t border-ink">
      <div className="border-b border-rule py-4">
        <div className="font-serif text-[15px] italic" style={{ color: QUADRANT_TEXT[sel.quadrant] }}>{QUADRANT_NAME[sel.quadrant]}</div>
        <div className="text-[30px] leading-tight">{sel.name}</div>
        <div className="label mt-1">{sel.boro}</div>
      </div>
      <div className="grid grid-cols-2 gap-y-3 border-b border-rule py-4">
        <Stat label="Rent / sq ft / yr" value={`$${Math.round(sel.rent)}`} />
        <Stat label="3-yr closure" value={`${Math.round(sel.closure3y * 100)}%`} red />
        <Stat label="Places" value={sel.places.toLocaleString()} />
        <Stat label="Median life" value={sel.medianLife != null ? `${sel.medianLife.toFixed(1)}y` : "—"} />
      </div>
      <div className="border-b border-rule py-4">
        <div className="label mb-2">Against the city median</div>
        <Bar label="Rent" value={sel.rent / maxRent} tick={rentMed / maxRent} color="var(--ink)" note={`${rentDiff > 0 ? "+" : ""}${rentDiff}%`} />
        <Bar label="Closure" value={sel.closure3y / maxClose} tick={closeMed / maxClose} color="var(--awning)" note={`${closeDiff > 0 ? "+" : ""}${closeDiff} pts`} />
      </div>
      <div className="border-b border-rule py-4">
        <div className="label">Risk-adjusted rent</div>
        <div className="mono tnum mt-1 text-[24px]">${Math.round(sel.riskAdj)} <span className="label">rank {sel.riskAdjRank} of {rows.length}</span></div>
        <p className="mt-1 text-[13px] leading-snug text-muted">Rent divided by the odds of making year three. Lower is better value.</p>
      </div>
      <div className="border-b border-rule py-4">
        <div className="label mb-1">Cheaper and safer</div>
        {better.length === 0 ? (
          <p className="text-[15px] text-deli">Nothing beats it on both rent and risk.</p>
        ) : (
          better.map((b) => (
            <button key={b.id} type="button" onMouseEnter={() => onSelect(b.id)} onClick={() => onSelect(b.id)}
              className="flex w-full items-baseline justify-between py-1 text-left hover:bg-paper-raised">
              <span className="text-[15px]">{b.name}</span>
              <span className="mono text-[11px] text-muted">${Math.round(b.rent)} · {Math.round(b.closure3y * 100)}%</span>
            </button>
          ))
        )}
      </div>
      <div className="py-4">
        <div className="label mb-2 flex justify-between">
          <span>Filter by quadrant</span>
          {filter && <button type="button" onClick={() => setFilter(null)} className="underline">Show all</button>}
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {(["cs", "es", "cd", "ed"] as Quadrant[]).map((q) => (
            <button key={q} type="button" aria-pressed={filter === q} onClick={() => setFilter(filter === q ? null : q)}
              className={`flex items-center gap-1.5 border px-2 py-1.5 text-left text-[12px] ${filter === q ? "border-ink bg-paper-raised" : "border-transparent hover:bg-paper-raised"}`}>
              <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: QUADRANT_COLOR[q] }} />
              <span className="flex-1">{QUADRANT_NAME[q]}</span>
              <span className="mono text-muted">{counts[q]}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, red = false }: { label: string; value: string; red?: boolean }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mono tnum text-[22px] ${red ? "text-awning" : ""}`}>{value}</div>
    </div>
  );
}

function Bar({ label, value, tick, color, note }: { label: string; value: number; tick: number; color: string; note: string }) {
  return (
    <div className="mb-2 grid grid-cols-[52px_1fr_56px] items-center gap-2">
      <span className="label">{label}</span>
      <div className="relative h-2 bg-rule-soft">
        <div className="h-full" style={{ width: `${value * 100}%`, background: color }} />
        <div className="absolute -top-1 h-4 w-px bg-ink" style={{ left: `${tick * 100}%` }} />
      </div>
      <span className="mono tnum text-right text-[11px]">{note}</span>
    </div>
  );
}
