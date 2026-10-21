// Respect the visitor's "reduce motion" setting: map flights jump, transitions snap, scrolls are instant.

export const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** An animation length in ms, or 0 when the visitor prefers reduced motion. */
export const motionMs = (ms: number) => (reducedMotion() ? 0 : ms);

/** Scroll behaviour for scrollTo / scrollIntoView. */
export const scrollBehavior = (): ScrollBehavior => (reducedMotion() ? "auto" : "smooth");
