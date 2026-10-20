"use client";

import { QUADRANT_COLOR, QUADRANT_NAME, QUADRANT_TEXT, type Quadrant } from "@/lib/color";
import type { RiskHood } from "@/lib/quadrants";
import { useWidth } from "@/lib/useWidth";

const PAD = { l: 44, r: 12, t: 12, b: 34 };
const X_TICKS = [20, 30, 50, 100, 200, 400];
const ALWAYS_LABEL = ["SoHo", "Midtown-Times Square", "Lower East Side", "Flushing", "Bushwick", "Upper West Side", "Sunset Park"];

interface Props {
  rows: RiskHood[];
  rentMed: number;
  closeMed: number;
  selected: string;
  filter: Quadrant | null;
  onSelect: (id: string) => void;
}

export default function Scatter({ rows, rentMed, closeMed, selected, filter, onSelect }: Props) {
  const [box, W] = useWidth(500);
  const H = Math.round(Math.min(480, W * 0.96));
  const quadSize = W < 440 ? 14 : 21; // the two top labels must fit side by side on a phone
  // Rent is skewed ($12 to ~$690/sq ft/yr), so the x axis is logarithmic.
  const xMin = Math.log(Math.min(...rows.map((r) => r.rent)) * 0.85);
  const xMax = Math.log(Math.max(...rows.map((r) => r.rent)) * 1.15);
  const yLo = Math.floor(Math.min(...rows.map((r) => r.closure3y)) * 10) / 10;
  const yHi = Math.ceil(Math.max(...rows.map((r) => r.closure3y)) * 10) / 10;
  const x = (rent: number) => PAD.l + ((Math.log(rent) - xMin) / (xMax - xMin)) * (W - PAD.l - PAD.r);
  const y = (c: number) => PAD.t + (1 - (c - yLo) / (yHi - yLo)) * (H - PAD.t - PAD.b);
  const yTicks = Array.from({ length: Math.round((yHi - yLo) * 10) + 1 }, (_, i) => yLo + i / 10);
  const labelled = new Set(ALWAYS_LABEL.map((n) => rows.find((r) => r.name.startsWith(n))?.id).filter(Boolean));
  const sorted = [...rows].sort((a, b) => b.places - a.places); // big dots underneath

  return (
    <div ref={box}>
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block max-w-full" role="img" aria-label="Rent versus three-year closure odds by neighborhood">
      <line x1={x(rentMed)} x2={x(rentMed)} y1={PAD.t} y2={H - PAD.b} stroke="var(--ink)" strokeDasharray="3 3" />
      <line x1={PAD.l} x2={W - PAD.r} y1={y(closeMed)} y2={y(closeMed)} stroke="var(--ink)" strokeDasharray="3 3" />
      <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={H - PAD.b} stroke="var(--ink)" />
      <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="var(--ink)" />
      {X_TICKS.filter((t) => Math.log(t) >= xMin && Math.log(t) <= xMax).map((t) => (
        <text key={t} x={x(t)} y={H - PAD.b + 18} textAnchor="middle" fontSize={10} fill="var(--muted)" className="mono">${t}</text>
      ))}
      {yTicks.map((t) => (
        <text key={t} x={PAD.l - 8} y={y(t) + 3} textAnchor="end" fontSize={10} fill="var(--muted)" className="mono">{Math.round(t * 100)}%</text>
      ))}
      {sorted.map((r) => {
        const d = Math.sqrt(r.places) / 3.2 + 4;
        const on = r.id === selected;
        const faded = filter != null && r.quadrant !== filter;
        return (
          <g key={r.id} opacity={faded ? 0.15 : 1} onMouseEnter={() => onSelect(r.id)} onClick={() => onSelect(r.id)} className="cursor-pointer">
            {on && <circle cx={x(r.rent)} cy={y(r.closure3y)} r={d / 2 + 3.5} fill="var(--ink)" />}
            {on && <circle cx={x(r.rent)} cy={y(r.closure3y)} r={d / 2 + 2} fill="var(--paper)" />}
            <circle cx={x(r.rent)} cy={y(r.closure3y)} r={d / 2} fill={QUADRANT_COLOR[r.quadrant]}
              stroke={r.quadrant === "cd" ? "var(--ink)" : "none"} strokeWidth={1} />
          </g>
        );
      })}
      {/* Quadrant names go on top of the dots, with a page-coloured halo, so dots never cover them. */}
      {(["es", "ed", "cs", "cd"] as Quadrant[]).map((q) => (
        <text key={q} x={q[0] === "c" ? PAD.l + 8 : W - PAD.r - 8} y={q[1] === "d" ? PAD.t + 22 : H - PAD.b - 10}
          textAnchor={q[0] === "c" ? "start" : "end"} fontStyle="italic" fontSize={quadSize} fill={QUADRANT_TEXT[q]}
          stroke="var(--paper)" strokeWidth={4} paintOrder="stroke" className="pointer-events-none font-serif">
          {QUADRANT_NAME[q]}
        </text>
      ))}
      {rows.filter((r) => labelled.has(r.id) || r.id === selected).map((r) => (
        <text key={`t${r.id}`} x={x(r.rent) > W - 110 ? x(r.rent) - 8 : x(r.rent) + 8} y={y(r.closure3y) - 8}
          textAnchor={x(r.rent) > W - 110 ? "end" : "start"} fontSize={13} className="pointer-events-none font-serif"
          fill="var(--ink)" stroke="var(--paper)" strokeWidth={3} paintOrder="stroke">
          {r.name.split("-")[0]}
        </text>
      ))}
    </svg>
    </div>
  );
}
