"use client";

import { useSyncExternalStore } from "react";
import { DARK, LIGHT, type Palette } from "./color";

const QUERY = "(prefers-color-scheme: dark)";

function subscribe(cb: () => void) {
  const m = window.matchMedia(QUERY);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}

/** Map palette that follows the system light/dark setting. Light during SSR. */
export function usePalette(): Palette {
  const dark = useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
  return dark ? DARK : LIGHT;
}
