"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useBuildings, useNeighborhoods } from "@/lib/data";
import { placeHref } from "@/lib/places";
import { loadIndex } from "@/lib/search";
import { useAtlas } from "@/lib/store";
import type { BetaData } from "@/lib/types";
import betaJson from "@/public/data/beta.json";

const betaOf = new Map((betaJson as unknown as BetaData).rows.filter((r) => r.group === "nta2020").map((r) => [r.level, r.beta]));
const TOP = 8;

/** Shown under the map while a neighbourhood is selected: its numbers and its most-churned addresses. */
export default function NeighborhoodPanel() {
  const { nta, setNta } = useAtlas();
  const hoods = useNeighborhoods();
  const buildings = useBuildings();
  const [addr, setAddr] = useState<Map<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!nta || addr) return;
    loadIndex()
      .then((rows) => setAddr(new Map(rows.map(([id, a]) => [id, a]))))
      .catch((e: Error) => setError(e.message));
  }, [nta, addr]);

  const hood = hoods.data?.find((h) => h.id === nta);
  const top = useMemo(() => {
    if (!hood || !buildings.data || !hoods.data) return [];
    const idx = hoods.data.indexOf(hood);
    return buildings.data.filter((b) => b.nta === idx).sort((a, b) => b.tenants - a.tenants).slice(0, TOP);
  }, [hood, buildings.data, hoods.data]);

  if (!nta || !hood) return null;
  const beta = betaOf.get(nta);
  return (
    <section className="border-t border-ink bg-paper-raised px-4 py-8 md:px-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="kicker">Neighborhood · {hood.boro}</p>
          <h2 className="mt-2 text-[32px] leading-tight md:text-[40px]">{hood.name}</h2>
        </div>
        <button type="button" onClick={() => setNta(null)} className="mono text-[11px] uppercase tracking-[0.06em] underline-offset-2 hover:underline">
          Show all of NYC
        </button>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6 border-t border-ink pt-3 md:grid-cols-5">
        <Stat label="Places since 2012" value={hood.places.toLocaleString()} />
        <Stat label="3-yr closure odds" value={hood.closure3y != null ? `${Math.round(hood.closure3y * 100)}%` : "—"} red />
        <Stat label="Median lifespan" value={hood.medianLife != null ? `${hood.medianLife.toFixed(1)}y` : "—"} />
        <Stat label="Rent / sq ft / yr" value={hood.rent != null ? `$${Math.round(hood.rent)}` : "—"} />
        <Stat label="Beta" value={beta != null ? beta.toFixed(2) : "—"} />
      </div>
      <div className="label mb-2 mt-8">Addresses with the most businesses since 2012 (food halls and markets included)</div>
      {error && <p className="label">{error}</p>}
      <div className="grid gap-x-8 md:grid-cols-2">
        {top.map((b) => (
          <Link key={b.id} href={placeHref(b.id)} className="flex items-baseline justify-between border-b border-rule py-2 hover:bg-paper">
            <span className="text-[16px]">{addr?.get(b.id) ?? "…"}</span>
            <span className="mono text-[11px] text-muted">{b.tenants} businesses{b.medianLife != null ? ` · median ${b.medianLife.toFixed(1)}y` : ""}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

function Stat({ label, value, red = false }: { label: string; value: string; red?: boolean }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mono tnum text-[24px] ${red ? "text-awning" : ""}`}>{value}</div>
    </div>
  );
}
