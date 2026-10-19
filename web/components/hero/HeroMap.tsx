"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { AmbientLight, DirectionalLight, LightingEffect, LinearInterpolator, type MapViewState } from "@deck.gl/core";
import { ColumnLayer, SolidPolygonLayer } from "@deck.gl/layers";
import { useAtlas } from "@/lib/store";
import { hasCategory } from "@/lib/data";
import { boroughLabels, clampView, landPolygons, makeLandTest, NYC_CENTER, outlineLayer, parksLayer } from "@/lib/mapView";
import { usePalette } from "@/lib/usePalette";
import { buildingColor, hexBins, makeScale, rawValue, type Cell } from "@/lib/metrics";
import type { Building, Neighborhood } from "@/lib/types";
import MapControls from "./MapControls";
import { useTrackpad } from "@/lib/useTrackpad";
import { FLY, focusOutline, frameGeometry } from "@/lib/focus";

const CAMERA_TRANSITION = new LinearInterpolator(["bearing", "pitch"]);

// Matte plaster relief: soft ambient plus one light from the west/north-west, no gloss.
const lighting = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 252, 245], intensity: 0.9 }),
  sun: new DirectionalLight({ color: [255, 248, 236], intensity: 1.1, direction: [1, -1.2, -1.6] }),
});
const MATERIAL = { ambient: 0.6, diffuse: 0.5, shininess: 0, specularColor: [0, 0, 0] as [number, number, number] };
const BUILDING_ZOOM = 12.6; // above this, one column per building
const HEX_RADIUS_M = 220; // small enough that the East River and Harlem River stay visible
const MOBILE_HEX_RADIUS_M = 330;
const HEX_FILL = 0.82; // gap between hexes so the coastline and parks read through

export interface HoverInfo {
  building: number;
  x: number;
  y: number;
}

interface Props {
  buildings: Building[];
  hoods: Neighborhood[];
  land: GeoJSON.FeatureCollection;
  parks: GeoJSON.FeatureCollection | null;
  flat?: boolean; // mobile: pitch 0, no extrusion
  initialZoom?: number;
  onHover?: (h: HoverInfo | null) => void;
  onTap?: (building: number) => void;
  onOpen?: (building: number) => void; // desktop click: open the address page
}

export default function HeroMap({ buildings, hoods, land, parks, flat = false, initialZoom = 10.2, onHover, onTap, onOpen }: Props) {
  const { year, view, category, nta } = useAtlas();
  const ntaIdx = useMemo(() => (nta ? hoods.findIndex((h) => h.id === nta) : -1), [nta, hoods]);
  const focusHood = ntaIdx >= 0 ? hoods[ntaIdx] : null;
  const inFocus = useCallback((b: Building) => ntaIdx < 0 || b.nta === ntaIdx, [ntaIdx]);
  // Opens top-down and north-up like a street map (Bronx at the top, Brooklyn and Queens to the
  // right of Manhattan); the controls tilt into the 3D relief and rotate it.
  const [viewState, setViewState] = useState<MapViewState>({
    ...NYC_CENTER,
    zoom: initialZoom,
    pitch: 0,
    bearing: 0,
  });
  // Where the camera is heading. Button clicks build on this, not on the mid-animation camera,
  // so "3D" then "rotate" quickly doesn't cancel the tilt.
  const target = useRef({ bearing: 0, pitch: 0 });
  const [shownTarget, setShownTarget] = useState({ bearing: 0, pitch: 0 }); // mirror for rendering the controls
  const setTarget = (t: { bearing: number; pitch: number }) => {
    target.current = t;
    setShownTarget(t);
  };
  const animateTo = (next: { bearing?: number; pitch?: number }) => {
    setTarget({ ...target.current, ...next });
    setViewState((v) => ({ ...v, ...target.current, transitionDuration: 450, transitionInterpolator: CAMERA_TRANSITION }) as MapViewState);
  };
  const minZoom = initialZoom - 0.6; // can't zoom out past a little more than the whole city

  // Trackpad: pinch zooms; once the map is clicked, swipe pans and shift+swipe rotates/tilts.
  const box = useRef<HTMLDivElement>(null);
  const viewRef = useRef(viewState);
  useEffect(() => {
    viewRef.current = viewState;
  }, [viewState]);
  const getView = useCallback(() => viewRef.current, []);
  const setView = useCallback(
    (v: MapViewState) => {
      const next = clampView(v, minZoom);
      viewRef.current = next;
      target.current = { bearing: next.bearing ?? 0, pitch: next.pitch ?? 0 };
      setShownTarget(target.current);
      setViewState(next);
    },
    [minZoom],
  );
  const trackpad = useTrackpad({ el: box, getView, setView, enabled: !flat });

  // Measure the box ourselves and hand deck.gl the real size: left alone it measures the canvas
  // before layout (300x150) and draws the first frames stretched.
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  useEffect(() => {
    const node = box.current;
    if (!node) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      if (width > 0 && height > 0) setSize({ width: Math.round(width), height: Math.round(height) });
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, []);

  const palette = usePalette();
  // Boroughs are MultiPolygons; the land plate wants one ring set per polygon.
  const landPolys = useMemo(() => landPolygons(land), [land]);
  const onLand = useMemo(() => makeLandTest(landPolys), [landPolys]);
  const scale = useMemo(() => makeScale(buildings, view, hoods), [buildings, view, hoods]);
  const value = useMemo(() => (b: Building) => scale(rawValue(b, view, hoods)), [scale, view, hoods]);
  const showBuildings = !flat && viewState.zoom > BUILDING_ZOOM;
  const cells = useMemo<Cell[]>(
    () => (showBuildings ? [] : hexBins(buildings, flat ? MOBILE_HEX_RADIUS_M : HEX_RADIUS_M, value, year, category, palette, onLand, inFocus)),
    [buildings, value, year, category, palette, showBuildings, flat, onLand, inFocus],
  );

  // Tallest hexes (99th percentile) rise ~2.5 km, so the whole city reads as one relief.
  const hexScale = useMemo(() => {
    const h = cells.map((c) => c.height).sort((a, b) => a - b);
    return h.length ? 2500 / Math.max(1, h[Math.floor(0.99 * (h.length - 1))]) : 1;
  }, [cells]);


  // Fly to the chosen neighbourhood (or back out to the city when it's cleared).
  const lastNta = useRef<string | null>(null);
  useEffect(() => {
    if (!size || nta === lastNta.current) return;
    lastNta.current = nta;
    const to = focusHood
      ? frameGeometry(focusHood.geometry, size, viewRef.current)
      : { ...viewRef.current, ...NYC_CENTER, zoom: initialZoom };
    setViewState({ ...to, transitionDuration: "auto", transitionInterpolator: FLY } as MapViewState);
  }, [nta, focusHood, size, initialZoom]);

  const layers = [
    new SolidPolygonLayer<GeoJSON.Position[][]>({
      id: "land",
      data: landPolys,
      getPolygon: (p) => p as unknown as [number, number][][], // GeoJSON rings are number[] positions
      getFillColor: palette.land,
      _full3d: false,
    }),
    ...(parks ? [parksLayer("parks", parks, palette)] : []),
    outlineLayer("outline", landPolys, palette),
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
          getElevation: (b) => (hasCategory(b, category) && inFocus(b) ? b.tenants : b.tenants * 0.15),
          getFillColor: (b) => buildingColor(b, value(b), year, category, palette, inFocus(b)),
          material: MATERIAL,
          pickable: true,
          updateTriggers: { getFillColor: [year, view, category, ntaIdx, palette], getElevation: [category, ntaIdx] },
          transitions: { getFillColor: 300 },
        })
      : new ColumnLayer<Cell>({
          id: "hexes",
          data: cells,
          diskResolution: 6,
          radius: (flat ? MOBILE_HEX_RADIUS_M : HEX_RADIUS_M) * HEX_FILL,
          extruded: !flat,
          elevationScale: hexScale,
          getPosition: (c) => [c.lon, c.lat],
          getElevation: (c) => c.height,
          getFillColor: (c) => c.color,
          material: MATERIAL,
          pickable: true,
          transitions: { getFillColor: 300 },
        }),
    ...(focusHood ? [focusOutline(focusHood.geometry, palette)] : []),
    boroughLabels("boroughs", (viewState.pitch ?? 0) > 5 ? 2800 : 0, palette),
  ];

  return (
    <div ref={box} className="absolute inset-0" onPointerDown={trackpad.activate}>
    {size && <DeckGL
      width={size.width}
      height={size.height}
      viewState={viewState}
      onViewStateChange={({ viewState: v, interactionState }) => {
        const next = clampView(v as MapViewState, minZoom);
        // A drag or wheel (not an animation step) sets a new resting camera.
        if (!interactionState?.inTransition) setTarget({ bearing: next.bearing ?? 0, pitch: next.pitch ?? 0 });
        setViewState(next);
      }}
      // Wheel/pinch are handled by useTrackpad, so the page can still scroll past an inactive map.
      controller={flat ? { dragRotate: false, touchRotate: false } : { dragRotate: true, scrollZoom: false }}
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
        if (!o) return;
        const idx = "top" in o ? o.top : o.idx;
        if (onTap) onTap(idx);
        else onOpen?.(idx);
      }}
    />}
    {!flat && <MapControls bearing={viewState.bearing ?? 0} pitch={shownTarget.pitch} targetBearing={shownTarget.bearing} onChange={animateTo} />}
    {!flat && (
      <div className="label pointer-events-none absolute bottom-4 left-1/2 z-10 -translate-x-1/2 border border-rule bg-paper-raised/90 px-2.5 py-1.5">
        {trackpad.active
          ? "Swipe to pan · pinch to zoom · shift+swipe to rotate and tilt"
          : "Click the map to explore with your trackpad · pinch to zoom"}
      </div>
    )}
    </div>
  );
}
