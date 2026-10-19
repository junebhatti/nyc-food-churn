// Map ramp and quadrant colours from the design handoff, in light and dark.

export type RGB = [number, number, number];

const hex = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;

const mix = (a: RGB, b: RGB, t: number): RGB => a.map((v, i) => Math.round(v + (b[i] - v) * t)) as RGB;

/** Colours the deck.gl maps need as RGB; CSS gets the same values as tokens in globals.css. */
export interface Palette {
  rampLow: RGB;
  rampMid: RGB;
  rampHigh: RGB;
  dead: RGB;
  land: RGB;
  park: RGB;
  street: RGB;
  streetMajor: RGB;
  ink: RGB;
  muted: RGB;
  paper: RGB;
  filteredOut: RGB;
  /** Unhovered relief blocks mix toward this. */
  blockBase: RGB;
  quadrant: Record<Quadrant, RGB>;
}

export const LIGHT: Palette = {
  rampLow: hex("#4F7D5E"),
  rampMid: hex("#F4EEE2"),
  rampHigh: hex("#C0402A"),
  dead: hex("#DAD2C3"),
  land: hex("#E7E0D2"),
  park: hex("#BECEA8"),
  street: hex("#BDB19C"),
  streetMajor: hex("#A0937B"),
  ink: hex("#1C1B18"),
  muted: hex("#5A554C"),
  paper: hex("#F3EEE4"),
  filteredOut: hex("#E2DACB"),
  blockBase: hex("#F4EEE2"),
  quadrant: { cs: hex("#1E5B3A"), es: hex("#1C1B18"), cd: hex("#E2B13C"), ed: hex("#B8321D") },
};

/** Dark variant from the handoff's 1c reference: navy ground, hues lifted for contrast. */
export const DARK: Palette = {
  rampLow: hex("#4FA273"),
  rampMid: hex("#5C6077"),
  rampHigh: hex("#E8644C"),
  dead: hex("#2E3146"),
  land: hex("#23263A"),
  park: hex("#25392F"),
  street: hex("#484D68"),
  streetMajor: hex("#666C8C"),
  ink: hex("#E9E9ED"),
  muted: hex("#9A9CAB"),
  paper: hex("#161826"),
  filteredOut: hex("#2A2D40"),
  blockBase: hex("#2E3146"),
  quadrant: { cs: hex("#5DB585"), es: hex("#E9E9ED"), cd: hex("#E8C46A"), ed: hex("#E8644C") },
};

/** t in [0,1]: green -> middle -> red, linear in RGB through the middle stop. */
export function ramp(t: number, p: Palette): RGB {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? mix(p.rampLow, p.rampMid, x / 0.5) : mix(p.rampMid, p.rampHigh, (x - 0.5) / 0.5);
}

/** The five legend chips, as CSS tokens so they follow the theme. */
export const LEGEND_CHIPS = [0, 1, 2, 3, 4].map((i) => `var(--ramp-${i})`);

export type Quadrant = "cs" | "es" | "cd" | "ed";
export const QUADRANT_COLOR: Record<Quadrant, string> = {
  cs: "var(--deli)",
  es: "var(--ink)",
  cd: "var(--bodega)",
  ed: "var(--awning)",
};
export const QUADRANT_TEXT: Record<Quadrant, string> = {
  cs: "var(--deli)",
  es: "var(--ink)",
  cd: "var(--bodega-text)",
  ed: "var(--awning)",
};
export const QUADRANT_NAME: Record<Quadrant, string> = {
  cs: "Cheap & safe",
  es: "Expensive & safe",
  cd: "Cheap & deadly",
  ed: "Expensive & deadly",
};

/** Unhovered relief blocks: quadrant colour mixed toward the base (70% for expensive & safe). */
export function quadrantBlock(q: Quadrant, active: boolean, p: Palette): RGB {
  const c = p.quadrant[q];
  if (active) return c;
  return mix(c, p.blockBase, q === "es" ? 0.7 : 0.5);
}

/** Robust domain for a metric: 5th-95th percentile. */
export function quantileDomain(values: number[]): [number, number] {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (!v.length) return [0, 1];
  const q = (p: number) => v[Math.min(v.length - 1, Math.floor(p * (v.length - 1)))];
  return [q(0.05), q(0.95)];
}
