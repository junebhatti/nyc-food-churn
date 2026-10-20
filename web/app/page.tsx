import type { Metadata } from "next";
import Hero from "@/components/hero/Hero";
import NeighborhoodPanel from "@/components/hero/NeighborhoodPanel";
import Footer from "@/components/Footer";
import type { Summary, Yearly } from "@/lib/types";
// Small files are bundled at build time (written by pipeline/export_site.py); the big map files
// load in the browser. The stories live on their own pages (lib/stories.ts).
import summaryJson from "@/public/data/summary.json";
import yearlyJson from "@/public/data/yearly.json";
import { HOME, pageMeta } from "./_og/meta";

export const metadata: Metadata = pageMeta(HOME.title, HOME.description, "/");

const summary = summaryJson as Summary;
const yearly = yearlyJson as unknown as Yearly;

export default function Page() {
  return (
    <main>
      <Hero summary={summary} yearly={yearly} />
      <NeighborhoodPanel />
      <Footer />
    </main>
  );
}
