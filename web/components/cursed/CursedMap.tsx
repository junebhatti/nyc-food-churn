"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import DeckGL from "@deck.gl/react";
import type { MapViewState } from "@deck.gl/core";
import { ScatterplotLayer, SolidPolygonLayer, TextLayer } from "@deck.gl/layers";
import { ArrowsOut } from "@phosphor-icons/react";
import { usePalette } from "@/lib/usePalette";
import { useStreets } from "@/lib/data";
import { FLY } from "@/lib/focus";
import { boroughLabels, clampView, GROUND, landPolygons, NYC_CENTER, outlineLayer, parksLayer, streetLayers } from "@/lib/mapView";
import type { CursedAddress } from "@/lib/types";
import { motionMs } from "@/lib/motion";

interface Props {
  addresses: CursedAddress[];
  land: GeoJSON.FeatureCollection;
  parks: GeoJSON.FeatureCollection | null;
  selected: number;
  onSelect: (i: number) => void;
}

const MIN_ZOOM = 8.9;
const CITY: MapViewState = { ...NYC_CENTER, zoom: 9.15, pitch: 0, bearing: 0 };
const FOCUS_ZOOM = 13; // close enough to see the blocks around a picked address
const ZOOM_PER_PINCH = 0.012;
const STREETS_ZOOM = 11.5; // streets appear (and load) once zoomed this close

type Dot = { a: CursedAddress; i: number };

const COARSE = "(pointer: coarse)";
function subscribeCoarse(cb: () => void) {
  const m = window.matchMedia(COARSE);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}

/** City map of the listed cursed addresses: numbered dots, the selected one red. Picking an
 *  address (here or in the list) flies to it; "Whole city" flies back. Pinch or double-click
 *  zooms, drag pans, and plain scrolling still scrolls the page. */
export default function CursedMap({ addresses, land, parks, selected, onSelect }: Props) {
  const palette = usePalette();
  const landPolys = useMemo(() => landPolygons(land), [land]);
  const [viewState, setViewState] = useState<MapViewState>(CITY);
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  // Touch screens: one finger scrolls the page (it would otherwise be trapped by the map); pinch zooms and moves it.
  const touch = useSyncExternalStore(subscribeCoarse, () => window.matchMedia(COARSE).matches, () => false);
  const showStreets = viewState.zoom > STREETS_ZOOM;
  const streets = useStreets(showStreets);

  // Fly to the picked address, but open on the whole city.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const a = addresses[selected];
    setViewState((v) => ({ ...v, longitude: a.lon, latitude: a.lat, zoom: FOCUS_ZOOM, transitionDuration: motionMs(900), transitionInterpolator: FLY }) as MapViewState);
  }, [selected, addresses]);

  // Pinch (ctrl+wheel) zooms the map; ordinary scrolling is left to the page.
  useEffect(() => {
    const node = box.current;
    if (!node) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      setViewState((v) => clampView({ ...v, zoom: v.zoom - e.deltaY * ZOOM_PER_PINCH }, MIN_ZOOM));
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  // Draw the selected and hovered dots last so they sit on top of their neighbours.
  const dots = useMemo<Dot[]>(() => {
    const rank = (d: Dot) => (d.i === selected ? 2 : d.i === hover?.i ? 1 : 0);
    return addresses.map((a, i) => ({ a, i })).sort((x, y) => rank(x) - rank(y));
  }, [addresses, selected, hover?.i]);
  const big = (d: Dot) => d.i === selected || d.i === hover?.i;

  const layers = [
    new SolidPolygonLayer<GeoJSON.Position[][]>({ id: "land", data: landPolys, getPolygon: (p) => p as unknown as [number, number][][], getFillColor: palette.land, parameters: GROUND }),
    ...(parks ? [parksLayer("parks", parks, palette)] : []),
    ...(showStreets && streets.data ? streetLayers("streets", streets.data, palette) : []),
    outlineLayer("outline", landPolys, palette),
    boroughLabels("boroughs", 0, palette),
    new ScatterplotLayer<Dot>({
      id: "cursed",
      data: dots,
      getPosition: (d) => [d.a.lon, d.a.lat],
      getRadius: (d) => (big(d) ? 12 : 9),
      radiusUnits: "pixels",
      getFillColor: (d) => (d.i === selected ? palette.quadrant.ed : palette.ink),
      getLineColor: palette.paper,
      lineWidthMinPixels: 1.5,
      stroked: true,
      pickable: true,
      updateTriggers: { getRadius: [selected, hover?.i], getFillColor: [selected, palette] },
    }),
    new TextLayer<Dot>({
      id: "ranks",
      data: dots,
      getPosition: (d) => [d.a.lon, d.a.lat],
      getText: (d) => String(d.a.rank),
      getSize: (d) => (big(d) ? 12 : 10),
      getColor: palette.paper,
      fontFamily: "IBM Plex Mono, ui-monospace, monospace",
      fontWeight: 500,
      characterSet: "auto",
      fontSettings: { sdf: false },
      updateTriggers: { getSize: [selected, hover?.i] },
    }),
  ];

  const tip = hover ? addresses[hover.i] : null;
  const zoomedIn = viewState.zoom > CITY.zoom + 0.5;

  return (
    <div ref={box} className="absolute inset-0" role="region" aria-label="Map of the most cursed addresses; the same addresses are listed beside it.">
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: v, interactionState }) => {
          // The map moved under the cursor (a fly or a drag), so the hover card no longer points at its dot.
          if (interactionState?.inTransition || interactionState?.isDragging) setHover(null);
          setViewState(clampView(v as MapViewState, MIN_ZOOM));
        }}
        controller={{ scrollZoom: false, dragRotate: false, touchRotate: false, doubleClickZoom: true, dragPan: !touch }}
        touchAction={touch ? "pan-y" : "none"}
        layers={layers}
        pickingRadius={10}
        getCursor={({ isHovering, isDragging }) => (isDragging ? "grabbing" : isHovering ? "pointer" : "grab")}
        onHover={(info) => {
          const d = info.object as Dot | undefined;
          setHover(d ? { i: d.i, x: info.x, y: info.y } : null);
        }}
        onClick={(info) => {
          const d = info.object as Dot | undefined;
          if (!d) return;
          setHover(null);
          onSelect(d.i);
        }}
      />
      {tip && hover && (
        <div className="pointer-events-none absolute z-10 w-max max-w-[220px] border border-ink bg-paper-raised px-2.5 py-1.5"
          style={{ left: hover.x + 14, top: hover.y - 10 }}>
          <div className="text-[15px] leading-tight">{tip.rank}. {tip.address}</div>
          <div className="label">{tip.neighborhood} · {tip.tenants} tenants · {tip.medianLife != null ? `${tip.medianLife.toFixed(1)}y median` : ""}</div>
        </div>
      )}
      {zoomedIn && (
        <button type="button" onClick={() => setViewState({ ...CITY, transitionDuration: motionMs(700), transitionInterpolator: FLY } as MapViewState)}
          className="mono absolute right-3 top-3 z-10 flex h-9 items-center gap-1.5 border border-ink bg-paper-raised px-3 text-[11px] uppercase tracking-[0.06em] hover:bg-paper">
          <ArrowsOut size={13} /> Whole city
        </button>
      )}
      <div className="label pointer-events-none absolute bottom-3 left-3 bg-paper/85 px-2 py-1">{touch ? "Pinch to zoom · tap a dot" : "Pinch or double-click to zoom · drag to pan"}</div>
    </div>
  );
}
