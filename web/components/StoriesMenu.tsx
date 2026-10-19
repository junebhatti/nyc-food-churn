"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CaretDown, List, X } from "@phosphor-icons/react";
import { STORIES, storyHref } from "@/lib/stories";

/** "Stories" dropdown in the header: the seven story pages, plus the map. ☰ on phones. */
export default function StoriesMenu({ current }: { current?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={box} className="relative">
      <button type="button" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(!open)}
        aria-label="Stories"
        className="mono flex h-11 items-center justify-center gap-1.5 text-[11px] uppercase tracking-[0.06em] max-md:w-11 md:h-9 md:border md:border-ink md:px-3 md:hover:bg-paper-raised">
        <span className="md:hidden">{open ? <X size={22} /> : <List size={22} />}</span>
        <span className="hidden md:inline">Stories</span>
        <CaretDown size={12} className="hidden md:inline" />
      </button>
      {open && (
        <nav className="absolute right-0 top-full z-50 mt-1 w-[300px] border border-ink bg-paper-raised">
          <Link href="/" onClick={() => setOpen(false)}
            className={`flex items-baseline gap-3 border-b border-rule px-4 py-3 hover:bg-paper ${current === "map" ? "bg-paper" : ""}`}>
            <span className="mono w-5 text-[11px] text-muted">00</span>
            <span className="text-[16px]">The map</span>
          </Link>
          {STORIES.map((s) => (
            <Link key={s.slug} href={storyHref(s.slug)} onClick={() => setOpen(false)}
              aria-current={current === s.slug ? "page" : undefined}
              className={`flex items-baseline gap-3 border-b border-rule px-4 py-3 last:border-b-0 hover:bg-paper ${current === s.slug ? "bg-paper shadow-[inset_3px_0_0_var(--awning)]" : ""}`}>
              <span className="mono w-5 text-[11px] text-awning">{s.num}</span>
              <span className="text-[16px]">{s.label}</span>
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}
