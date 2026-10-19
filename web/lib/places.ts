"use client";

import type { Place } from "./types";

export const N_SHARDS = 128;

/** FNV-1a 32-bit, identical to pipeline/export_site.py shard_of(). */
export function shardOf(id: string, n = N_SHARDS): number {
  let h = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(id)) {
    h ^= byte;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h % n;
}

const cache = new Map<number, Promise<Record<string, Place>>>();

export async function fetchPlace(id: string): Promise<Place | null> {
  const shard = shardOf(id);
  if (!cache.has(shard)) {
    cache.set(
      shard,
      fetch(`/data/places/${String(shard).padStart(3, "0")}.json`).then((r) => {
        if (!r.ok) throw new Error(`Failed to load address data (shard ${shard}): HTTP ${r.status}`);
        return r.json();
      }),
    );
  }
  const data = await cache.get(shard)!;
  return data[id] ?? null;
}

export const placeHref = (id: string) => `/place/${id}`;

/** Outbound links: we link to reviews rather than republishing them. */
export function outboundLinks(name: string, address: string, boro: string | null) {
  const q = encodeURIComponent(`${name} ${address} ${boro ?? ""} New York`);
  return {
    google: `https://www.google.com/maps/search/?api=1&query=${q}`,
    yelp: `https://www.yelp.com/search?find_desc=${encodeURIComponent(name)}&find_loc=${encodeURIComponent(`${address}, ${boro ?? ""}, NY`)}`,
    web: `https://www.google.com/search?q=${q}`,
  };
}
