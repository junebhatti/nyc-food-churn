"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { useNeighborhoods } from "@/lib/data";
import { placeHref } from "@/lib/places";
import { loadIndex, NICKNAMES, norm, searchIndex, type Hit } from "@/lib/search";
import { useAtlas } from "@/lib/store";
import type { SearchRow } from "@/lib/types";
import { lookupAddress, type Nearest } from "./geosearch";
import { scrollBehavior } from "@/lib/motion";

type Option =
  | { kind: "place"; hit: Hit }
  | { kind: "hood"; id: string; name: string; boro: string };

/** One box for addresses, business names and neighbourhoods. */
export default function SearchBox({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const path = usePathname();
  const setNta = useAtlas((s) => s.setNta);
  const hoods = useNeighborhoods();
  const [rows, setRows] = useState<SearchRow[] | null>(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [geo, setGeo] = useState<{ label: string; nearest: Nearest[] } | null | "loading">(null);
  const box = useRef<HTMLDivElement>(null);

  const focus = () => {
    setOpen(true);
    if (!rows) loadIndex().then(setRows).catch((e: Error) => setError(e.message));
  };

  const options = useMemo<Option[]>(() => {
    const nq = norm(q);
    if (nq.length < 2) return [];
    const target = NICKNAMES[nq]?.toLowerCase();
    const hoodHits = (hoods.data ?? [])
      .filter((h) => h.places > 0 && (norm(h.name).includes(nq) || (target && h.name.toLowerCase().startsWith(target))))
      .slice(0, 3)
      .map((h) => ({ kind: "hood" as const, id: h.id, name: h.name, boro: h.boro }));
    const placeHits = rows ? searchIndex(rows, q, 7).map((hit) => ({ kind: "place" as const, hit })) : [];
    return [...hoodHits, ...placeHits];
  }, [q, rows, hoods.data]);

  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (o: Option) => {
    setOpen(false);
    setQ("");
    if (o.kind === "place") return router.push(placeHref(o.hit.id));
    setNta(o.id);
    if (path !== "/") router.push(`/?n=${o.id}`);
    else window.scrollTo({ top: 0, behavior: scrollBehavior() });
  };

  const lookup = async () => {
    setGeo("loading");
    try {
      setGeo(await lookupAddress(q));
    } catch (e) {
      console.error(e);
      setError((e as Error).message);
      setGeo(null);
    }
  };

  const looksLikeAddress = /^\d/.test(q.trim());
  return (
    <div ref={box} className={`relative ${compact ? "w-full" : "w-[300px]"}`}>
      <label className="flex h-9 items-center gap-2 border border-ink bg-paper-raised px-2.5">
        <MagnifyingGlass size={14} className="shrink-0 text-muted" />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setSel(0); setGeo(null); setOpen(true); }}
          onFocus={focus}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, options.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter" && options[sel]) choose(options[sel]);
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder="Search an address, place or neighborhood"
          aria-label="Search an address, place or neighborhood"
          className="mono min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-muted"
        />
      </label>
      {open && q.trim().length >= 2 && (
        <div className="absolute left-0 right-0 top-10 z-50 max-h-[70vh] overflow-y-auto border border-ink bg-paper-raised shadow-none">
          {error && <p className="label p-3">{error}</p>}
          {!rows && !error && <p className="label p-3">Loading the address index…</p>}
          {options.map((o, i) => (
            <button key={o.kind === "place" ? o.hit.id : `n${o.id}`} type="button" onMouseEnter={() => setSel(i)} onClick={() => choose(o)}
              className={`block w-full border-b border-rule px-3 py-2 text-left ${i === sel ? "bg-paper" : ""}`}>
              {o.kind === "hood" ? (
                <><span className="label block text-awning">Neighborhood · filter the map</span><span className="text-[16px]">{o.name}</span> <span className="label">{o.boro}</span></>
              ) : (
                <><span className="block text-[16px]">{o.hit.address}</span>
                  <span className="label block truncate">{[o.hit.hood, o.hit.names].filter(Boolean).join(" · ")}</span></>
              )}
            </button>
          ))}
          {rows && !options.length && !looksLikeAddress && (
            <p className="label px-3 py-3">No addresses, businesses or neighborhoods match “{q.trim()}”.</p>
          )}
          {rows && looksLikeAddress && (
            <div className="border-t border-ink p-3">
              {geo === null && (
                <button type="button" onClick={lookup} className="mono min-h-10 text-[11px] uppercase tracking-[0.06em] underline-offset-2 hover:underline">
                  {options.length ? "Not here? Look up this address" : "No match. Look up this address"}
                </button>
              )}
              {geo === "loading" && <p className="label">Looking it up…</p>}
              {geo && geo !== "loading" && (
                <div>
                  <p className="text-[14px]">{geo.label}</p>
                  <p className="label mt-1">{geo.nearest[0]?.metres <= 25
                    ? "This address is in the atlas:"
                    : "No food or drink business recorded here since 2012. Nearest that had one:"}</p>
                  {geo.nearest.map((n) => (
                    <button key={n.id} type="button" onClick={() => { setOpen(false); router.push(placeHref(n.id)); }}
                      className="flex min-h-10 w-full items-center justify-between py-1 text-left text-[14px] hover:underline">
                      <span>{n.address}</span><span className="mono text-[11px] text-muted">{n.metres} m</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
