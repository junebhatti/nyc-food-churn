import { ArrowUpRight } from "@phosphor-icons/react";
import { outboundLinks } from "@/lib/places";
import type { PlaceBusiness } from "@/lib/types";
import { lifeColor } from "../cursed/Timeline";

const PRICE: Record<string, string> = { cheap: "$", mid: "$$", upscale: "$$$", fine: "$$$$" };
const GRADE_COLOR: Record<string, string> = { A: "var(--deli)", B: "var(--bodega-text)", C: "var(--awning)" };
const SOURCE_NOTE: Record<string, string> = {
  sla: "Known from its liquor licence (no food permit).",
  snap: "Known from SNAP retailer records; dates are SNAP authorization dates.",
};
const yr = (y: number | null) => (y == null ? "?" : String(Math.floor(y)));

export default function BusinessCard({ b, address, boro }: { b: PlaceBusiness; address: string; boro: string | null }) {
  const links = outboundLinks(b.name, address, boro);
  const ins = b.inspections;
  return (
    <article className="flex flex-col border border-ink bg-paper-raised p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[22px] leading-tight">{b.name}</h3>
          <div className="label mt-1">
            {b.category}{b.cuisine && b.cuisine !== b.category ? ` · ${b.cuisine}` : ""}{b.price ? ` · ${PRICE[b.price] ?? ""}` : ""}{b.chain ? " · Chain" : ""}{b.liquor ? " · Liquor licence" : ""}
          </div>
        </div>
        <span className={`mono shrink-0 border px-2 py-1 text-[10px] uppercase tracking-[0.06em] ${b.isOpen ? "border-deli text-deli" : "border-awning text-awning"}`}>
          {b.isOpen ? "Open" : "Closed"}
        </span>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <div className="h-2 w-10" style={{ background: lifeColor(b.life) }} />
        <span className="mono tnum text-[13px]">
          {b.isOpen ? `Open since ${yr(b.open)} · ${b.life.toFixed(1)} yrs` : `${yr(b.open)}–${yr(b.close)} · lasted ${b.life.toFixed(1)} yrs`}
        </span>
      </div>

      {ins && (
        <div className="mt-4 flex items-center gap-3 border-t border-rule pt-3">
          {ins.grade ? (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center border-2 text-[20px] font-medium" style={{ borderColor: GRADE_COLOR[ins.grade], color: GRADE_COLOR[ins.grade] }}>
              {ins.grade}
            </span>
          ) : (
            <span className="mono flex h-9 w-9 shrink-0 items-center justify-center border border-rule text-[10px] text-muted">—</span>
          )}
          <div className="mono text-[11px] leading-snug text-ink-2">
            Health grade{ins.gradeDate ? ` (${ins.gradeDate})` : ""}
            <br />
            {ins.n} inspection{ins.n === 1 ? "" : "s"} · last {ins.last}
            {ins.scores.length > 0 && <> · recent scores {ins.scores.map((s) => s[1]).join(", ")}</>}
          </div>
        </div>
      )}

      {b.acclaim.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {b.acclaim.map((a, i) => (
            <li key={i}>
              {a.url ? (
                <a href={a.url} target="_blank" rel="noopener noreferrer" className="mono inline-flex items-center gap-1 border border-ink px-2 py-1 text-[10px] uppercase tracking-[0.04em] hover:bg-paper">
                  {a.label} <ArrowUpRight size={10} />
                </a>
              ) : (
                <span className="mono inline-block border border-ink px-2 py-1 text-[10px] uppercase tracking-[0.04em]">{a.label}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {SOURCE_NOTE[b.source] && <p className="label mt-3">{SOURCE_NOTE[b.source]}</p>}

      <div className="mono mt-auto flex flex-wrap gap-x-4 gap-y-1 border-t border-rule pt-3 text-[11px] uppercase tracking-[0.06em]">
        <a href={links.google} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">Google Maps <ArrowUpRight size={11} /></a>
        <a href={links.yelp} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">Yelp reviews <ArrowUpRight size={11} /></a>
        <a href={links.web} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">Search <ArrowUpRight size={11} /></a>
      </div>
    </article>
  );
}
