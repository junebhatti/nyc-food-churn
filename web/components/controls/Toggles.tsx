"use client";

import { useAtlas } from "@/lib/store";
import type { CategoryFilter, View } from "@/lib/types";

const VIEWS: { id: View; label: string }[] = [
  { id: "churn", label: "Churn" },
  { id: "lifespan", label: "Lifespan" },
  { id: "risk", label: "Risk" },
  { id: "rent", label: "Rent" },
];

export const CATEGORY_BUTTONS: { id: CategoryFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "restaurant", label: "Restaurant" },
  { id: "bar", label: "Bar" },
  { id: "cafe", label: "Café" },
  { id: "bakery", label: "Bakery" },
  { id: "bodega", label: "Bodega" },
];

/** Segmented control: four buttons in one ink box with ink dividers. */
export function ViewToggle({ mobile = false }: { mobile?: boolean }) {
  const { view, setView } = useAtlas();
  return (
    <div role="group" aria-label="Map view" className={`mono grid grid-cols-4 border border-ink text-[11px] uppercase tracking-[0.06em] ${mobile ? "w-full" : ""}`}>
      {VIEWS.map((v, i) => (
        <button
          key={v.id}
          type="button"
          aria-pressed={view === v.id}
          onClick={() => setView(v.id)}
          className={`px-3 ${mobile ? "h-11" : "h-9"} ${i ? "border-l border-ink" : ""} ${view === v.id ? "bg-ink text-paper" : "hover:bg-paper-raised"}`}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

export function CategoryButtons({ mobile = false }: { mobile?: boolean }) {
  const { category, setCategory } = useAtlas();
  return (
    <div
      role="group"
      aria-label="Category"
      className={`mono flex gap-2 text-[11px] uppercase tracking-[0.06em] ${mobile ? "-mx-4 overflow-x-auto px-4 pb-1" : "flex-wrap"}`}
    >
      {CATEGORY_BUTTONS.map((c) => (
        <button
          key={c.id}
          type="button"
          aria-pressed={category === c.id}
          onClick={() => setCategory(c.id)}
          className={`shrink-0 border px-3 ${mobile ? "h-9" : "h-9"} ${category === c.id ? "border-ink bg-ink text-paper" : "border-rule hover:bg-paper-raised"}`}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}
