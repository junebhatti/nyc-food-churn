"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { WebMercatorViewport, type MapViewState } from "@deck.gl/core";

const ZOOM_PER_PINCH = 0.012; // per wheel pixel while pinching (ctrl+wheel in Chrome/Firefox)
const ROTATE_PER_PX = 0.25; // degrees per pixel of shift+swipe
const MAX_PITCH = 60;

interface Options {
  el: RefObject<HTMLDivElement | null>;
  getView: () => MapViewState;
  setView: (v: MapViewState) => void;
  enabled: boolean;
}

/**
 * Apple-Maps-style trackpad control for a deck.gl map that sits inside a scrolling page.
 * - Pinch always zooms (ctrl+wheel in Chrome/Firefox, gesture events in Safari).
 * - After the map is clicked ("active"), two-finger swipe pans and shift+swipe rotates/tilts;
 *   leaving the map deactivates it, so swiping over an inactive map scrolls the page as usual.
 * - Safari's two-finger rotate gesture turns the map.
 */
export function useTrackpad({ el, getView, setView, enabled }: Options) {
  const [active, setActive] = useState(false);
  const activeRef = useRef(false);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    const node = el.current;
    if (!node || !enabled) return;

    const size = () => ({ width: node.clientWidth, height: node.clientHeight });

    const onWheel = (e: WheelEvent) => {
      const v = getView();
      if (e.ctrlKey) {
        e.preventDefault(); // pinch: zoom the map, never the browser page
        setView({ ...v, zoom: v.zoom - e.deltaY * ZOOM_PER_PINCH });
        return;
      }
      if (!activeRef.current) return; // let the page scroll
      e.preventDefault();
      if (e.shiftKey) {
        // Some browsers turn shift+vertical scroll into horizontal; take whichever axis moved.
        const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
        const horizontal = Math.abs(e.deltaX) >= Math.abs(e.deltaY);
        setView(
          horizontal
            ? { ...v, bearing: (v.bearing ?? 0) + d * ROTATE_PER_PX }
            : { ...v, pitch: Math.min(MAX_PITCH, Math.max(0, (v.pitch ?? 0) - d * ROTATE_PER_PX)) },
        );
        return;
      }
      const { width, height } = size();
      const vp = new WebMercatorViewport({ ...v, width, height });
      const [longitude, latitude] = vp.unproject([width / 2 + e.deltaX, height / 2 + e.deltaY]);
      setView({ ...v, longitude, latitude });
    };

    // Safari: pinch and rotate arrive as gesture events.
    let start: { zoom: number; bearing: number } | null = null;
    type Gesture = Event & { scale: number; rotation: number };
    const onGestureStart = (e: Event) => {
      e.preventDefault();
      const v = getView();
      start = { zoom: v.zoom, bearing: v.bearing ?? 0 };
    };
    const onGestureChange = (e: Event) => {
      e.preventDefault();
      if (!start) return;
      const g = e as Gesture;
      setView({ ...getView(), zoom: start.zoom + Math.log2(g.scale), bearing: start.bearing - g.rotation });
    };
    const onGestureEnd = () => {
      start = null;
    };
    const onLeave = () => setActive(false);

    node.addEventListener("wheel", onWheel, { passive: false });
    node.addEventListener("gesturestart", onGestureStart);
    node.addEventListener("gesturechange", onGestureChange);
    node.addEventListener("gestureend", onGestureEnd);
    node.addEventListener("mouseleave", onLeave);
    return () => {
      node.removeEventListener("wheel", onWheel);
      node.removeEventListener("gesturestart", onGestureStart);
      node.removeEventListener("gesturechange", onGestureChange);
      node.removeEventListener("gestureend", onGestureEnd);
      node.removeEventListener("mouseleave", onLeave);
    };
  }, [el, getView, setView, enabled]);

  return { active, activate: () => setActive(true) };
}
