"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAtlas } from "@/lib/store";
import { useBuildings, useLand, useNeighborhoods, useParks, useTenants, useYearlyByNta } from "@/lib/data";
import { placeHref } from "@/lib/places";
import { LEGEND_CHIPS } from "@/lib/color";
import { LEGEND, viewNote } from "@/lib/metrics";
import { useIsMobile } from "@/lib/useIsMobile";
import { useWidth } from "@/lib/useWidth";
import type { Summary, Yearly } from "@/lib/types";
import YearScrubber from "../controls/YearScrubber";
import { CategoryButtons, ViewToggle } from "../controls/Toggles";
import NeighborhoodPicker, { useNtaUrlSync } from "../controls/NeighborhoodPicker";
import TopBar from "../TopBar";
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
  const { year, view, category, nta } = useAtlas();
  const router = useRouter();
  useNtaUrlSync();
  const byNta = useYearlyByNta(nta != null);
  const buildings = useBuildings();
  const hoods = useNeighborhoods();
  const land = useLand();
  const parks = useParks();
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [tapped, setTapped] = useState<number | null>(null);
  const tenants = useTenants(hover != null || tapped != null);
  const error = buildings.error ?? hoods.error ?? land.error;
  const ready = buildings.data && hoods.data && land.data;
  const ntaSeries = nta ? byNta.data?.[nta]?.[category] : undefined;
  const series = ntaSeries ?? yearly[category];
  const openInYear = series.alive[year - yearly.years[0]];
  const hoodName = nta ? hoods.data?.find((h) => h.id === nta)?.name : undefined;
  // The citywide median, or the chosen neighbourhood's (its places opened since 2012, all categories).
  const hoodLife = nta ? hoods.data?.find((h) => h.id === nta)?.medianLife ?? null : null;
  const legend = LEGEND[view];
  const [mapArea, mapW, mapH] = useWidth(1000);

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
      onOpen={(i) => router.push(placeHref(buildings.data![i].id))}
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
      <>
      <TopBar current="map" />
      <section className="px-4">
        <div className="pt-6">{headline}</div>
        <div className="mt-5"><ViewToggle mobile /></div>
        <div className="mt-2"><NeighborhoodPicker hoods={hoods.data} mobile /></div>
        <div className="relative mt-4 aspect-square w-full bg-paper">{map}</div>
        <div className="mt-2 flex">{LEGEND_CHIPS.map((c) => <div key={c} className="h-2 flex-1" style={{ background: c }} />)}</div>
        <div className="label mt-1 flex justify-between"><span>{legend.lo}</span><span>{legend.hi}</span></div>
        <p className="label mt-3">Flat map on small screens. Tap a hex for its buildings.</p>
        {/* Sticky within the map section only, so it doesn't cover the sections below. */}
        <div className="sticky bottom-0 z-30 -mx-4 mt-4 border-t border-ink bg-paper px-4 pb-3.5 pt-2.5">
          <YearScrubber yearly={yearly} compact openNow={openInYear} series={series} />
          <div className="mt-2"><CategoryButtons mobile /></div>
        </div>
        {tapped != null && (
          <TapSheet row={tenants.data?.[tapped]} hood={hoodOf(tapped)} loading={!tenants.data} onClose={() => setTapped(null)} placeId={buildings.data?.[tapped]?.id} />
        )}
      </section>
      </>
    );
  }

  return (
    <section className="relative flex h-svh min-h-[720px] flex-col">
      <TopBar current="map" />
      <div className="relative min-h-0 flex-1">
        <div ref={mapArea} className="absolute inset-y-0 left-[18%] right-0" onMouseLeave={() => setHover(null)}>
          {map}
          {/* Fades the map's left edge into the page: hides the canvas edge, which shows as a seam
              once zoomed in, and keeps the headline readable over the columns. */}
          <div className="pointer-events-none absolute inset-y-0 left-0 w-[360px] bg-gradient-to-r from-paper from-15% to-transparent" />
          {hover && <HoverCard row={tenants.data?.[hover.building]} hood={hoodOf(hover.building)} x={hover.x} y={hover.y} bounds={{ width: mapW, height: mapH }} />}
        </div>
        <div className="pointer-events-none absolute left-10 top-10 w-[440px]">
          {headline}
          <p className="prose-hl mt-4 max-w-[400px]">
            {viewNote(view, category)}
          </p>
          <div className="mt-5 flex gap-10 border-t border-ink pt-3">
            <div><div className="label">Open in {year}{hoodName ? ` · ${hoodName.split("-")[0]}` : ""}</div><div className="mono tnum text-[26px]">{openInYear.toLocaleString()}</div></div>
            <div><div className="label">Median lifespan{nta && hoodLife != null ? ` · ${hoodName?.split("-")[0]}` : ""}</div><div className="mono tnum text-[26px]">{nta && hoodLife != null ? hoodLife.toFixed(1) : summary.medianLife} yrs</div></div>
          </div>
        </div>
        <div className="absolute right-10 top-6 flex flex-col items-end text-right">
          <div className="label mb-1.5">Neighborhood</div>
          <NeighborhoodPicker hoods={hoods.data} />
        </div>
        <div className="pointer-events-none absolute right-10 top-[96px] text-right">
          <div className="label text-ink">{legend.title}</div>
          <div className="ml-auto mt-2 flex w-40">{LEGEND_CHIPS.map((c) => <div key={c} className="h-2 flex-1" style={{ background: c }} />)}</div>
          <div className="label mt-1 flex w-40 justify-between"><span>{legend.lo}</span><span>{legend.hi}</span></div>
          <div className="label mt-2 inline-flex items-center gap-1.5"><span className="inline-block h-2 w-3 bg-[var(--dead)]" /> Dark this year</div>
        </div>
      </div>
      {/* One row from 1280px; below that the slider wraps to its own full-width row. */}
      <div className="flex shrink-0 flex-wrap items-center gap-x-8 gap-y-3 border-t border-ink px-10 py-3 xl:h-[100px] xl:flex-nowrap xl:py-0">
        <div><div className="label mb-1.5">View</div><ViewToggle /></div>
        <div><div className="label mb-1.5">Category</div><CategoryButtons /></div>
        <div className="flex w-full min-w-0 xl:w-auto xl:flex-1"><YearScrubber yearly={yearly} series={series} /></div>
      </div>
    </section>
  );
}
