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
  const max = Math.max(...series.open, ...series.close, 1);
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
        <div className="flex items-stretch gap-[3px]" aria-hidden>
          {series.open.map((o, i) => {
            const y = FIRST_YEAR + i;
            const dim = y > year ? "opacity-25" : "";
            return (
              <div key={y} className={`flex flex-1 flex-col ${dim}`}>
                <div className="flex items-end" style={{ height: barH }}>
                  <div className="w-full bg-deli" style={{ height: (o / max) * barH }} />
                </div>
                <div className="h-px bg-ink" />
                <div style={{ height: barH }}>
                  <div className="w-full bg-awning" style={{ height: (series.close[i] / max) * barH }} />
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
          <div className="label flex justify-between">
            <span>{FIRST_YEAR}</span>
            <span>▲ openings · ▼ closings</span>
            <span>2020 shock</span>
            <span>{LAST_YEAR}</span>
          </div>
        )}
      </div>
    </div>
  );
}
