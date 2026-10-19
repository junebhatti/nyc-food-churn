"use client";

import type { Neighborhood, TenantRow } from "@/lib/types";

interface Props {
  row: TenantRow | undefined;
  hood: Neighborhood | undefined;
  x: number;
  y: number;
}

const fmtLife = (o: number, c: number | null, now: number) => `${((c ?? now) - o).toFixed(1)}y`;

/** 252px card with a 9px ink square on the building and a 28px leader to the card. */
export default function HoverCard({ row, hood, x, y }: Props) {
  if (!row) return null;
  const [address, , tenants] = row;
  const now = 2026.8;
  const recent = [...tenants].reverse().slice(0, 3);
  const earlier = tenants.length - recent.length;
  const closedLives = tenants.filter((t) => t[4] != null).map((t) => (t[4] as number) - t[3]).sort((a, b) => a - b);
  const median = closedLives.length ? closedLives[Math.floor(closedLives.length / 2)] : null;

  return (
    <div className="pointer-events-none absolute z-20" style={{ left: x - 4, top: y - 4 }}>
      <div className="h-[9px] w-[9px] bg-ink" />
      <div className="absolute left-1 top-1 h-px w-7 bg-ink" />
      <div className="absolute left-8 top-[-12px] w-[252px] border border-ink bg-paper-raised p-3">
        <div className="text-[19px] leading-tight">{address}</div>
        <div className="label mt-1">
          {hood?.name ?? "—"} · {tenants.length} tenant{tenants.length === 1 ? "" : "s"} since 2012
        </div>
        <div className="mt-2 border-t border-rule pt-2">
          {recent.map((t, i) => (
            <div key={i} className="mono flex justify-between gap-2 py-0.5 text-[11px]">
              <span className="truncate">{t[0]}</span>
              <span className={t[4] == null ? "text-deli" : "text-muted"}>
                {t[4] == null ? `open · ${fmtLife(t[3], null, now)}` : fmtLife(t[3], t[4], now)}
              </span>
            </div>
          ))}
          {earlier > 0 && (
            <div className="label mt-1">
              + {earlier} earlier{median != null ? ` · median ${median.toFixed(1)}y` : ""}
            </div>
          )}
        </div>
        <div className="mt-2 grid grid-cols-2 border-t border-rule pt-2">
          <div>
            <div className="label">3-yr closure</div>
            <div className="mono tnum text-[15px] text-awning">
              {hood?.closure3y != null ? `${Math.round(hood.closure3y * 100)}%` : "—"}
            </div>
          </div>
          <div>
            <div className="label">Rent / sq ft</div>
            <div className="mono tnum text-[15px]">{hood?.rent != null ? `$${Math.round(hood.rent)}` : "—"}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
