import type { CursedTestData } from "@/lib/types";
import SurvivalChart, { Legend, type Series } from "../charts/SurvivalChart";
import Section, { Stat } from "./Section";

const COLORS: Record<string, string> = { fresh: "var(--deli)", "1-2 prior": "var(--bodega-text)", "3+ prior": "var(--awning)" };
const NAMES: Record<string, string> = { fresh: "Fresh storefront", "1-2 prior": "1–2 earlier tenants", "3+ prior": "3+ earlier tenants" };
const BANDS = ["0-1y", "1-2y", "2-3y", "3-5y", "5-10y"];
const BAND_LABEL: Record<string, string> = { "0-1y": "Year 1", "1-2y": "Year 2", "2-3y": "Year 3", "3-5y": "Years 4–5", "5-10y": "Years 6–10" };

// The 45% / 26% predecessor figures come from the 2026-10-20 split-address rerun (also in lib/ask/context.ts);
// update them if the pipeline is rerun.
export default function CursedTest({ data, grid }: { data: CursedTestData; grid: number[] }) {
  const series: Series[] = ["fresh", "1-2 prior", "3+ prior"].map((k) => {
    const r = data.curves.find((c) => c.level === k);
    return { label: NAMES[k], values: r?.curve ?? [], color: COLORS[k], strong: k === "3+ prior" };
  });
  const hr = (prior: string, band: string) => data.byAge.find((d) => d.prior === prior && d.age_band === band)?.hazard_ratio_vs_fresh ?? 1;
  const max = Math.max(...BANDS.flatMap((b) => [hr("1-2 prior", b), hr("3+ prior", b)]), 2);
  const firstYear = hr("3+ prior", "0-1y");

  return (
    <Section
      id="cursed-test"
      kicker="05 — The cursed spot test"
      title={<>A storefront&rsquo;s past barely predicts its next tenant.</>}
      intro={<>Places that open where three or more businesses already failed are <b>{firstYear.toFixed(1)}×</b> as likely to close in their first year as places in a fresh storefront: close to no difference. The &ldquo;cursed spot&rdquo; is mostly a story we tell after the fact. What does carry over is how the last tenant fared, not how many came before it: when the previous place lasted under a year, about 45% of new openings close within three years, against about 26% when it lasted eight years or more.</>}
    >
      <div className="grid gap-12 lg:grid-cols-2">
        <div>
          <div className="label mb-3">Share still open, by years since opening</div>
          <SurvivalChart grid={grid} series={series} height={320} label="Survival by storefront history" />
          <div className="mt-2"><Legend series={series} /></div>
        </div>
        <div>
          <div className="label mb-3">Closure risk vs a fresh storefront, by age</div>
          <div className="space-y-4">
            {BANDS.map((b) => (
              <div key={b} className="grid grid-cols-[92px_1fr] items-center gap-3">
                <span className="mono text-[11px] uppercase tracking-[0.06em] text-muted">{BAND_LABEL[b]}</span>
                <div className="space-y-1">
                  {(["1-2 prior", "3+ prior"] as const).map((p) => {
                    const v = hr(p, b);
                    return (
                      <div key={p} className="relative flex h-4 items-center">
                        <div className="absolute inset-y-[-3px] w-px bg-ink" style={{ left: `${(1 / max) * 100}%` }} />
                        <div className="relative h-full" style={{ width: `${(v / max) * 100}%`, background: COLORS[p] }} />
                        {/* Paper behind the label so the 1× line never cuts through it. */}
                        <span className="mono tnum relative ml-1 bg-paper px-1 text-[11px]">{v.toFixed(1)}×</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <p className="label mt-3">The ink line marks 1× (same risk as a fresh storefront). Single-storefront buildings, places opened since 2015.</p>
          <div className="mt-8 flex gap-10 border-t border-ink pt-3">
            <Stat label="Year-1 risk, 3+ earlier tenants" value={`${firstYear.toFixed(1)}×`} />
            <Stat label="Years 4–5" value={`${hr("3+ prior", "3-5y").toFixed(1)}×`} />
          </div>
        </div>
      </div>
    </Section>
  );
}
