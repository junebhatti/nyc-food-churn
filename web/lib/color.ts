// Map ramp and quadrant colours from the design handoff.

export type RGB = [number, number, number];

const hex = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;

export const RAMP_LOW = hex("#4F7D5E");
export const RAMP_MID = hex("#F4EEE2");
export const RAMP_HIGH = hex("#C0402A");
export const LEGEND_CHIPS = ["#4F7D5E", "#A9B8A0", "#F4EEE2", "#DC9A82", "#C0402A"];
export const DEAD: RGB = hex("#DAD2C3");
export const LAND: RGB = hex("#E7E0D2");
export const INK: RGB = hex("#1C1B18");

const mix = (a: RGB, b: RGB, t: number): RGB => a.map((v, i) => Math.round(v + (b[i] - v) * t)) as RGB;

/** t in [0,1]: green -> paper -> red, linear in RGB through the middle stop. */
export function ramp(t: number): RGB {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? mix(RAMP_LOW, RAMP_MID, x / 0.5) : mix(RAMP_MID, RAMP_HIGH, (x - 0.5) / 0.5);
}

export type Quadrant = "cs" | "es" | "cd" | "ed";
export const QUADRANT_COLOR: Record<Quadrant, string> = {
  cs: "#1E5B3A",
  es: "#1C1B18",
  cd: "#E2B13C",
  ed: "#B8321D",
};
export const QUADRANT_TEXT: Record<Quadrant, string> = {
  cs: "#1E5B3A",
  es: "#1C1B18",
  cd: "#8F6A12",
  ed: "#B8321D",
};
export const QUADRANT_NAME: Record<Quadrant, string> = {
  cs: "Cheap & safe",
  es: "Expensive & safe",
  cd: "Cheap & deadly",
  ed: "Expensive & deadly",
};

/** Unhovered relief blocks: quadrant colour mixed toward paper (30% for expensive & safe). */
export function quadrantBlock(q: Quadrant, active: boolean): RGB {
  const c = hex(QUADRANT_COLOR[q]);
  if (active) return c;
  return mix(c, RAMP_MID, q === "es" ? 0.7 : 0.5);
}

/** Robust domain for a metric: 5th-95th percentile. */
export function quantileDomain(values: number[]): [number, number] {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return [0, 1];
  const q = (p: number) => v[Math.min(v.length - 1, Math.floor(p * (v.length - 1)))];
  return [q(0.05), q(0.95)];
}
