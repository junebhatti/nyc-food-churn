// Shapes of the JSON written by pipeline/export_site.py (web/public/data/).

export const CATEGORIES = ["restaurant", "bar", "cafe", "bakery", "bodega"] as const;
export type Category = (typeof CATEGORIES)[number];
export type CategoryFilter = "all" | Category;
export type View = "churn" | "lifespan" | "risk" | "rent";

export interface Summary {
  opened: number;
  openNow: number;
  medianLife: number;
  years: number[];
  categories: Category[];
  liveDate: string;
  buildings: number;
}

export interface Neighborhood {
  id: string;
  name: string;
  boro: string;
  places: number;
  rent: number | null; // storefront rent, $/sq ft/yr (LL157, 2019-24 mean)
  closure3y: number | null; // share of new places closed within 3 years
  medianLife: number | null; // years
  curve: number[] | null; // survival at 0..10 years
  geometry: GeoJSON.Geometry;
}

export interface Building {
  idx: number;
  id: string; // stable place id for /place/<id>
  lat: number;
  lon: number;
  tenants: number;
  medianLife: number | null;
  nta: number | null; // index into neighborhoods
  lit: number[]; // per category: 15-bit mask of years 2012..2026 with a business open
}

/** [address, nta code, [[name, categoryIndex, cuisineLabel, openYear, closeYear|null], ...]] */
export type TenantRow = [string, string | null, [string, number, string, number, number | null][]];

export interface YearSeries {
  open: (number | null)[]; // null: no data that year (bodegas after the SNAP data ends in 2025)
  close: (number | null)[];
  alive: number[]; // businesses open at any point that year
}

export type Yearly = { years: number[] } & Record<CategoryFilter, YearSeries>;

export interface CursedTenant {
  name: string;
  cuisine: string;
  price: string | null;
  open: number;
  close: number | null;
  life: number;
  isOpen: boolean;
}

export interface CursedAddress {
  rank: number;
  id: string;
  address: string;
  neighborhood: string;
  boro: string;
  lat: number;
  lon: number;
  tenants: number;
  medianLife: number | null;
  vacantPct: number;
  areaMedianLife: number | null;
  timeline: CursedTenant[];
}

// Analysis sections (pipeline/export_analysis.py)

export interface CurveRow {
  level: string;
  n: number;
  median: number | null; // years; null when more than half survive 10 years
  s1: number;
  s3: number;
  s5: number;
  curve: (number | null)[]; // survival on `grid`
}

export interface HalfLifeData {
  grid: number[];
  groups: Record<string, { label: string; rows: CurveRow[] }>;
}

export interface CursedTestData {
  curves: CurveRow[];
  byAge: { prior: string; age_band: string; hazard: number; hazard_ratio_vs_fresh: number; closures: number; business_years: number }[];
}

export interface BetaRow {
  group: string;
  level: string;
  label: string;
  avg_at_risk: number;
  baseline_exit_pct: number;
  spread_bp: number;
  covid_excess_pts: number;
  beta: number;
}

export interface BetaData {
  city: { year: number; city_exit_pct: number }[];
  rows: BetaRow[];
}

export interface CovidData {
  periods: string[];
  open: number[];
  close: number[];
}

export interface PitchNeighborhood {
  id: string;
  name: string;
  boro: string;
  valueZ: number;
  trafficZ: number;
  beta: number | null;
  rent: number | null;
  closure3y: number | null;
}

export interface PitchData {
  grid: number[];
  baseline: number[];
  coef: Record<string, number>;
  means: Record<string, number>;
  cuisines: { id: string; label: string }[];
  neighborhoods: PitchNeighborhood[];
  fit: { n: number; events: number; concordance: number; opened: string };
}

// Address pages (pipeline/export_places.py)

export interface PlaceBusiness {
  name: string;
  category: string;
  cuisine: string;
  open: number | null;
  close: number | null;
  isOpen: boolean;
  life: number;
  price: string | null;
  chain: boolean;
  liquor: boolean;
  source: "dohmh" | "sla" | "snap";
  inspections: { n: number; last: string; grade: string | null; gradeDate: string | null; scores: [string, number][] } | null;
  acclaim: { kind: string; label: string; url?: string | null }[];
}

export interface Place {
  id: string;
  address: string;
  zip: string | null;
  boro: string | null;
  lat: number;
  lon: number;
  nta: string | null;
  ntaName: string | null;
  tenants: number;
  medianLife: number | null;
  hood: { closure3y: number | null; rent: number | null; medianLife: number | null; beta: number | null };
  businesses: PlaceBusiness[]; // newest first
  nearby: [string, string, number, number][]; // [id, address, tenants, metres]
}

/** [id, address, neighbourhood, "name | name | ..."] */
export type SearchRow = [string, string, string, string];
