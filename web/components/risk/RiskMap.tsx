"use client";

import { useMemo } from "react";
import DeckGL from "@deck.gl/react";
import { AmbientLight, DirectionalLight, LightingEffect } from "@deck.gl/core";
import { PolygonLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { quadrantBlock, type Quadrant } from "@/lib/color";
import { usePalette } from "@/lib/usePalette";
import type { RiskHood } from "@/lib/quadrants";
import { boroughLabels, clampView, NYC_CENTER, outlineLayer } from "@/lib/mapView";
import type { MapViewState } from "@deck.gl/core";
import { useState } from "react";
import { motionMs } from "@/lib/motion";

const lighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 252, 245], intensity: 0.9 }),
  sun: new DirectionalLight({ color: [255, 248, 236], intensity: 1.1, direction: [1, -1.2, -1.6] }),
});
const MATERIAL = { ambient: 0.6, diffuse: 0.5, shininess: 0, specularColor: [0, 0, 0] as [number, number, number] };

interface Props {
  rows: RiskHood[];
  land: GeoJSON.FeatureCollection;
  selected: string;
  filter: Quadrant | null;
  onSelect: (id: string) => void;
}

type Poly = { id: string; ring: GeoJSON.Position[][]; hood: RiskHood };

const polys = (g: GeoJSON.Geometry): GeoJSON.Position[][][] =>
  g.type === "MultiPolygon" ? g.coordinates : g.type === "Polygon" ? [g.coordinates] : [];

/** One extruded block per neighbourhood, raised by its 3-yr closure odds (handoff 3a). */
export default function RiskMap({ rows, land, selected, filter, onSelect }: Props) {
  const palette = usePalette();
  const data = useMemo<Poly[]>(() => rows.flatMap((h) => polys(h.geometry).map((ring) => ({ id: h.id, ring, hood: h }))), [rows]);
  const landPolys = useMemo(() => land.features.flatMap((f) => polys(f.geometry)), [land]);
  const minC = Math.min(...rows.map((r) => r.closure3y));
  const sel = rows.find((r) => r.id === selected);
  const label = useMemo(() => {
    if (!sel) return [];
    const ring = polys(sel.geometry).sort((a, b) => b[0].length - a[0].length)[0]?.[0] ?? [];
    const c = ring.reduce((a, p) => [a[0] + p[0] / ring.length, a[1] + p[1] / ring.length], [0, 0]);
    return [{ position: [c[0], c[1], (sel.closure3y - minC) * 9000 + 300], text: sel.name.split("-")[0] }];
  }, [sel, minC]);

  const [viewState, setViewState] = useState<MapViewState>({ ...NYC_CENTER, zoom: 9.05, pitch: 40, bearing: 0 });

  const layers = [
    new SolidPolygonLayer<GeoJSON.Position[][]>({ id: "land", data: landPolys, getPolygon: (p) => p as unknown as [number, number][][], getFillColor: palette.land }),
    outlineLayer("outline", landPolys, palette),
    new PolygonLayer<Poly>({
      id: "hoods",
      data,
      extruded: true,
      wireframe: false,
      stroked: false,
      getPolygon: (d) => d.ring,
      getElevation: (d) => (filter && d.hood.quadrant !== filter ? 40 : (d.hood.closure3y - minC) * 9000 + 60),
      getFillColor: (d) =>
        filter && d.hood.quadrant !== filter ? palette.filteredOut : quadrantBlock(d.hood.quadrant, d.id === selected, palette),
      material: MATERIAL,
      pickable: true,
      updateTriggers: { getFillColor: [selected, filter, palette], getElevation: [filter] },
      transitions: { getElevation: motionMs(300) },
    }),
    new TextLayer({
      id: "callout",
      data: label,
      getPosition: (d: { position: number[] }) => d.position as [number, number, number],
      getText: (d: { text: string }) => d.text,
      getSize: 15,
      fontFamily: "Newsreader, Georgia, serif",
      getColor: palette.ink,
      background: true,
      getBackgroundColor: [...palette.paper, 230],
      backgroundPadding: [4, 2],
      getPixelOffset: [0, -14],
    }),
    boroughLabels("boroughs", 3300, palette),
  ];

  return (
    <DeckGL
      viewState={viewState}
      onViewStateChange={({ viewState: v }) => setViewState(clampView(v as MapViewState, 8.8))}
      controller={{ scrollZoom: false }}
      layers={layers}
      effects={[lighting]}
      getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
      onHover={(info) => {
        const d = info.object as Poly | undefined;
        if (d) onSelect(d.id);
      }}
    />
  );
}
