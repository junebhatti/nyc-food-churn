import { Suspense } from "react";
import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";
import PlacePage from "@/components/place/PlacePage";
import cursedJson from "@/public/data/cursed.json";
import { pageMeta } from "../../_og/meta";
import { describe, getAlias, getPlace } from "./data";

type Props = { params: Promise<{ id: string }> };

/** An id that isn't an address: send old (renamed) ids to their new page, else 404. */
async function missing(id: string): Promise<never> {
  const to = await getAlias(id);
  if (to) permanentRedirect(`/place/${to}`);
  notFound();
}

// Cache Components needs at least one prerendered param; prerender the 50 cursed addresses and
// serve the same client shell for every other address (its data loads from /data/places/).
export function generateStaticParams() {
  return (cursedJson as { id: string }[]).map((c) => ({ id: c.id }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const place = await getPlace(id);
  if (!place) return missing(id);
  return pageMeta(`${place.address} — NYC Turnover`, describe(place), `/place/${id}`);
}

// An unknown id renders the not-found page (see the note on Page below).
// The id is read before the Suspense boundary on purpose: it lets renamed ids answer with a real 308 and
// unknown ids with a 404. Next's dev overlay warns that this can slow navigation; correct status codes matter
// more here (old shared links, crawlers).
export default async function Page({ params }: Props) {
  const { id } = await params;
  if (!(await getPlace(id))) return missing(id);
  return (
    <Suspense fallback={<p className="label p-10">Loading…</p>}>
      <PlacePage />
    </Suspense>
  );
}
