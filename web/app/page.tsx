import Hero from "@/components/hero/Hero";
import CursedAddresses from "@/components/cursed/CursedAddresses";
import RentVsRisk from "@/components/risk/RentVsRisk";
import type { CursedAddress, Summary, Yearly } from "@/lib/types";
// Small files are bundled at build time (written by pipeline/export_site.py); the big map files load in the browser.
import summaryJson from "@/public/data/summary.json";
import yearlyJson from "@/public/data/yearly.json";
import cursedJson from "@/public/data/cursed.json";

const summary = summaryJson as Summary;
const yearly = yearlyJson as unknown as Yearly;
const cursed = cursedJson as CursedAddress[];

export default function Page() {
  return (
    <main>
      <Hero summary={summary} yearly={yearly} />
      <CursedAddresses addresses={cursed} />
      <RentVsRisk />
      <footer className="border-t border-ink px-4 py-10 md:px-10">
        <p className="label max-w-3xl leading-relaxed">
          Sources: NYC DOHMH restaurant inspections (about 75 archived copies, 2012–2026), NY State Liquor Authority licences, USDA SNAP
          retailers, NYC storefront registry rents (LL157), and NYC Planning boundaries. A place counts as closed when it leaves the
          inspection data; closure dates are estimated to within about a season. Built by Junaid Bhatti.
        </p>
      </footer>
    </main>
  );
}
