"use client";

export const SERIES_COLORS = ["var(--ink)", "var(--awning)", "var(--deli)", "var(--bodega-text)", "var(--violet)", "var(--muted)"];

export interface Series {
  label: string;
  values: (number | null)[];
  color: string;
  dashed?: boolean;
  strong?: boolean;
}

interface Props {
  grid: number[];
  series: Series[];
  height?: number;
  label: string;
}

const W = 640;
const PAD = { l: 44, r: 16, t: 14, b: 32 };

/** Share still open by years since opening, with the half-life (50%) line dashed. */
export default function SurvivalChart({ grid, series, height = 340, label }: Props) {
  const H = height;
  const x = (t: number) => PAD.l + (t / grid[grid.length - 1]) * (W - PAD.l - PAD.r);
  const y = (s: number) => PAD.t + (1 - s) * (H - PAD.t - PAD.b);
  const path = (v: (number | null)[]) =>
    v.reduce((d, s, i) => (s == null ? d : d + `${d ? "L" : "M"}${x(grid[i]).toFixed(1)},${y(s).toFixed(1)}`), "");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={label}>
      {[0, 0.25, 0.5, 0.75, 1].map((s) => (
        <g key={s}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(s)} y2={y(s)} stroke={s === 0.5 ? "var(--ink)" : "var(--rule-soft)"}
            strokeDasharray={s === 0.5 ? "3 3" : undefined} />
          <text x={PAD.l - 8} y={y(s) + 3} textAnchor="end" fontSize={10} fill="var(--muted)" className="mono">{s * 100}%</text>
        </g>
      ))}
      <text x={W - PAD.r} y={y(0.5) - 6} textAnchor="end" fontSize={10} fill="var(--ink)" className="mono">HALF-LIFE</text>
      {[0, 2, 4, 6, 8, 10].map((t) => (
        <text key={t} x={x(t)} y={H - 10} textAnchor="middle" fontSize={10} fill="var(--muted)" className="mono">{t}y</text>
      ))}
      <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={H - PAD.b} stroke="var(--ink)" />
      <line x1={PAD.l} x2={W - PAD.r} y1={H - PAD.b} y2={H - PAD.b} stroke="var(--ink)" />
      {series.map((s) => (
        <path key={s.label} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.strong ? 2.5 : 1.6}
          strokeDasharray={s.dashed ? "5 4" : undefined} />
      ))}
    </svg>
  );
}

export function Legend({ series }: { series: Series[] }) {
  return (
    <div className="label flex flex-wrap gap-x-4 gap-y-1">
      {series.map((s) => (
        <span key={s.label} className="inline-flex items-center gap-1.5">
          <span className="inline-block h-[2px] w-4" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}
