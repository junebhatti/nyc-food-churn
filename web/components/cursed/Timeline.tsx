import type { CursedTenant } from "@/lib/types";

export const SPAN_START = 2012.0;
export const SPAN_END = 2026.8;
const pct = (y: number) => ((Math.min(Math.max(y, SPAN_START), SPAN_END) - SPAN_START) / (SPAN_END - SPAN_START)) * 100;

/** Lifespan colour: < 1.5y awning, 1.5–3y bodega, > 3y deli. */
export function lifeColor(years: number): string {
  return years < 1.5 ? "var(--awning)" : years <= 3 ? "var(--bodega)" : "var(--deli)";
}

const textOn = (years: number) => (years >= 1.5 && years <= 3 ? "var(--ink)" : "var(--paper)");

const LANES = 4; // 0/2 above the strip (near/far), 1/3 below (near/far)
const LANE_H = 34;

/** 34px strip with ink rules, a vacancy hatch behind, tenant bars, and names in four lanes
 *  (two above, two below) so quick turnovers don't collide; each name stops before the next in its lane. */
export default function TimelineStrip({ timeline }: { timeline: CursedTenant[] }) {
  const ticks = Array.from({ length: 8 }, (_, i) => 2012 + i * 2);
  const room = timeline.map((t, i) => {
    const next = timeline[i + LANES];
    return next ? pct(next.open) - pct(t.open) - 0.6 : 100 - pct(t.open);
  });
  return (
    <div className="relative" style={{ paddingTop: LANE_H * 2, paddingBottom: LANE_H * 2 }}>
      {timeline.map((t, i) => {
        const lane = i % LANES;
        const above = lane % 2 === 0;
        const far = lane >= 2;
        const offset = far ? 0 : LANE_H;
        return (
          <div
            key={`l${i}`}
            className="absolute overflow-hidden border-l border-ink pl-1.5"
            style={{
              left: `${pct(t.open)}%`,
              width: `${Math.max(room[i], 3)}%`,
              ...(above ? { top: offset, height: LANE_H * 2 - offset } : { bottom: offset, height: LANE_H * 2 - offset }),
            }}
          >
            <div className={`flex h-full flex-col ${above ? "justify-start" : "justify-end"}`}>
              <span className="truncate text-[14px] leading-tight" title={t.name}>{t.name}</span>
              <span className="label truncate !text-[10px]">{t.cuisine}</span>
            </div>
          </div>
        );
      })}
      <div className="vacancy-hatch relative h-[34px] border-y border-ink">
        {timeline.map((t, i) => {
          const end = t.close ?? SPAN_END;
          const w = pct(end) - pct(t.open);
          return (
            <div
              key={i}
              title={`${t.name}: ${t.life.toFixed(1)} years`}
              className="mono absolute inset-y-0 flex items-center justify-center overflow-hidden text-[11px]"
              style={{ left: `${pct(t.open)}%`, width: `${Math.max(w, 0.4)}%`, background: lifeColor(t.life), color: textOn(t.life), boxShadow: "inset -1px 0 0 var(--paper-raised)" }}
            >
              {w > 4 ? `${t.life.toFixed(1)}y` : ""}
            </div>
          );
        })}
      </div>
      <div className="label absolute inset-x-0 bottom-[-18px] h-4">
        {ticks.map((y) => (
          <span key={y} className="absolute -translate-x-1/2" style={{ left: `${pct(y)}%` }}>{y}</span>
        ))}
      </div>
    </div>
  );
}
