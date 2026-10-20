import type { CursedTenant } from "@/lib/types";

export const SPAN_START = 2012.0;
export const SPAN_END = 2026.8;
const pct = (y: number) => ((Math.min(Math.max(y, SPAN_START), SPAN_END) - SPAN_START) / (SPAN_END - SPAN_START)) * 100;

/** Lifespan colour: < 1.5y awning, 1.5–3y bodega, > 3y deli. */
export function lifeColor(years: number): string {
  return years < 1.5 ? "var(--awning)" : years <= 3 ? "var(--bodega)" : "var(--deli)";
}

/** Where a tenant's bar ends: today if open, else its close date, else (no close date recorded) open + lifespan. */
const endOf = (t: CursedTenant) => (t.isOpen ? SPAN_END : t.close ?? t.open + t.life);

const ROW = "grid grid-cols-[112px_minmax(0,1fr)] items-center gap-3 md:grid-cols-[170px_minmax(0,1fr)] md:gap-5 xl:grid-cols-[220px_minmax(0,1fr)]";

/** Spans when at least one tenant was open, for the "occupied vs empty" row on top. */
function occupied(timeline: CursedTenant[]): [number, number][] {
  const spans = timeline.map((t) => [Math.max(t.open, SPAN_START), endOf(t)] as [number, number]).sort((a, b) => a[0] - b[0]);
  const out: [number, number][] = [];
  for (const [s, e] of spans) {
    const last = out[out.length - 1];
    if (last && s <= last[1]) last[1] = Math.max(last[1], e);
    else out.push([s, e]);
  }
  return out;
}

/** One row per business on a shared 2012–2026 axis, oldest first, so tenants that overlapped
 *  (several storefronts in one building) never cover each other. The top row shows when the
 *  address had any food tenant, with a hatch where it had none. */
export default function TimelineStrip({ timeline }: { timeline: CursedTenant[] }) {
  const ticks = Array.from({ length: 8 }, (_, i) => 2012 + i * 2);
  const grid = (
    <div className="pointer-events-none absolute inset-0">
      {ticks.map((y) => <div key={y} className="absolute inset-y-0 w-px bg-rule-soft" style={{ left: `${pct(y)}%` }} />)}
    </div>
  );
  return (
    <div>
      <div className={ROW}>
        <span />
        <div className="label relative h-4">
          {ticks.map((y, i) => (
            <span key={y} className={`absolute -translate-x-1/2 ${i % 2 ? "max-xl:hidden" : ""}`} style={{ left: `${pct(y)}%` }}>{y}</span>
          ))}
        </div>
      </div>

      <div className={`${ROW} mt-2 border-b border-ink pb-2`}>
        <span className="label">At this address</span>
        <div className="vacancy-hatch relative h-3 border-y border-rule">
          {occupied(timeline).map(([s, e]) => (
            <div key={s} className="absolute inset-y-0 bg-muted" style={{ left: `${pct(s)}%`, width: `${Math.max(pct(e) - pct(s), 0.3)}%` }} />
          ))}
        </div>
      </div>

      {timeline.map((t, i) => {
        const left = pct(t.open);
        const width = Math.max(pct(endOf(t)) - left, 0.4);
        const life = t.isOpen ? `open · ${t.life.toFixed(1)}y` : `${t.life.toFixed(1)}y`;
        // After the bar if there's room, else before it, else (a bar spanning nearly everything) inside its end.
        const place = left + width < 84 ? "after" : left > 16 ? "before" : "inside";
        return (
          <div key={`${t.name}-${i}`} className={`${ROW} border-b border-rule-soft py-1.5`}>
            <div className="min-w-0">
              <div className="truncate text-[15px] leading-tight" title={t.name}>{t.name}</div>
              <div className="label truncate !text-[10px]">{t.cuisine}</div>
            </div>
            <div className="relative h-5">
              {grid}
              <div
                className="absolute inset-y-1"
                title={`${t.name}: ${t.life.toFixed(1)} years`}
                style={{ left: `${left}%`, width: `${width}%`, background: lifeColor(t.life) }}
              />
              {t.open < SPAN_START && (
                <span className="mono absolute left-1 top-1/2 -translate-y-1/2 text-[10px] text-paper">◂ {Math.floor(t.open)}</span>
              )}
              <span
                className={`mono tnum absolute top-1/2 -translate-y-1/2 whitespace-nowrap text-[11px] ${place === "inside" ? "text-paper" : t.isOpen ? "text-deli" : "text-muted"}`}
                style={place === "after" ? { left: `calc(${left + width}% + 6px)` }
                  : place === "before" ? { right: `calc(${100 - left}% + 6px)` }
                  : { right: `calc(${100 - left - width}% + 6px)` }}
              >
                {life}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
