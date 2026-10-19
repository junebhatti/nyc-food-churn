"use client";

import { useEffect } from "react";
import { X } from "@phosphor-icons/react";
import { useAtlas } from "@/lib/store";
import type { Neighborhood } from "@/lib/types";

/** Neighbourhood filter for the map: a native select (searchable by typing), plus a clear button. */
export default function NeighborhoodPicker({ hoods, mobile = false }: { hoods: Neighborhood[] | null; mobile?: boolean }) {
  const { nta, setNta } = useAtlas();
  const options = (hoods ?? []).filter((h) => h.places > 0).sort((a, b) => a.name.localeCompare(b.name));
  return (
    <div className={`flex items-center ${mobile ? "w-full" : ""}`}>
      <select
        value={nta ?? ""}
        onChange={(e) => setNta(e.target.value || null)}
        aria-label="Neighborhood"
        className={`mono h-9 border border-ink bg-paper-raised px-2 text-[11px] ${mobile ? "h-11 flex-1" : "w-[210px]"} ${nta ? "border-2" : ""}`}
      >
        <option value="">All of NYC</option>
        {options.map((h) => <option key={h.id} value={h.id}>{h.name} · {h.boro}</option>)}
      </select>
      {nta && (
        <button type="button" onClick={() => setNta(null)} aria-label="Show all of NYC"
          className={`flex items-center justify-center border border-l-0 border-ink hover:bg-paper-raised ${mobile ? "h-11 w-11" : "h-9 w-9"}`}>
          <X size={14} />
        </button>
      )}
    </div>
  );
}

/** Keep ?n=<NTA> in the address bar in sync with the filter, so a neighbourhood view can be shared. */
export function useNtaUrlSync() {
  const { nta, setNta } = useAtlas();
  useEffect(() => {
    const n = new URLSearchParams(window.location.search).get("n");
    if (n) setNta(n);
  }, [setNta]);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (nta) url.searchParams.set("n", nta);
    else url.searchParams.delete("n");
    window.history.replaceState(null, "", url);
  }, [nta]);
}
