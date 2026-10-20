"use client";

import { useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import type { MapViewState } from "@deck.gl/core";
import { ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { usePalette } from "@/lib/usePalette";
import { boroughLabels, clampView, landPolygons, NYC_CENTER, outlineLayer, parksLayer } from "@/lib/mapView";
import type { CursedAddress } from "@/lib/types";

interface Props {
  addresses: CursedAddress[];
  land: GeoJSON.FeatureCollection;
  parks: GeoJSON.FeatureCollection | null;
  selected: number;
  onSelect: (i: number) => void;
}

const MIN_ZOOM = 8.9;

/** Flat city map with the listed cursed addresses as numbered dots; the selected one is red. */
export default function CursedMap({ addresses, land, parks, selected, onSelect }: Props) {
  const palette = usePalette();
  const landPolys = useMemo(() => landPolygons(land), [land]);
  const [viewState, setViewState] = useState<MapViewState>({ ...NYC_CENTER, zoom: 9.15, pitch: 0, bearing: 0 });
  // Draw the selected dot last so it sits on top of any neighbours.
  const dots = useMemo(
    () => addresses.map((a, i) => ({ a, i })).sort((x, y) => Number(x.i === selected) - Number(y.i === selected)),
    [addresses, selected],
  );

  const layers = [
    new SolidPolygonLayer<GeoJSON.Position[][]>({ id: "land", data: landPolys, getPolygon: (p) => p as unknown as [number, number][][], getFillColor: palette.land }),
    ...(parks ? [parksLayer("parks", parks, palette)] : []),
    outlineLayer("outline", landPolys, palette),
    boroughLabels("boroughs", 0, palette),
    new ScatterplotLayer<(typeof dots)[number]>({
      id: "cursed",
      data: dots,
      getPosition: (d) => [d.a.lon, d.a.lat],
      getRadius: (d) => (d.i === selected ? 11 : 8),
      radiusUnits: "pixels",
      getFillColor: (d) => (d.i === selected ? palette.quadrant.ed : palette.ink),
      getLineColor: palette.paper,
      lineWidthMinPixels: 1.5,
      stroked: true,
      pickable: true,
      updateTriggers: { getRadius: [selected], getFillColor: [selected, palette] },
    }),
    new TextLayer<(typeof dots)[number]>({
      id: "ranks",
      data: dots,
      getPosition: (d) => [d.a.lon, d.a.lat],
      getText: (d) => String(d.a.rank),
      getSize: (d) => (d.i === selected ? 12 : 10),
      getColor: palette.paper,
      fontFamily: "IBM Plex Mono, ui-monospace, monospace",
      fontWeight: 500,
      characterSet: "auto",
      fontSettings: { sdf: false },
      updateTriggers: { getSize: [selected] },
    }),
  ];

  return (
    <DeckGL
      viewState={viewState}
      onViewStateChange={({ viewState: v }) => setViewState(clampView(v as MapViewState, MIN_ZOOM))}
      // Drag pans; scrolling stays with the page.
      controller={{ scrollZoom: false, dragRotate: false, touchRotate: false }}
      layers={layers}
      getCursor={({ isHovering }) => (isHovering ? "pointer" : "grab")}
      onClick={(info) => {
        const d = info.object as (typeof dots)[number] | undefined;
        if (d) onSelect(d.i);
      }}
    />
  );
}
