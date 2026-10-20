import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { Place } from "@/lib/types";

const N_SHARDS = 128;

/** FNV-1a 32-bit, as in lib/places.ts (a client module, so the server can't import it). */
function shardOf(id: string): number {
  let h = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(id)) {
    h ^= byte;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h % N_SHARDS;
}

/** One address from its shard in public/data/places, or null if there's no such id. */
export async function getPlace(id: string): Promise<Place | null> {
  "use cache";
  if (!/^[0-9a-z]{1,32}$/.test(id)) return null;
  const file = join(process.cwd(), "public/data/places", `${String(shardOf(id)).padStart(3, "0")}.json`);
  const shard = JSON.parse(await readFile(file, "utf8")) as Record<string, Place>;
  return shard[id] ?? null;
}

const yrs = (n: number) => `${n.toFixed(1)} year${n === 1 ? "" : "s"}`;

export function describe(p: Place): string {
  const where = [p.address, p.ntaName, p.boro].filter(Boolean).join(", ");
  const life = p.medianLife == null ? "" : `; they lasted a median ${yrs(p.medianLife)}`;
  return `${p.tenants} food & drink business${p.tenants === 1 ? "" : "es"} at ${where} since 2012${life}. Lifespans, health grades and links for each.`;
}
