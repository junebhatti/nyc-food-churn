import type { CovidData } from "@/lib/types";
import Section, { Stat } from "./Section";

const W = 720;
const H = 300;
const P = { l: 44, r: 12, t: 16, b: 30 };

export default function Covid({ data }: { data: CovidData }) {
  const n = data.periods.length;
  const max = Math.max(...data.open, ...data.close);
  const mid = P.t + (H - P.t - P.b) / 2;
  const half = (H - P.t - P.b) / 2;
  const bw = (W - P.l - P.r) / n;
  const i2020 = data.periods.indexOf("2020H1");
  const lost = data.close.slice(i2020, i2020 + 2).reduce((a, b) => a + b, 0);
  const opened = data.open.slice(i2020, i2020 + 2).reduce((a, b) => a + b, 0);
  const iRecover = data.periods.findIndex((p, i) => i > i2020 + 1 && data.open[i] > data.close[i] * 1.4);

  return (
    <Section
      id="covid"
      kicker="06 — The 2020 shock"
      title={<>In 2020 the city lost {lost.toLocaleString()} places and opened {opened.toLocaleString()}.</>}
      intro={<>Openings above the line, closings below, every six months. The second half of 2020 was the worst stretch in the data: closings roughly doubled their normal pace while openings fell by about half. Openings recovered through 2021 and peaked in early 2022.</>}
    >
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_260px]">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Openings and closings every six months, 2017 to 2023">
          {data.periods.map((p, i) => {
            const x = P.l + i * bw;
            const oh = (data.open[i] / max) * half;
            const ch = (data.close[i] / max) * half;
            const shock = p.startsWith("2020");
            return (
              <g key={p}>
                {shock && <rect x={x} y={P.t} width={bw} height={H - P.t - P.b} fill="var(--rule-soft)" />}
                <rect x={x + 3} y={mid - oh} width={bw - 6} height={oh} fill="var(--deli)" />
                <rect x={x + 3} y={mid} width={bw - 6} height={ch} fill="var(--awning)" />
                {p.endsWith("H1") && <text x={x + bw} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--muted)" className="mono">{p.slice(0, 4)}</text>}
              </g>
            );
          })}
          <line x1={P.l} x2={W - P.r} y1={mid} y2={mid} stroke="var(--ink)" />
          {[max, 0, max].map((v, k) => (
            <text key={k} x={P.l - 6} y={k === 0 ? P.t + 8 : k === 1 ? mid + 3 : H - P.b} textAnchor="end" fontSize={9} fill="var(--muted)" className="mono">
              {k === 1 ? "0" : `${(v / 1000).toFixed(1)}k`}
            </text>
          ))}
          <text x={P.l + i2020 * bw + 4} y={P.t + 12} fontSize={10} fill="var(--awning)" className="mono">2020</text>
          <text x={W - P.r} y={P.t + 10} textAnchor="end" fontSize={10} fill="var(--deli)" className="mono">▲ OPENINGS</text>
          <text x={W - P.r} y={H - P.b - 4} textAnchor="end" fontSize={10} fill="var(--awning)" className="mono">▼ CLOSINGS</text>
        </svg>
        <div className="space-y-5 border-t border-ink pt-3">
          <Stat label="Closed, 2020" value={lost.toLocaleString()} tone="red" />
          <Stat label="Opened, 2020" value={opened.toLocaleString()} tone="green" />
          {iRecover > 0 && <Stat label="Openings clearly back" value={data.periods[iRecover].replace("H1", " H1").replace("H2", " H2")} />}
          <p className="label leading-relaxed">
            Health inspections paused from spring 2020 to mid-2021, so many 2020 closure dates are estimated from loans, grants and
            outdoor-dining records, and are good to about a season.
          </p>
        </div>
      </div>
    </Section>
  );
}
