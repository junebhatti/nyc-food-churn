"use client";

import { loadIndex } from "@/lib/search";

// NYC Planning's free geocoder, for addresses that never had a food business in our data.
const GEOSEARCH = "https://geosearch.planninglabs.nyc/v2/search";

export interface Nearest {
  id: string;
  address: string;
  metres: number;
}

interface BuildingsFile {
  columns: string[];
  rows: (string | number | null)[][];
}

let buildings: Promise<BuildingsFile> | null = null;

export async function lookupAddress(q: string): Promise<{ label: string; nearest: Nearest[] }> {
  const res = await fetch(`${GEOSEARCH}?text=${encodeURIComponent(q)}&size=1`);
  if (!res.ok) throw new Error(`Address lookup failed: HTTP ${res.status}`);
  const json = await res.json();
  const f = json.features?.[0];
  // Don't guess: a loose match (another street with a similar name, a made-up number) is worse than no answer.
  const confidence = f?.properties?.confidence ?? 0;
  if (!f || confidence < 0.8 || f.properties?.match_type === "fallback") {
    throw new Error("NYC's address lookup couldn't find that exact address. Try adding the borough.");
  }
  const [lon, lat] = f.geometry.coordinates as [number, number];

  buildings ??= fetch("/data/buildings.json").then((r) => {
    if (!r.ok) throw new Error(`Building data failed to load: HTTP ${r.status}`);
    return r.json();
  });
  const [b, index] = await Promise.all([buildings, loadIndex()]);
  const c = (name: string) => b.columns.indexOf(name);
  const [iId, iLat, iLon] = [c("id"), c("lat"), c("lon")];
  const address = new Map(index.map(([id, addr]) => [id, addr]));
  const k = Math.cos((lat * Math.PI) / 180);
  const nearest = b.rows
    .map((r) => ({ id: r[iId] as string, d: 111_320 * Math.hypot((r[iLat] as number) - lat, ((r[iLon] as number) - lon) * k) }))
    .sort((x, y) => x.d - y.d)
    .slice(0, 8)
    .map((x) => ({ id: x.id, address: address.get(x.id) ?? x.id, metres: Math.round(x.d) }))
    .filter((x, i, all) => all.findIndex((y) => y.address === x.address) === i) // one row per address
    .slice(0, 3);
  return { label: f.properties?.label ?? q, nearest };
}
