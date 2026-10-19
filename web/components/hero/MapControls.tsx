"use client";

import { ArrowClockwise, ArrowCounterClockwise, CaretDown, CaretUp, NavigationArrow } from "@phosphor-icons/react";

export const TILT_3D = 50;
const ROTATE_STEP = 22.5;
const TILT_STEP = 15;
const MAX_PITCH = 60;

interface Props {
  bearing: number; // current, for the compass needle
  targetBearing: number; // where the camera is heading, for the rotate buttons
  pitch: number; // target pitch
  /** Animate the camera to a new bearing/pitch. */
  onChange: (next: { bearing?: number; pitch?: number }) => void;
}

const btn = "flex h-9 w-9 items-center justify-center border-ink bg-paper-raised hover:bg-paper";

/** Map-style camera controls: rotate, tilt, 2D/3D, and a compass that resets to north-up. */
export default function MapControls({ bearing, targetBearing, pitch, onChange }: Props) {
  const is3d = pitch > 5;
  return (
    <div className="pointer-events-auto absolute bottom-4 right-4 z-10 flex flex-col items-end gap-2">
      <button
        type="button"
        onClick={() => onChange({ bearing: 0, pitch: 0 })}
        aria-label="Reset to north-up"
        title="North up"
        className="flex h-11 w-11 items-center justify-center border border-ink bg-paper-raised hover:bg-paper"
      >
        {/* The arrow points north on screen, turning as the map rotates. */}
        <span className="flex flex-col items-center" style={{ transform: `rotate(${-bearing}deg)` }}>
          <NavigationArrow size={16} weight="fill" className="rotate-45 text-awning" />
          <span className="mono -mt-0.5 text-[8px]">N</span>
        </span>
      </button>
      <div className="flex border border-ink">
        <button type="button" className={btn} onClick={() => onChange({ bearing: targetBearing - ROTATE_STEP })} aria-label="Rotate left" title="Rotate left">
          <ArrowCounterClockwise size={16} />
        </button>
        <button type="button" className={`${btn} border-l`} onClick={() => onChange({ bearing: targetBearing + ROTATE_STEP })} aria-label="Rotate right" title="Rotate right">
          <ArrowClockwise size={16} />
        </button>
      </div>
      <div className="flex border border-ink">
        <button type="button" className={btn} onClick={() => onChange({ pitch: Math.min(MAX_PITCH, pitch + TILT_STEP) })} aria-label="Tilt up" title="Tilt">
          <CaretUp size={16} />
        </button>
        <button type="button" className={`${btn} border-l`} onClick={() => onChange({ pitch: Math.max(0, pitch - TILT_STEP) })} aria-label="Tilt down" title="Flatten">
          <CaretDown size={16} />
        </button>
      </div>
      <button
        type="button"
        onClick={() => onChange({ pitch: is3d ? 0 : TILT_3D })}
        aria-pressed={is3d}
        className={`mono h-9 w-[74px] border border-ink text-[11px] uppercase tracking-[0.06em] ${is3d ? "bg-ink text-paper" : "bg-paper-raised hover:bg-paper"}`}
      >
        {is3d ? "3D" : "2D"} view
      </button>
      <span className="label hidden text-right md:block">Right-drag to rotate</span>
    </div>
  );
}
