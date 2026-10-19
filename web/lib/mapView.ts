// Shared camera rules for the deck.gl maps: north-up like a printed NYC map, held to the city.

import { PathLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import type { MapViewState } from "@deck.gl/core";
import type { Palette } from "./color";

export const NYC_CENTER = { longitude: -73.94, latitude: 40.7 };
export const BOUNDS = { west: -74.28, east: -73.68, south: 40.48, north: 40.93 };
export const MAX_ZOOM = 16;

/** Keep the camera over NYC and within the zoom range; drop the canvas size the controller adds. */
export function clampView(v: MapViewState & { width?: number; height?: number }, minZoom: number): MapViewState {
  const next = { ...v };
  delete next.width; // reported from before layout (300x150); keeping it stretches the map
  delete next.height;
  next.zoom = Math.min(MAX_ZOOM, Math.max(minZoom, next.zoom));
  next.longitude = Math.min(BOUNDS.east, Math.max(BOUNDS.west, next.longitude));
  next.latitude = Math.min(BOUNDS.north, Math.max(BOUNDS.south, next.latitude));
  return next;
}

const BOROUGH_LABELS = [
  { text: "BRONX", position: [-73.865, 40.855] },
  { text: "MANHATTAN", position: [-74.005, 40.79] },
  { text: "QUEENS", position: [-73.79, 40.73] },
  { text: "BROOKLYN", position: [-73.955, 40.64] },
  { text: "STATEN ISLAND", position: [-74.155, 40.585] },
];

type Ring = GeoJSON.Position[];

/** Borough coastlines as thin ink lines, so the columns sit on a recognisable map. */
export function outlineLayer(id: string, landPolys: GeoJSON.Position[][][], p: Palette) {
  const rings: Ring[] = landPolys.flatMap((p) => p);
  return new PathLayer<Ring>({
    id,
    data: rings,
    getPath: (r) => r as unknown as [number, number][],
    getColor: [...p.ink, 150],
    getWidth: 1.1,
    widthUnits: "pixels",
  });
}

/** Plex Mono uppercase borough names floating above the relief. */
export function boroughLabels(id: string, height: number, p: Palette) {
  return new TextLayer<(typeof BOROUGH_LABELS)[number]>({
    id,
    data: BOROUGH_LABELS,
    getPosition: (d) => [d.position[0], d.position[1], height],
    getText: (d) => d.text,
    getSize: 11,
    fontFamily: "IBM Plex Mono, ui-monospace, monospace",
    characterSet: "auto",
    getColor: p.muted,
    fontSettings: { sdf: false },
    background: true,
    getBackgroundColor: [...p.paper, 210],
    backgroundPadding: [4, 2],
    parameters: { depthCompare: "always" }, // always on top of the columns
  });
}

export function landPolygons(land: GeoJSON.FeatureCollection): GeoJSON.Position[][][] {
  return land.features.flatMap((f) =>
    f.geometry.type === "MultiPolygon"
      ? (f.geometry as GeoJSON.MultiPolygon).coordinates
      : f.geometry.type === "Polygon"
        ? [(f.geometry as GeoJSON.Polygon).coordinates]
        : [],
  );
}

/** Parks as flat muted green under the columns (Central Park, Prospect Park, Flushing Meadows...). */
export function parksLayer(id: string, parks: GeoJSON.FeatureCollection, p: Palette) {
  return new SolidPolygonLayer<GeoJSON.Position[][]>({
    id,
    data: landPolygons(parks),
    getPolygon: (p) => p as unknown as [number, number][][],
    getFillColor: p.park,
  });
}

/** Point-in-land test (even-odd ray casting) with a per-cell cache; the hex grid is fixed, so each
 *  cell is tested once per page view. */
export function makeLandTest(landPolys: GeoJSON.Position[][][]) {
  const boxes = landPolys.map((poly) => {
    let w = Infinity, e = -Infinity, s = Infinity, n = -Infinity;
    for (const [x, y] of poly[0]) {
      w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y);
    }
    return { poly, w, e, s, n };
  });
  const inRing = (ring: GeoJSON.Position[], x: number, y: number) => {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  };
  const cache = new Map<string, boolean>();
  return (id: string, x: number, y: number) => {
    const hit = cache.get(id);
    if (hit !== undefined) return hit;
    const on = boxes.some((b) => x >= b.w && x <= b.e && y >= b.s && y <= b.n &&
      inRing(b.poly[0], x, y) && !b.poly.slice(1).some((hole) => inRing(hole, x, y)));
    cache.set(id, on);
    return on;
  };
}
