"use client";

import { useEffect, useRef, useState } from "react";

/** Measured width (and height) of a container, so an SVG chart can be drawn at its real on-screen width (labels
 *  keep their pixel size on phones instead of shrinking with a fixed viewBox). `fallback` is used
 *  for the server render and the first paint. */
export function useWidth<T extends HTMLElement = HTMLDivElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: fallback, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      const width = Math.round(e.contentRect.width);
      if (width > 0) setSize({ width, height: Math.round(e.contentRect.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size.width, size.height] as const;
}
