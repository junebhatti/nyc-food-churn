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
  open: number[];
  close: number[];
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
  address: string;
  neighborhood: string;
  boro: string;
  tenants: number;
  medianLife: number | null;
  vacantPct: number;
  areaMedianLife: number | null;
  timeline: CursedTenant[];
}
