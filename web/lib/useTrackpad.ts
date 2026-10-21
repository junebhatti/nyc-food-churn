"use client";

import { useEffect, type RefObject } from "react";
import { WebMercatorViewport, type MapViewState } from "@deck.gl/core";

const ZOOM_PER_PINCH = 0.012; // per wheel pixel while pinching (ctrl+wheel in Chrome/Firefox)
const ZOOM_PER_NOTCH = 0.5; // per mouse-wheel click
const ROTATE_PER_PX = 0.25; // degrees of bearing per pixel of sideways swipe
const TILT_PER_PX = 0.2; // degrees of pitch per pixel of vertical swipe
const MAX_PITCH = 60;

interface Options {
  el: RefObject<HTMLDivElement | null>;
  getView: () => MapViewState;
  setView: (v: MapViewState) => void;
  enabled: boolean;
}

/** A real mouse wheel: line-based deltas (Firefox) or whole 100ish-pixel notches with no sideways
 *  movement. Trackpads send small, mixed deltas. A very fast vertical trackpad flick can look like
 *  a notch; it then zooms instead of tilting, which is harmless. */
const isMouseWheel = (e: WheelEvent) =>
  e.deltaMode === 1 || (e.deltaX === 0 && Number.isInteger(e.deltaY) && Math.abs(e.deltaY) >= 50);

/**
 * Trackpad control for the full-page deck.gl map:
 * - pinch zooms (ctrl+wheel in Chrome/Firefox, gesture events in Safari),
 * - a two-finger sideways swipe rotates, a vertical swipe tilts (up tilts into 3D),
 * - a mouse wheel zooms, since a mouse can't pinch.
 * Panning is click-and-drag, handled by deck.gl's own controller.
 */
export function useTrackpad({ el, getView, setView, enabled }: Options) {
  useEffect(() => {
    const node = el.current;
    if (!node || !enabled) return;

    // Zoom keeping the point under the cursor fixed, like a map app.
    const zoomAt = (e: WheelEvent, v: MapViewState, zoom: number) => {
      const r = node.getBoundingClientRect();
      const px: [number, number] = [e.clientX - r.left, e.clientY - r.top];
      const size = { width: r.width, height: r.height };
      const lngLat = new WebMercatorViewport({ ...v, ...size }).unproject(px) as [number, number];
      const { longitude, latitude } = new WebMercatorViewport({ ...v, ...size, zoom }).panByPosition(lngLat, px);
      setView({ ...v, zoom, longitude: longitude ?? v.longitude, latitude: latitude ?? v.latitude });
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); // the map owns every wheel event over it, including browser zoom
      const v = getView();
      if (e.ctrlKey) {
        zoomAt(e, v, v.zoom - e.deltaY * ZOOM_PER_PINCH);
        return;
      }
      if (isMouseWheel(e)) {
        zoomAt(e, v, v.zoom - Math.sign(e.deltaY) * ZOOM_PER_NOTCH);
        return;
      }
      // Follow the dominant axis so a vertical swipe doesn't also drift the bearing.
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        setView({ ...v, bearing: (v.bearing ?? 0) + e.deltaX * ROTATE_PER_PX });
      } else {
        setView({ ...v, pitch: Math.min(MAX_PITCH, Math.max(0, (v.pitch ?? 0) + e.deltaY * TILT_PER_PX)) });
      }
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

    node.addEventListener("wheel", onWheel, { passive: false });
    node.addEventListener("gesturestart", onGestureStart);
    node.addEventListener("gesturechange", onGestureChange);
    node.addEventListener("gestureend", onGestureEnd);
    return () => {
      node.removeEventListener("wheel", onWheel);
      node.removeEventListener("gesturestart", onGestureStart);
      node.removeEventListener("gesturechange", onGestureChange);
      node.removeEventListener("gestureend", onGestureEnd);
    };
  }, [el, getView, setView, enabled]);
}
