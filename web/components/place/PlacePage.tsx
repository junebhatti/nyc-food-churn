"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowUpRight } from "@phosphor-icons/react";
import { fetchPlace, placeHref } from "@/lib/places";
import type { CursedTenant, Place } from "@/lib/types";
import TimelineStrip from "../cursed/Timeline";
import TopBar from "../TopBar";
import BusinessCard from "./BusinessCard";

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export default function PlacePage() {
  const { id } = useParams<{ id: string }>();
  // Results are tagged with the id they belong to, so navigating between addresses shows
  // "Loading" for the new one instead of the previous address's data.
  const [loaded, setLoaded] = useState<{ id: string; place: Place | null; error: string | null } | null>(null);
  useEffect(() => {
    let alive = true;
    fetchPlace(id)
      .then((p) => alive && setLoaded({ id, place: p, error: null }))
      .catch((e: Error) => {
        console.error(e);
        if (alive) setLoaded({ id, place: null, error: e.message });
      });
    return () => {
      alive = false;
    };
  }, [id]);
  const current = loaded?.id === id ? loaded : null;
  const place = current ? current.place : undefined;
  const error = current?.error ?? null;

  return (
    <main className="min-h-svh">
      <TopBar />
      <div className="px-4 py-10 md:px-10">
        {error && <p className="label">Couldn&rsquo;t load this address: {error}</p>}
        {place === undefined && !error && <p className="label">Loading…</p>}
        {place === null && !error && <p className="label">No address with id “{id}”. <Link href="/" className="underline">Back to the map</Link></p>}
        {place && <PlaceView place={place} />}
      </div>
    </main>
  );
}

function PlaceView({ place: p }: { place: Place }) {
  const timeline: CursedTenant[] = [...p.businesses].reverse().filter((b) => b.open != null).map((b) => ({
    name: b.name, cuisine: b.cuisine, price: b.price, open: b.open as number, close: b.close, life: b.life, isOpen: b.isOpen,
  }));
  const open = p.businesses.filter((b) => b.isOpen).length;
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${p.address} ${p.boro ?? ""} NY ${p.zip ?? ""}`)}`;
  return (
    <>
      <Link href={p.nta ? `/?n=${p.nta}` : "/"} className="mono inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.06em] text-muted hover:text-ink">
        <ArrowLeft size={12} /> {p.ntaName ? `${p.ntaName} on the map` : "Back to the map"}
      </Link>
      <p className="kicker mt-6">Address · {p.ntaName ?? p.boro ?? "New York"}</p>
      <h1 className="mt-2 text-[40px] leading-[1.02] tracking-[-0.02em] md:text-[56px]">{p.address}</h1>
      <div className="mono mt-2 flex flex-wrap items-center gap-4 text-[12px] text-muted">
        <span>{[p.boro, p.zip].filter(Boolean).join(" · ")}</span>
        <a href={maps} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-ink underline-offset-2 hover:underline">
          Open in Google Maps <ArrowUpRight size={12} />
        </a>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-6 border-t border-ink pt-3 md:grid-cols-6">
        <Stat label="Businesses since 2012" value={String(p.tenants)} />
        <Stat label="Open now" value={String(open)} green={open > 0} />
        <Stat label="Median life here" value={p.medianLife != null ? `${p.medianLife.toFixed(1)}y` : "—"} red />
        <Stat label="Area 3-yr closure" value={pct(p.hood.closure3y)} />
        <Stat label="Area rent / sq ft / yr" value={p.hood.rent != null ? `$${Math.round(p.hood.rent)}` : "—"} />
        <Stat label="Area beta" value={p.hood.beta != null ? p.hood.beta.toFixed(2) : "—"} />
      </div>

      {timeline.length > 0 && (
        <section className="mt-10 border border-ink bg-paper-raised p-5 md:p-7">
          <div className="label mb-2">Every food and drink business at this address</div>
          <div className="overflow-x-auto"><div className="min-w-[640px]"><TimelineStrip timeline={timeline} /></div></div>
        </section>
      )}

      <section className="mt-10">
        <div className="label mb-3">Newest first</div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {p.businesses.map((b, i) => <BusinessCard key={`${b.name}-${i}`} b={b} address={p.address} boro={p.boro} />)}
        </div>
      </section>

      {p.nearby.length > 0 && (
        <section className="mt-12 border-t border-ink pt-4">
          <div className="label mb-2">Nearby addresses</div>
          <div className="grid gap-x-8 md:grid-cols-2">
            {p.nearby.map(([nid, addr, n, m]) => (
              <Link key={nid} href={placeHref(nid)} className="flex items-baseline justify-between border-b border-rule py-2 hover:bg-paper-raised">
                <span className="text-[16px]">{addr}</span>
                <span className="mono text-[11px] text-muted">{n} business{n === 1 ? "" : "es"} · {m} m</span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <p className="label mt-12 max-w-2xl leading-relaxed">
        Health grades are NYC DOHMH inspection results. Reviews live on Google and Yelp; we link to them rather than copying them.
        Closure dates are estimated to within about a season.
      </p>
    </>
  );
}

function Stat({ label, value, red = false, green = false }: { label: string; value: string; red?: boolean; green?: boolean }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mono tnum text-[24px] ${red ? "text-awning" : green ? "text-deli" : ""}`}>{value}</div>
    </div>
  );
}
