"use client";

import { useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import { AmbientLight, DirectionalLight, LightingEffect, type MapViewState } from "@deck.gl/core";
import { ColumnLayer, SolidPolygonLayer } from "@deck.gl/layers";
import { useAtlas } from "@/lib/store";
import { hasCategory } from "@/lib/data";
import { LAND } from "@/lib/color";
import { buildingColor, hexBins, makeScale, rawValue, type Cell } from "@/lib/metrics";
import type { Building, Neighborhood } from "@/lib/types";

// Matte plaster relief: soft ambient plus one light from the west/north-west, no gloss.
const lighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 252, 245], intensity: 0.9 }),
  sun: new DirectionalLight({ color: [255, 248, 236], intensity: 1.1, direction: [1, -1.2, -1.6] }),
});
const MATERIAL = { ambient: 0.6, diffuse: 0.5, shininess: 0, specularColor: [0, 0, 0] as [number, number, number] };
const BUILDING_ZOOM = 12.6; // above this, one column per building
const HEX_RADIUS_M = 380;

export interface HoverInfo {
  building: number;
  x: number;
  y: number;
}

interface Props {
  buildings: Building[];
  hoods: Neighborhood[];
  land: GeoJSON.FeatureCollection;
  flat?: boolean; // mobile: pitch 0, no extrusion
  initialZoom?: number;
  onHover?: (h: HoverInfo | null) => void;
  onTap?: (building: number) => void;
}

export default function HeroMap({ buildings, hoods, land, flat = false, initialZoom = 10.2, onHover, onTap }: Props) {
  const { year, view, category } = useAtlas();
  const [viewState, setViewState] = useState<MapViewState>({
    longitude: -73.935,
    latitude: 40.705,
    zoom: initialZoom,
    pitch: flat ? 0 : 48,
    bearing: flat ? 0 : -20,
  });

  const scale = useMemo(() => makeScale(buildings, view, hoods), [buildings, view, hoods]);
  const value = useMemo(() => (b: Building) => scale(rawValue(b, view, hoods)), [scale, view, hoods]);
  const showBuildings = !flat && viewState.zoom > BUILDING_ZOOM;
  const cells = useMemo<Cell[]>(
    () => (showBuildings ? [] : hexBins(buildings, flat ? 520 : HEX_RADIUS_M, value, year, category)),
    [buildings, value, year, category, showBuildings, flat],
  );

  // Tallest hexes (99th percentile) rise ~2.5 km, so the whole city reads as one relief.
  const hexScale = useMemo(() => {
    const h = cells.map((c) => c.height).sort((a, b) => a - b);
    return h.length ? 2500 / Math.max(1, h[Math.floor(0.99 * (h.length - 1))]) : 1;
  }, [cells]);

  // Boroughs are MultiPolygons; the land plate wants one ring set per polygon.
  const landPolys = useMemo(
    () =>
      land.features.flatMap((f) =>
        f.geometry.type === "MultiPolygon"
          ? (f.geometry as GeoJSON.MultiPolygon).coordinates
          : [(f.geometry as GeoJSON.Polygon).coordinates],
      ),
    [land],
  );

  const layers = [
    new SolidPolygonLayer<GeoJSON.Position[][]>({
      id: "land",
      data: landPolys,
      getPolygon: (p) => p as unknown as [number, number][][], // GeoJSON rings are number[] positions
      getFillColor: LAND,
      _full3d: false,
    }),
    showBuildings
      ? new ColumnLayer<Building>({
          id: "buildings",
          data: buildings,
          diskResolution: 4,
          radius: 18,
          angle: 45,
          extruded: true,
          elevationScale: 22,
          getPosition: (b) => [b.lon, b.lat],
          getElevation: (b) => (hasCategory(b, category) ? b.tenants : b.tenants * 0.15),
          getFillColor: (b) => buildingColor(b, value(b), year, category),
          material: MATERIAL,
          pickable: true,
          updateTriggers: { getFillColor: [year, view, category], getElevation: [category] },
          transitions: { getFillColor: 300 },
        })
      : new ColumnLayer<Cell>({
          id: "hexes",
          data: cells,
          diskResolution: 6,
          radius: (flat ? 520 : HEX_RADIUS_M) * 0.9,
          extruded: !flat,
          elevationScale: hexScale,
          getPosition: (c) => [c.lon, c.lat],
          getElevation: (c) => c.height,
          getFillColor: (c) => c.color,
          material: MATERIAL,
          pickable: true,
          transitions: { getFillColor: 300 },
        }),
  ];

  return (
    <DeckGL
      viewState={viewState}
      onViewStateChange={({ viewState: v }) => {
        // Drop width/height: the controller reports the canvas size from before layout (300x150),
        // and keeping it in viewState renders the whole map at that size, stretched.
        const next = { ...(v as MapViewState & { width?: number; height?: number }) };
        delete next.width;
        delete next.height;
        setViewState(next);
      }}
      controller={flat ? { dragRotate: false, touchRotate: false } : { dragRotate: true }}
      layers={layers}
      effects={flat ? [] : [lighting]}
      getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
      onHover={(info) => {
        if (!onHover) return;
        const o = info.object as Building | Cell | undefined;
        if (!o) return onHover(null);
        onHover({ building: "top" in o ? o.top : o.idx, x: info.x, y: info.y });
      }}
      onClick={(info) => {
        const o = info.object as Building | Cell | undefined;
        if (o && onTap) onTap("top" in o ? o.top : o.idx);
      }}
    />
  );
}
