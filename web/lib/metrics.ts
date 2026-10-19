// Per-building values for each map view, hex binning, and the colour/height of every column.

import { quantileDomain, ramp, type Palette, type RGB } from "./color";
import { hasCategory, isLit } from "./data";
import type { Building, CategoryFilter, Neighborhood, View } from "./types";

export const LEGEND: Record<View, { title: string; lo: string; hi: string }> = {
  churn: { title: "Tenant turnover", lo: "Few tenants", hi: "Many" },
  lifespan: { title: "Median lifespan", lo: "Long-lived", hi: "Short" },
  risk: { title: "3-yr closure odds", lo: "Safe", hi: "Deadly" },
  rent: { title: "Rent per sq ft", lo: "Cheap", hi: "Expensive" },
};

/** Raw value per building for a view; higher always means "redder" (worse / more expensive). */
export function rawValue(b: Building, view: View, hoods: Neighborhood[]): number | null {
  const n = b.nta != null ? hoods[b.nta] : undefined;
  switch (view) {
    case "churn":
      return b.tenants;
    case "lifespan": {
      const life = b.medianLife ?? n?.medianLife ?? null;
      return life == null ? null : -life; // short life = red
    }
    case "risk":
      return n?.closure3y ?? null;
    case "rent":
      return n?.rent != null && n.rent > 0 ? Math.log(n.rent) : null;
  }
}

export type Scale = (v: number | null) => number | null;

export function makeScale(buildings: Building[], view: View, hoods: Neighborhood[]): Scale {
  const vals = buildings.map((b) => rawValue(b, view, hoods)).filter((v): v is number => v != null);
  const [lo, hi] = quantileDomain(vals);
  return (v) => (v == null ? null : hi > lo ? (v - lo) / (hi - lo) : 0.5);
}

export interface Cell {
  id: string;
  lon: number;
  lat: number;
  height: number;
  color: RGB;
  top: number; // building with the most tenants, for the hover card
}

const LAT0 = 40.7;
const M_PER_DEG_LAT = 111_320;
const M_PER_DEG_LON = 111_320 * Math.cos((LAT0 * Math.PI) / 180);

/** Pointy-top axial hex binning in metres around NYC. */
export function hexBins(
  buildings: Building[],
  radiusM: number,
  value: (b: Building) => number | null,
  year: number,
  category: CategoryFilter,
  palette: Palette,
  onLand?: (id: string, lon: number, lat: number) => boolean,
  inFocus: (b: Building) => boolean = () => true,
): Cell[] {
  const size = radiusM;
  const cells = new Map<string, { q: number; r: number; h: number; sum: number; n: number; lit: boolean; top: number; topN: number; lon: number; lat: number; k: number }>();
  for (const b of buildings) {
    if (!hasCategory(b, category)) continue;
    const x = (b.lon + 74) * M_PER_DEG_LON;
    const y = (b.lat - LAT0) * M_PER_DEG_LAT;
    const qf = ((Math.sqrt(3) / 3) * x - (1 / 3) * y) / size;
    const rf = ((2 / 3) * y) / size;
    let q = Math.round(qf);
    let r = Math.round(rf);
    const s = Math.round(-qf - rf);
    const dq = Math.abs(q - qf), dr = Math.abs(r - rf), ds = Math.abs(s - (-qf - rf));
    if (dq > dr && dq > ds) q = -r - s;
    else if (dr > ds) r = -q - s;
    const key = `${q},${r}`;
    let c = cells.get(key);
    if (!c) cells.set(key, (c = { q, r, h: 0, sum: 0, n: 0, lit: false, top: b.idx, topN: -1, lon: 0, lat: 0, k: 0 }));
    const focus = inFocus(b);
    c.h += focus ? b.tenants : b.tenants * 0.15; // outside the chosen neighbourhood: low and dark
    c.lon += b.lon;
    c.lat += b.lat;
    c.k += 1;
    if (focus && isLit(b, year, category)) {
      c.lit = true;
      const v = value(b);
      if (v != null) {
        c.sum += v;
        c.n += 1;
      }
    }
    if (b.tenants > c.topN) {
      c.topN = b.tenants;
      c.top = b.idx;
    }
  }
  return [...cells.entries()].map(([id, c]) => {
    const x = size * Math.sqrt(3) * (c.q + c.r / 2);
    const y = size * 1.5 * c.r;
    const t = c.n ? c.sum / c.n : null;
    let lon = x / M_PER_DEG_LON - 74;
    let lat = y / M_PER_DEG_LAT + LAT0;
    // A grid cell centred in the river would paint over the water; sit it on its buildings instead.
    if (onLand && !onLand(id, lon, lat)) {
      lon = c.lon / c.k;
      lat = c.lat / c.k;
    }
    return {
      id,
      lon,
      lat,
      height: c.h,
      color: c.lit && t != null ? ramp(t, palette) : palette.dead,
      top: c.top,
    };
  });
}

export function buildingColor(b: Building, t: number | null, year: number, category: CategoryFilter, palette: Palette, focus = true): RGB {
  if (!focus || !hasCategory(b, category) || !isLit(b, year, category) || t == null) return palette.dead;
  return ramp(t, palette);
}
