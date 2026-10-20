"use client";

import { useEffect, useRef, useState } from "react";

/** Measured width of a container, so an SVG chart can be drawn at its real on-screen width (labels
 *  keep their pixel size on phones instead of shrinking with a fixed viewBox). `fallback` is used
 *  for the server render and the first paint. */
export function useWidth<T extends HTMLElement = HTMLDivElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const w = Math.round(e.contentRect.width);
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}
