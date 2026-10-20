"use client";

import { useState } from "react";
import type { CovidData } from "@/lib/types";
import { useWidth } from "@/lib/useWidth";
import Section, { Stat } from "./Section";

const PRICE_H = 230; // candle pane
const GAP = 26; // year labels between the panes
const VOL_H = 90; // volume pane
const H = PRICE_H + GAP + VOL_H + 8;
const P = { l: 48, r: 12, t: 14 };
const k = (v: number) => `${(v / 1000).toFixed(1)}k`;

/** Places open in the city as half-yearly candlesticks, with openings and closings as the volume. */
export default function Covid({ data }: { data: CovidData }) {
  const [box, W] = useWidth(720);
  const [pick, setPick] = useState<number | null>(null);
  const n = data.periods.length;
  const bw = (W - P.l - P.r) / n;
  const lo = Math.min(...data.candles.map((c) => c.l));
  const hi = Math.max(...data.candles.map((c) => c.h));
  const pad = (hi - lo) * 0.08;
  const y = (v: number) => P.t + (1 - (v - (lo - pad)) / (hi - lo + 2 * pad)) * (PRICE_H - P.t);
  const volTop = PRICE_H + GAP;
  const volMax = Math.max(...data.open, ...data.close);
  const vh = (v: number) => (v / volMax) * VOL_H;
  const ticks = [lo, (lo + hi) / 2, hi].map((v) => Math.round(v / 100) * 100);

  const i2020 = data.periods.indexOf("2020H1");
  const lost = data.close.slice(i2020, i2020 + 2).reduce((a, b) => a + b, 0);
  const opened = data.open.slice(i2020, i2020 + 2).reduce((a, b) => a + b, 0);
  const before = data.candles[i2020].o;
  const bottom = Math.min(...data.candles.slice(i2020).map((c) => c.l));
  const iBack = data.candles.findIndex((c, i) => i > i2020 && c.c >= before);

  return (
    <Section
      id="covid"
      kicker="06 — The 2020 shock"
      title={<>In 2020 the city lost {lost.toLocaleString()} places and opened {opened.toLocaleString()}.</>}
      intro={<>Read it like a stock chart of how many places were open. Each candle is six months: the body runs from the count at the start to the count at the end, <span className="text-deli">green</span> if the city gained places and <span className="text-awning">red</span> if it lost them, and the thin wick shows the high and low in between. The bars underneath are the volume: places that opened and closed. 2020 is two long red candles on heavy closing volume.</>}
    >
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div ref={box} className="min-w-0">
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block max-w-full" role="img" aria-label="Places open in NYC as half-yearly candlesticks, 2017 to 2023, with openings and closings as volume">
          {/* 2020 shading across both panes */}
          <rect x={P.l + i2020 * bw} y={P.t} width={bw * 2} height={H - P.t} fill="var(--rule-soft)" />
          <text x={P.l + i2020 * bw + 4} y={P.t + 12} fontSize={10} fill="var(--awning)" className="mono">2020</text>

          {ticks.map((v) => (
            <g key={v}>
              <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} stroke="var(--rule-soft)" strokeDasharray="2 3" />
              <text x={P.l - 6} y={y(v) + 3} textAnchor="end" fontSize={9} fill="var(--muted)" className="mono">{k(v)}</text>
            </g>
          ))}
          <text x={P.l} y={P.t - 2} fontSize={9} fill="var(--muted)" className="mono">PLACES OPEN</text>

          {data.candles.map((c, i) => {
            const cx = P.l + i * bw + bw / 2;
            const up = c.c >= c.o;
            const color = up ? "var(--deli)" : "var(--awning)";
            const top = y(Math.max(c.o, c.c));
            const body = Math.max(Math.abs(y(c.o) - y(c.c)), 1.5);
            return (
              <g key={data.periods[i]}>
                <title>{`${data.periods[i].replace("H", " H")}: ${c.o.toLocaleString()} → ${c.c.toLocaleString()} open (high ${c.h.toLocaleString()}, low ${c.l.toLocaleString()}); ${data.open[i].toLocaleString()} opened, ${data.close[i].toLocaleString()} closed`}</title>
                <line x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth={1.5} />
                <rect x={cx - bw * 0.28} y={top} width={bw * 0.56} height={body} fill={color} />
              </g>
            );
          })}

          {/* Full-height hit areas: tap or hover a half-year for its numbers. */}
          {data.periods.map((p, i) => (
            <rect key={`hit${p}`} x={P.l + i * bw} y={P.t} width={bw} height={H - P.t} fill={pick === i ? "var(--ink)" : "transparent"}
              fillOpacity={pick === i ? 0.06 : 0} className="cursor-pointer" onMouseEnter={() => setPick(i)} onClick={() => setPick(i)} />
          ))}

          {/* year labels between the panes */}
          {data.periods.map((p, i) =>
            p.endsWith("H1") ? (
              <text key={p} x={P.l + (i + 1) * bw} y={PRICE_H + 17} textAnchor="middle" fontSize={10} fill="var(--muted)" className="mono">{p.slice(0, 4)}</text>
            ) : null,
          )}

          {/* volume: openings and closings side by side */}
          <line x1={P.l} x2={W - P.r} y1={volTop + VOL_H} y2={volTop + VOL_H} stroke="var(--ink)" />
          <text x={P.l - 6} y={volTop + 8} textAnchor="end" fontSize={9} fill="var(--muted)" className="mono">{k(volMax)}</text>
          {data.periods.map((p, i) => {
            const x0 = P.l + i * bw + bw * 0.2;
            const w = bw * 0.28;
            return (
              <g key={`v${p}`}>
                <rect x={x0} y={volTop + VOL_H - vh(data.open[i])} width={w} height={vh(data.open[i])} fill="var(--deli)" />
                <rect x={x0 + w + 2} y={volTop + VOL_H - vh(data.close[i])} width={w} height={vh(data.close[i])} fill="var(--awning)" />
              </g>
            );
          })}
          <text x={W - P.r} y={volTop + 8} textAnchor="end" fontSize={10} className="mono">
            <tspan fill="var(--muted)">VOLUME · </tspan><tspan fill="var(--deli)">▮ OPENED </tspan><tspan fill="var(--awning)">▮ CLOSED</tspan>
          </text>
        </svg>
        <p className="mono tnum mt-2 min-h-5 text-[12px]">
          {pick == null ? <span className="text-muted">Tap or hover a candle for its numbers.</span> : (
            <>
              <span className="text-muted">{data.periods[pick].replace("H", " H")}: </span>
              {data.candles[pick].o.toLocaleString()} → {data.candles[pick].c.toLocaleString()} open
              <span className="text-muted"> (low {data.candles[pick].l.toLocaleString()}, high {data.candles[pick].h.toLocaleString()}) · </span>
              <span className="text-deli">{data.open[pick].toLocaleString()} opened</span> · <span className="text-awning">{data.close[pick].toLocaleString()} closed</span>
            </>
          )}
        </p>
        </div>
        <div className="space-y-5 border-t border-ink pt-3">
          <Stat label="Closed, 2020" value={lost.toLocaleString()} tone="red" />
          <Stat label="Opened, 2020" value={opened.toLocaleString()} tone="green" />
          <Stat label="Open before → lowest" value={`${k(before)} → ${k(bottom)}`} />
          {iBack > 0 && <Stat label="Back above pre-COVID" value={data.periods[iBack].replace("H1", " H1").replace("H2", " H2")} />}
          <p className="label leading-relaxed">
            Health inspections paused from spring 2020 to mid-2021, so many 2020 closure dates are estimated from loans, grants and
            outdoor-dining records, and are good to about a season.
          </p>
        </div>
      </div>
    </Section>
  );
}
