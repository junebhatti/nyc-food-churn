import type { Quadrant } from "./color";
import type { Neighborhood } from "./types";

export const MIN_PLACES = 80; // neighbourhoods with fewer places are too noisy to plot

export interface RiskHood extends Neighborhood {
  rent: number;
  closure3y: number;
  quadrant: Quadrant;
  riskAdj: number; // rent / (1 - closure3y): rent per surviving dollar
  riskAdjRank: number; // 1 = best value
}

const median = (v: number[]) => {
  const s = [...v].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

/** Neighbourhoods with rent and closure odds, split into quadrants at the city medians. */
export function riskHoods(hoods: Neighborhood[]) {
  const ok = hoods.filter((h) => h.rent != null && h.closure3y != null && h.places >= MIN_PLACES) as (Neighborhood & {
    rent: number;
    closure3y: number;
  })[];
  const rentMed = median(ok.map((h) => h.rent));
  const closeMed = median(ok.map((h) => h.closure3y));
  const rows: RiskHood[] = ok.map((h) => {
    const expensive = h.rent > rentMed;
    const deadly = h.closure3y > closeMed;
    const quadrant: Quadrant = expensive ? (deadly ? "ed" : "es") : deadly ? "cd" : "cs";
    return { ...h, quadrant, riskAdj: h.rent / (1 - h.closure3y), riskAdjRank: 0 };
  });
  [...rows].sort((a, b) => a.riskAdj - b.riskAdj).forEach((h, i) => (h.riskAdjRank = i + 1));
  return { rows, rentMed, closeMed };
}

/** Up to 3 neighbourhoods that are both cheaper and safer, best value first. */
export function dominating(h: RiskHood, rows: RiskHood[]): RiskHood[] {
  return rows
    .filter((o) => o.id !== h.id && o.rent < h.rent && o.closure3y < h.closure3y)
    .sort((a, b) => a.riskAdj - b.riskAdj)
    .slice(0, 3);
}
