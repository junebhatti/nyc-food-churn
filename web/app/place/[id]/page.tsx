import { Suspense } from "react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PlacePage from "@/components/place/PlacePage";
import cursedJson from "@/public/data/cursed.json";
import { pageMeta } from "../../_og/meta";
import { describe, getPlace } from "./data";

type Props = { params: Promise<{ id: string }> };

// Cache Components needs at least one prerendered param; prerender the 50 cursed addresses and
// serve the same client shell for every other address (its data loads from /data/places/).
export function generateStaticParams() {
  return (cursedJson as { id: string }[]).map((c) => ({ id: c.id }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const place = await getPlace(id);
  if (!place) notFound();
  return pageMeta(`${place.address} — NYC Turnover`, describe(place), `/place/${id}`);
}

// Checking the id before the Suspense boundary lets an unknown address send a real 404 status
// instead of a 200 that streams the not-found page.
export default async function Page({ params }: Props) {
  const { id } = await params;
  if (!(await getPlace(id))) notFound();
  return (
    <Suspense fallback={<p className="label p-10">Loading…</p>}>
      <PlacePage />
    </Suspense>
  );
}
