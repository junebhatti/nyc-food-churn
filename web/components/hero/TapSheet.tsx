"use client";

import { ArrowRight, X } from "@phosphor-icons/react";
import type { Neighborhood, TenantRow } from "@/lib/types";
import { lifeColor } from "../cursed/Timeline";

interface Props {
  row: TenantRow | undefined;
  hood: Neighborhood | undefined;
  loading: boolean;
  onClose: () => void;
  placeId: string | undefined;
}

const START = 2012;
const END = 2026.8;

/** Mobile bottom sheet that replaces the hover card (artboard 1g). */
export default function TapSheet({ row, hood, loading, onClose, placeId }: Props) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-paper/45" onClick={onClose} aria-hidden />
      <div role="dialog" aria-label="Building details" className="fixed inset-x-0 bottom-0 z-50 max-h-[80svh] overflow-y-auto border-t border-ink bg-paper-raised px-4 pb-6 pt-2">
        <div className="mx-auto h-[3px] w-9 bg-rule" />
        <div className="mt-3 flex items-start justify-between gap-3">
          <div>
            <div className="label">{hood?.name ?? "—"}</div>
            <div className="mt-1 text-[28px] leading-tight">{row?.[0] ?? (loading ? "Loading…" : "—")}</div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="flex h-11 w-11 shrink-0 items-center justify-center border border-ink"><X size={18} /></button>
        </div>
        {row && (
          <>
            <div className="mt-4 grid grid-cols-3 border-t border-rule pt-3">
              <Stat label="Tenants" value={String(row[2].length)} />
              <Stat label="3-yr close" value={hood?.closure3y != null ? `${Math.round(hood.closure3y * 100)}%` : "—"} red />
              <Stat label="Rent/sq ft" value={hood?.rent != null ? `$${Math.round(hood.rent)}` : "—"} />
            </div>
            <div className="vacancy-hatch relative mt-4 h-[22px] border-y border-ink">
              {row[2].map((t, i) => {
                const o = Math.max(t[3], START);
                const c = t[4] ?? END;
                return (
                  <div key={i} className="absolute inset-y-0" style={{ left: `${((o - START) / (END - START)) * 100}%`, width: `${((c - o) / (END - START)) * 100}%`, background: lifeColor(c - t[3]), boxShadow: "inset -1px 0 0 var(--paper-raised)" }} />
                );
              })}
            </div>
            <div className="label mt-1 flex justify-between"><span>2012</span><span>2019</span><span>2026</span></div>
            <div className="mt-3">
              {[...row[2]].reverse().slice(0, 3).map((t, i) => (
                <div key={i} className="flex min-h-11 items-center justify-between border-b border-rule">
                  <span className="text-[15px]">{t[0]}</span>
                  <span className={`mono text-[11px] ${t[4] == null ? "text-deli" : "text-muted"}`}>
                    {t[4] == null ? `open · ${(END - t[3]).toFixed(1)}y` : `${(t[4] - t[3]).toFixed(1)}y`}
                  </span>
                </div>
              ))}
            </div>
            <a href={placeId ? `/place/${placeId}` : "#cursed"} className="mono mt-4 flex h-11 items-center justify-center gap-2 border border-ink text-[11px] uppercase tracking-[0.06em]">
              Full timeline <ArrowRight size={14} />
            </a>
          </>
        )}
      </div>
    </>
  );
}

function Stat({ label, value, red = false }: { label: string; value: string; red?: boolean }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mono tnum text-[18px] ${red ? "text-awning" : ""}`}>{value}</div>
    </div>
  );
}
