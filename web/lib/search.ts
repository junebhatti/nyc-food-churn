"use client";

import type { SearchRow } from "./types";

// Common nicknames for neighbourhood search.
export const NICKNAMES: Record<string, string> = {
  les: "Lower East Side", ues: "Upper East Side", uws: "Upper West Side", fidi: "Financial District",
  "fi di": "Financial District", soho: "SoHo", noho: "SoHo", tribeca: "Tribeca", dumbo: "Downtown Brooklyn",
  "east vill": "East Village", "west vill": "West Village", bk: "Brooklyn", lic: "Long Island City",
  "bed stuy": "Bedford-Stuyvesant", "bed-stuy": "Bedford-Stuyvesant", hk: "Hell's Kitchen", "hells kitchen": "Hell's Kitchen",
};

let index: Promise<SearchRow[]> | null = null;

/** The search index (about 1.4 MB gzipped) loads the first time the box is focused. */
export function loadIndex(): Promise<SearchRow[]> {
  if (!index) {
    index = fetch("/data/search.json").then((r) => {
      if (!r.ok) throw new Error(`Search index failed to load: HTTP ${r.status}`);
      return r.json();
    });
    index.catch(() => (index = null)); // allow a retry after a failure
  }
  return index;
}

/** Normalise addresses so "6917 5th ave" matches "6917 5Th Ave" and "41-94 bowne" matches "4194 Bowne". */
export const norm = (s: string) =>
  s.toLowerCase().replace(/(\d)(st|nd|rd|th)\b/g, "$1").replace(/\bavenue\b/g, "ave").replace(/\bstreet\b/g, "st")
    .replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();

export interface Hit {
  id: string;
  address: string;
  hood: string;
  names: string;
  score: number;
}

export function searchIndex(rows: SearchRow[], q: string, limit = 8): Hit[] {
  const nq = norm(q);
  if (nq.length < 2) return [];
  const compact = nq.replace(/ /g, "");
  const hits: Hit[] = [];
  for (const [id, address, hood, names] of rows) {
    const na = norm(address);
    let score = 0;
    if (na.startsWith(nq) || na.replace(/ /g, "").startsWith(compact)) score = 3;
    else if (na.includes(nq)) score = 2;
    else if (norm(names).includes(nq)) score = 1;
    if (score) hits.push({ id, address, hood, names, score });
    if (hits.length > 400) break;
  }
  return hits.sort((a, b) => b.score - a.score || a.address.length - b.address.length).slice(0, limit);
}
