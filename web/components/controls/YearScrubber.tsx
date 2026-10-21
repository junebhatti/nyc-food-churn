"use client";

import { Pause, Play } from "@phosphor-icons/react";
import { FIRST_YEAR, LAST_YEAR, useAtlas } from "@/lib/store";
import type { Yearly, YearSeries } from "@/lib/types";

interface Props {
  yearly: Yearly;
  compact?: boolean; // mobile: 18px bars, smaller year
  openNow?: number;
  series?: YearSeries; // e.g. one neighbourhood's counts; defaults to the city for the category
}

/** Play button, the year, an openings/closings butterfly chart and the range input. */
export default function YearScrubber({ yearly, compact = false, openNow, series: override }: Props) {
  const { year, playing, category, setYear, togglePlay } = useAtlas();
  const series = override ?? yearly[category];
  const max = Math.max(...series.open.map((v) => v ?? 0), ...series.close.map((v) => v ?? 0), 1);
  const barH = compact ? 18 : 22;

  return (
    <div className="flex min-w-0 flex-1 items-center gap-4">
      <button
        type="button"
        onClick={togglePlay}
        aria-label={playing ? "Pause" : "Play through the years"}
        className={`flex h-10 w-10 shrink-0 items-center justify-center border border-ink ${compact ? "h-11 w-11 bg-ink text-paper" : "hover:bg-paper-raised"}`}
      >
        {playing ? <Pause size={18} weight="fill" /> : <Play size={18} weight="fill" />}
      </button>
      <div className="shrink-0">
        <div className={`mono tnum leading-none ${compact ? "text-[28px]" : "text-[30px]"}`}>{year}</div>
        {openNow != null && <div className="label mt-1 tnum">{openNow.toLocaleString()} open</div>}
      </div>
      <div className="min-w-0 flex-1">
        {/* Each year's column is a shortcut to that year (the slider below is the keyboard control); green above the line is
            openings, red below is closings, and each column's tooltip gives the counts. */}
        <div className="flex items-stretch gap-[3px]" aria-hidden>
          {series.open.map((o, i) => {
            const y = FIRST_YEAR + i;
            const dim = y > year ? "opacity-25" : "";
            if (o == null || series.close[i] == null) {
              // unknown year: a hollow stub on each side of the axis instead of a zero
              return (
                <div key={y} className={`flex flex-1 cursor-pointer flex-col ${dim}`} title={`No data for ${y}`} onClick={() => setYear(y)}>
                  <div className="flex items-end" style={{ height: barH }}><div className="h-1 w-full border border-b-0 border-dashed border-muted" /></div>
                  <div className="h-px bg-ink" />
                  <div style={{ height: barH }}><div className="h-1 w-full border border-t-0 border-dashed border-muted" /></div>
                </div>
              );
            }
            return (
              <div key={y} className={`flex flex-1 cursor-pointer flex-col hover:opacity-100 ${dim} ${y === year ? "outline outline-1 outline-offset-1 outline-ink" : ""}`}
                title={`${y}: ${o.toLocaleString()} opened · ${(series.close[i] ?? 0).toLocaleString()} closed`} onClick={() => setYear(y)}>
                <div className="flex items-end" style={{ height: barH }}>
                  <div className="w-full bg-deli" style={{ height: (o / max) * barH }} />
                </div>
                <div className="h-px bg-ink" />
                <div style={{ height: barH }}>
                  <div className="w-full bg-awning" style={{ height: ((series.close[i] ?? 0) / max) * barH }} />
                </div>
              </div>
            );
          })}
        </div>
        <input
          type="range"
          min={FIRST_YEAR}
          max={LAST_YEAR}
          step={1}
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          aria-label="Year"
          className={`mt-1 w-full ${compact ? "h-7" : ""}`}
        />
        {!compact && (
          <div className="label relative h-4">
            <span className="absolute left-0">{FIRST_YEAR}</span>
            {/* Centred under the 2020 column. */}
            <span className="absolute -translate-x-1/2" style={{ left: `${((2020 - FIRST_YEAR + 0.5) / (LAST_YEAR - FIRST_YEAR + 1)) * 100}%` }}>2020 shock</span>
            <span className="absolute right-0">{LAST_YEAR}</span>
          </div>
        )}
      </div>
    </div>
  );
}
