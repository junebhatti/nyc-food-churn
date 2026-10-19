import { Suspense } from "react";
import type { Metadata } from "next";
import PlacePage from "@/components/place/PlacePage";
import cursedJson from "@/public/data/cursed.json";

// Cache Components needs at least one prerendered param; prerender the 50 cursed addresses and
// serve the same client shell for every other address (its data loads from /data/places/).
export function generateStaticParams() {
  return (cursedJson as { id: string }[]).map((c) => ({ id: c.id }));
}

export const metadata: Metadata = {
  title: "Address — NYC Turnover",
  description: "Every food and drink business at one NYC address since 2012: lifespans, health grades, acclaim and links.",
};

export default function Page() {
  return (
    <Suspense fallback={<p className="label p-10">Loading…</p>}>
      <PlacePage />
    </Suspense>
  );
}
