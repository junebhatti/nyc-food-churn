"use client";

import { create } from "zustand";
import type { CategoryFilter, View } from "./types";

export const FIRST_YEAR = 2012;
export const LAST_YEAR = 2026;
const STEP_MS = 650; // play advances one year per 650 ms (handoff spec)

interface AtlasState {
  year: number;
  playing: boolean;
  view: View;
  category: CategoryFilter;
  hoveredBuilding: number | null;
  nta: string | null; // neighbourhood filter (NTA 2020 code), mirrored in the URL as ?n=
  setNta: (n: string | null) => void;
  setYear: (y: number) => void;
  setView: (v: View) => void;
  setCategory: (c: CategoryFilter) => void;
  setHovered: (i: number | null) => void;
  togglePlay: () => void;
}

let timer: ReturnType<typeof setInterval> | null = null;

export const useAtlas = create<AtlasState>((set, get) => ({
  year: LAST_YEAR,
  playing: false,
  view: "churn",
  category: "all",
  hoveredBuilding: null,
  nta: null,
  setNta: (nta) => set({ nta }),
  setYear: (year) => set({ year }),
  setView: (view) => set({ view }),
  setCategory: (category) => set({ category }),
  setHovered: (hoveredBuilding) => set({ hoveredBuilding }),
  togglePlay: () => {
    if (get().playing) {
      if (timer) clearInterval(timer);
      timer = null;
      set({ playing: false });
      return;
    }
    if (get().year >= LAST_YEAR) set({ year: FIRST_YEAR });
    set({ playing: true });
    timer = setInterval(() => {
      const next = get().year + 1;
      if (next > LAST_YEAR) {
        if (timer) clearInterval(timer);
        timer = null;
        set({ playing: false });
        return;
      }
      set({ year: next });
    }, STEP_MS);
  },
}));
