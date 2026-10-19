// Neighbourhood focus for the main map: camera framing and the highlighted outline.

import { FlyToInterpolator, WebMercatorViewport, type MapViewState } from "@deck.gl/core";
import { PathLayer } from "@deck.gl/layers";
import type { Palette } from "./color";

export const FLY = new FlyToInterpolator({ speed: 1.6 });

function rings(g: GeoJSON.Geometry): GeoJSON.Position[][] {
  if (g.type === "Polygon") return g.coordinates;
  if (g.type === "MultiPolygon") return g.coordinates.flat();
  return [];
}

/** Camera that frames a neighbourhood, keeping the current bearing and pitch. */
export function frameGeometry(g: GeoJSON.Geometry, size: { width: number; height: number }, current: MapViewState): MapViewState {
  const pts = rings(g).flat();
  const lons = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  const vp = new WebMercatorViewport({ ...size, longitude: current.longitude, latitude: current.latitude, zoom: current.zoom });
  const { longitude, latitude, zoom } = vp.fitBounds(
    [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
    { padding: Math.min(80, Math.floor(Math.min(size.width, size.height) / 6)) },
  );
  return { ...current, longitude, latitude, zoom: Math.min(zoom, 15) };
}

/** Thick ink outline around the chosen neighbourhood. */
export function focusOutline(g: GeoJSON.Geometry, p: Palette) {
  return new PathLayer<GeoJSON.Position[]>({
    id: "focus-outline",
    data: rings(g),
    getPath: (r) => r as unknown as [number, number][],
    getColor: [...p.ink, 230],
    getWidth: 2.5,
    widthUnits: "pixels",
    parameters: { depthCompare: "always" },
  });
}
