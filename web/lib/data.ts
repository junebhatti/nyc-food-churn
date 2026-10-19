"use client";

import { useEffect, useState } from "react";
import { FIRST_YEAR } from "./store";
import { CATEGORIES, type Building, type CategoryFilter, type Neighborhood, type TenantRow } from "./types";

// One download per file per page, shared by every component that asks for it.
const inflight = new Map<string, Promise<unknown>>();

function getJson<T>(name: string): Promise<T> {
  if (!inflight.has(name)) {
    const p = fetch(`/data/${name}`).then((res) => {
      if (!res.ok) throw new Error(`Failed to load /data/${name}: HTTP ${res.status}`);
      return res.json();
    });
    p.catch(() => inflight.delete(name)); // allow a retry after a failure
    inflight.set(name, p);
  }
  return inflight.get(name) as Promise<T>;
}

interface BuildingsFile {
  columns: string[];
  rows: (string | number | null)[][];
}

function parseBuildings(f: BuildingsFile): Building[] {
  const col = (name: string) => f.columns.indexOf(name);
  const [id, lat, lon, tenants, life, nta] = ["id", "lat", "lon", "tenants", "medianLife", "nta"].map(col);
  const lit = CATEGORIES.map((c) => col(`lit_${c}`));
  return f.rows.map((r, idx) => ({
    idx,
    id: r[id] as string,
    lat: r[lat] as number,
    lon: r[lon] as number,
    tenants: r[tenants] as number,
    medianLife: r[life] as number | null,
    nta: r[nta] as number | null,
    lit: lit.map((i) => (r[i] as number) ?? 0),
  }));
}

/** Loads a JSON file once per page; surfaces failures instead of rendering an empty map. */
function useJson<T>(name: string, parse?: (raw: unknown) => T, enabled = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    getJson<unknown>(name)
      .then((raw) => alive && setData(parse ? parse(raw) : (raw as T)))
      .catch((e: Error) => {
        console.error(e);
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [name, enabled]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error };
}

export const useBuildings = () => useJson<Building[]>("buildings.json", (r) => parseBuildings(r as BuildingsFile));
export const useNeighborhoods = () => useJson<Neighborhood[]>("neighborhoods.json");
export const useLand = () => useJson<GeoJSON.FeatureCollection>("land.json");
export const useParks = () => useJson<GeoJSON.FeatureCollection>("parks.json");
export const useYearlyByNta = (enabled: boolean) =>
  useJson<Record<string, Record<CategoryFilter, { open: number[]; close: number[]; alive: number[] }>>>("yearly_nta.json", undefined, enabled);
export const useTenants = (enabled: boolean) => useJson<TenantRow[]>("tenants.json", undefined, enabled);

/** Was any business of the selected category open in this building during `year`? */
export function isLit(b: Building, year: number, category: CategoryFilter): boolean {
  const bit = 1 << (year - FIRST_YEAR);
  if (category === "all") return b.lit.some((m) => (m & bit) !== 0);
  return (b.lit[CATEGORIES.indexOf(category)] & bit) !== 0;
}

/** Has the building ever housed the selected category? */
export function hasCategory(b: Building, category: CategoryFilter): boolean {
  return category === "all" || b.lit[CATEGORIES.indexOf(category)] !== 0;
}
