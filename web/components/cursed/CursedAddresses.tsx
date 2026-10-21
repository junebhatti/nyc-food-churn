"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRef, useState } from "react";
import { useLand, useParks } from "@/lib/data";
import { useIsMobile } from "@/lib/useIsMobile";
import type { CursedAddress } from "@/lib/types";
import TimelineStrip from "./Timeline";
import { scrollBehavior } from "@/lib/motion";

// deck.gl only runs in the browser.
const CursedMap = dynamic(() => import("./CursedMap"), { ssr: false });

const LIST_SIZE = 12;
const yr = (y: number) => Math.floor(y);
const PRICE: Record<string, string> = { cheap: "$", mid: "$$", upscale: "$$$", fine: "$$$$" };

export default function CursedAddresses({ addresses }: { addresses: CursedAddress[] }) {
  const [selected, setSelected] = useState(0);
  const a = addresses[selected];
  const list = addresses.slice(0, LIST_SIZE);
  const land = useLand();
  const mobile = useIsMobile();
  const mapBox = useRef<HTMLDivElement>(null);
  // On phones the map sits below the list, so a row tap brings it into view to show the fly-to.
  const pick = (i: number) => {
    setSelected(i);
    if (mobile) mapBox.current?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
  };
  const parks = useParks();

  return (
    <section id="cursed" className="border-t border-ink px-4 py-14 md:px-10">
      <div className="grid gap-12 lg:grid-cols-[320px_1fr] xl:grid-cols-[400px_1fr]">
        <div>
          <p className="kicker">01 — Cursed addresses</p>
          <h1 className="mt-3 text-[34px] leading-[1.04] tracking-[-0.015em] md:text-[42px]">The storefronts that can&rsquo;t keep a tenant.</h1>
          <p className="prose-hl mt-4">
            Single storefronts ranked by how many restaurants, bars, cafés and bakeries have come and gone since 2012.
          </p>
          <div className="label mt-6 grid grid-cols-[28px_1fr_56px_56px] border-b border-ink pb-2">
            <span>#</span><span>Address</span><span className="text-right">Tenants</span><span className="text-right">Median</span>
          </div>
          {list.map((r, i) => (
            <button
              key={r.rank}
              type="button"
              onClick={() => pick(i)}
              aria-pressed={i === selected}
              className={`grid w-full grid-cols-[28px_1fr_56px_56px] items-center border-b border-rule py-2.5 text-left hover:bg-paper-raised ${i === selected ? "bg-paper-raised shadow-[inset_3px_0_0_var(--awning)]" : ""}`}
            >
              <span className="mono pl-2 text-[11px] text-muted">{r.rank}</span>
              <span className="min-w-0">
                <span className="block truncate text-[17px]">{r.address}</span>
                <span className="label block truncate">{r.neighborhood}</span>
              </span>
              <span className="mono tnum text-right text-[18px]">{r.tenants}</span>
              <span className="mono tnum text-right text-[13px] text-awning">{r.medianLife != null ? `${r.medianLife.toFixed(1)}y` : "—"}</span>
            </button>
          ))}
        </div>

        <div className="min-w-0 self-start">
        <div ref={mapBox} className="relative mb-6 h-[340px] border border-ink bg-paper md:h-[420px]">
          {land.data ? (
            <CursedMap addresses={list} land={land.data} parks={parks.data} selected={selected} onSelect={setSelected} />
          ) : (
            <div className="label flex h-full items-center justify-center">{land.error ? `Map failed to load: ${land.error}` : "Loading the map…"}</div>
          )}
          <div className="label pointer-events-none absolute left-3 top-3 bg-paper/85 px-2 py-1">Top {LIST_SIZE}<span className="hidden md:inline"> · pick a dot or a row</span></div>
        </div>
        <div className="border border-ink bg-paper-raised p-5 md:p-7">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="min-w-0">
              <div className="label">Rank {a.rank} · {a.neighborhood}</div>
              <div className="mt-1 text-[32px] leading-none md:text-[44px]">{a.address}</div>
              <Link href={`/place/${a.id}`} className="mono mt-2 inline-block text-[11px] uppercase tracking-[0.06em] underline-offset-2 hover:underline">
                Full address page, health grades &amp; links →
              </Link>
            </div>
            <div className="grid grid-cols-4 gap-5">
              <Stat label="Tenants" value={String(a.tenants)} />
              <Stat label="Median life" value={a.medianLife != null ? `${a.medianLife.toFixed(1)}y` : "—"} red />
              <Stat label="No food tenant" value={`${Math.round(a.vacantPct * 100)}%`} />
              <Stat label="Area median" value={a.areaMedianLife != null ? `${a.areaMedianLife.toFixed(1)}y` : "—"} muted />
            </div>
          </div>
          <div className="mt-6"><TimelineStrip timeline={a.timeline} /></div>
          <div className="label mt-8 flex flex-wrap gap-4">
            <Key color="var(--awning)" text="Under 1.5 yrs" />
            <Key color="var(--bodega)" text="1.5–3 yrs" />
            <Key color="var(--deli)" text="Over 3 yrs" />
            <span className="inline-flex items-center gap-1.5"><span className="vacancy-hatch inline-block h-2.5 w-4 border border-rule" />No food tenant</span>
          </div>
          {/* Cuisine and price repeat the timeline above, so they only show where there's room. */}
          <div className="mt-6">
            <table className="mono w-full text-[12px] [&_td]:pr-3 [&_th]:pr-3">
              <thead className="label text-left">
                <tr className="border-b border-ink"><th className="w-7 py-2">#</th><th>Business</th><th className="hidden xl:table-cell">Cuisine</th><th className="hidden xl:table-cell">Price</th><th className="whitespace-nowrap">Years</th><th className="text-right !pr-0">Lifespan</th></tr>
              </thead>
              <tbody>
                {a.timeline.map((t, i) => (
                  <tr key={i} className="border-b border-rule-soft">
                    <td className="py-2 text-muted">{i + 1}</td>
                    <td className="font-serif text-[15px]">{t.name}</td>
                    <td className="hidden text-muted xl:table-cell">{t.cuisine}</td>
                    <td className="hidden xl:table-cell">{t.price ? PRICE[t.price] ?? "—" : "—"}</td>
                    <td className="tnum whitespace-nowrap">{yr(t.open)}–{t.isOpen ? "now" : t.close != null ? yr(t.close) : ""}</td>
                    <td className={`tnum whitespace-nowrap text-right !pr-0 ${t.isOpen ? "text-deli" : ""}`}>{t.isOpen ? `open · ${t.life.toFixed(1)}y` : `${t.life.toFixed(1)}y`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, red = false, muted = false }: { label: string; value: string; red?: boolean; muted?: boolean }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mono tnum text-[22px] ${red ? "text-awning" : muted ? "text-muted" : ""}`}>{value}</div>
    </div>
  );
}

function Key({ color, text }: { color: string; text: string }) {
  return <span className="inline-flex items-center gap-1.5"><span className="inline-block h-2.5 w-4" style={{ background: color }} />{text}</span>;
}
