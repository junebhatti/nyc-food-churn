import Hero from "@/components/hero/Hero";
import CursedAddresses from "@/components/cursed/CursedAddresses";
import RentVsRisk from "@/components/risk/RentVsRisk";
import HalfLife from "@/components/sections/HalfLife";
import Beta from "@/components/sections/Beta";
import CursedTest from "@/components/sections/CursedTest";
import Covid from "@/components/sections/Covid";
import Pitch from "@/components/sections/Pitch";
import NeighborhoodPanel from "@/components/hero/NeighborhoodPanel";
import type { BetaData, CovidData, CursedAddress, CursedTestData, HalfLifeData, PitchData, Summary, Yearly } from "@/lib/types";
// Small files are bundled at build time (written by pipeline/export_site.py and export_analysis.py);
// the big map files load in the browser.
import summaryJson from "@/public/data/summary.json";
import yearlyJson from "@/public/data/yearly.json";
import cursedJson from "@/public/data/cursed.json";
import halflifeJson from "@/public/data/halflife.json";
import cursedTestJson from "@/public/data/cursedtest.json";
import betaJson from "@/public/data/beta.json";
import covidJson from "@/public/data/covid.json";
import pitchJson from "@/public/data/pitch.json";

const summary = summaryJson as Summary;
const yearly = yearlyJson as unknown as Yearly;
const cursed = cursedJson as CursedAddress[];
const halflife = halflifeJson as unknown as HalfLifeData;
const cursedTest = cursedTestJson as unknown as CursedTestData;
const beta = betaJson as unknown as BetaData;
const covid = covidJson as CovidData;
const pitch = pitchJson as unknown as PitchData;

export default function Page() {
  return (
    <main>
      <Hero summary={summary} yearly={yearly} />
      <NeighborhoodPanel />
      <CursedAddresses addresses={cursed} />
      <HalfLife data={halflife} />
      <RentVsRisk />
      <Beta data={beta} />
      <CursedTest data={cursedTest} grid={halflife.grid} />
      <Covid data={covid} />
      <Pitch data={pitch} city={halflife.groups.all.rows[0]} />
      <footer className="border-t border-ink px-4 py-10 md:px-10">
        <p className="label max-w-3xl leading-relaxed">
          Sources: NYC DOHMH restaurant inspections (about 75 archived copies, 2012–2026), NY State Liquor Authority licences, USDA SNAP
          retailers, NYC storefront registry rents (LL157), NYC Planning boundaries, MTA, TLC and Census data for foot traffic, and
          Census Business Dynamics for validation. A place counts as closed when it leaves the inspection data; closure dates are
          estimated to within about a season. Built by Junaid Bhatti.
        </p>
      </footer>
    </main>
  );
}
