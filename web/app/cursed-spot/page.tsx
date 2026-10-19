import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import CursedTest from "@/components/sections/CursedTest";
import type { CursedTestData, HalfLifeData } from "@/lib/types";
import cursedTestJson from "@/public/data/cursedtest.json";
import halflifeJson from "@/public/data/halflife.json";

export const metadata: Metadata = { title: "The cursed spot test — Half-Life" };

export default function Page() {
  return (
    <StoryPage slug="cursed-spot">
      <CursedTest data={cursedTestJson as unknown as CursedTestData} grid={(halflifeJson as unknown as HalfLifeData).grid} />
    </StoryPage>
  );
}
