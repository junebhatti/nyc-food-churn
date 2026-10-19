"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { List } from "@phosphor-icons/react";
import { useAtlas } from "@/lib/store";
import { useBuildings, useLand, useNeighborhoods, useParks, useTenants } from "@/lib/data";
import { LEGEND_CHIPS } from "@/lib/color";
import { LEGEND } from "@/lib/metrics";
import { useIsMobile } from "@/lib/useIsMobile";
import type { Summary, Yearly } from "@/lib/types";
import YearScrubber from "../controls/YearScrubber";
import { CategoryButtons, ViewToggle } from "../controls/Toggles";
import HoverCard from "./HoverCard";
import TapSheet from "./TapSheet";
import type { HoverInfo } from "./HeroMap";

// deck.gl only runs in the browser; load it lazily so the text paints first.
const HeroMap = dynamic(() => import("./HeroMap"), { ssr: false });

interface Props {
  summary: Summary;
  yearly: Yearly;
}

export default function Hero({ summary, yearly }: Props) {
  const mobile = useIsMobile();
  const { year, view, category } = useAtlas();
  const buildings = useBuildings();
  const hoods = useNeighborhoods();
  const land = useLand();
  const parks = useParks();
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [tapped, setTapped] = useState<number | null>(null);
  const tenants = useTenants(hover != null || tapped != null);
  const error = buildings.error ?? hoods.error ?? land.error;
  const ready = buildings.data && hoods.data && land.data;
  const openInYear = yearly[category].alive[year - yearly.years[0]];
  const legend = LEGEND[view];

  const map = ready ? (
    <HeroMap
      buildings={buildings.data!}
      hoods={hoods.data!}
      land={land.data!}
      parks={parks.data}
      flat={mobile === true}
      initialZoom={mobile ? 8.75 : 9.8}
      onHover={mobile ? undefined : setHover}
      onTap={mobile ? setTapped : undefined}
    />
  ) : (
    <div className="label flex h-full items-center justify-center">{error ? `Map data failed to load: ${error}` : "Loading the city…"}</div>
  );

  const hoodOf = (i: number | null) => {
    const b = i != null ? buildings.data?.[i] : undefined;
    return b?.nta != null ? hoods.data?.[b.nta] : undefined;
  };

  const headline = (
    <>
      <p className="kicker">00 — The city eats its restaurants</p>
      <h1 className="mt-3 text-[38px] leading-[1.02] tracking-[-0.02em] md:text-[62px]">
        {Math.round(summary.opened / 1000)},000 places opened.{" "}
        <em className="text-awning">{Math.round(summary.openNow / 1000)},000 are still here.</em>
      </h1>
    </>
  );

  if (mobile) {
    return (
      <section className="px-4">
        <header className="flex h-[52px] items-center justify-between border-b border-rule">
          <span className="text-[20px] font-medium">Half-Life</span>
          <button type="button" aria-label="Menu" className="flex h-11 w-11 items-center justify-center"><List size={22} /></button>
        </header>
        <div className="pt-6">{headline}</div>
        <div className="mt-5"><ViewToggle mobile /></div>
        <div className="relative mt-4 aspect-square w-full bg-paper">{map}</div>
        <div className="mt-2 flex">{LEGEND_CHIPS.map((c) => <div key={c} className="h-2 flex-1" style={{ background: c }} />)}</div>
        <div className="label mt-1 flex justify-between"><span>{legend.lo}</span><span>{legend.hi}</span></div>
        <p className="label mt-3">Flat map on small screens. Tap a hex for its buildings.</p>
        {/* Sticky within the map section only, so it doesn't cover the sections below. */}
        <div className="sticky bottom-0 z-30 -mx-4 mt-4 border-t border-ink bg-paper px-4 pb-3.5 pt-2.5">
          <YearScrubber yearly={yearly} compact openNow={openInYear} />
          <div className="mt-2"><CategoryButtons mobile /></div>
        </div>
        {tapped != null && (
          <TapSheet row={tenants.data?.[tapped]} hood={hoodOf(tapped)} loading={!tenants.data} onClose={() => setTapped(null)} />
        )}
      </section>
    );
  }

  return (
    <section className="relative flex h-[min(900px,100svh)] min-h-[720px] flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-rule px-10">
        <div className="flex items-baseline gap-4">
          <span className="text-[22px] font-medium">Half-Life</span>
          <span className="label">An atlas of NYC restaurant churn, 2012–2026</span>
        </div>
        <nav className="mono flex gap-5 text-[11px] uppercase tracking-[0.06em] text-muted">
          <a href="#cursed" className="hover:text-ink">01 Cursed addresses</a>
          <a href="#half-life" className="hover:text-ink">02 Half-life</a>
          <a href="#rent-risk" className="hover:text-ink">03 Rent vs risk</a>
          <a href="#beta" className="hover:text-ink">04 Beta</a>
          <a href="#pitch" className="hover:text-ink">07 Pitch yours</a>
        </nav>
      </header>
      <div className="relative min-h-0 flex-1">
        <div className="absolute inset-y-0 left-[18%] right-0" onMouseLeave={() => setHover(null)}>
          {map}
          {hover && <HoverCard row={tenants.data?.[hover.building]} hood={hoodOf(hover.building)} x={hover.x} y={hover.y} />}
        </div>
        <div className="pointer-events-none absolute left-10 top-10 w-[440px]">
          {headline}
          <p className="prose-hl mt-4 max-w-[400px]">
            Every column is a building that has housed a restaurant, bar, café, bakery or bodega since 2012. Height is how many have come and gone.
          </p>
          <div className="mt-5 flex gap-10 border-t border-ink pt-3">
            <div><div className="label">Open in {year}</div><div className="mono tnum text-[26px]">{openInYear.toLocaleString()}</div></div>
            <div><div className="label">Median lifespan</div><div className="mono tnum text-[26px]">{summary.medianLife} yrs</div></div>
          </div>
        </div>
        <div className="pointer-events-none absolute right-10 top-6 text-right">
          <div className="label text-ink">{legend.title}</div>
          <div className="ml-auto mt-2 flex w-40">{LEGEND_CHIPS.map((c) => <div key={c} className="h-2 flex-1" style={{ background: c }} />)}</div>
          <div className="label mt-1 flex w-40 justify-between"><span>{legend.lo}</span><span>{legend.hi}</span></div>
          <div className="label mt-2 inline-flex items-center gap-1.5"><span className="inline-block h-2 w-3 bg-[#DAD2C3]" /> Dark this year</div>
        </div>
      </div>
      <div className="flex h-[100px] shrink-0 items-center gap-8 border-t border-ink px-10">
        <div><div className="label mb-1.5">View</div><ViewToggle /></div>
        <div><div className="label mb-1.5">Category</div><CategoryButtons /></div>
        <YearScrubber yearly={yearly} />
      </div>
    </section>
  );
}
