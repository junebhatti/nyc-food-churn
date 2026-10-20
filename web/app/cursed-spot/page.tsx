import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import { pageMeta } from "../_og/meta";
import { STORY_SHARE } from "../_og/stories";
import CursedTest from "@/components/sections/CursedTest";
import type { CursedTestData, HalfLifeData } from "@/lib/types";
import cursedTestJson from "@/public/data/cursedtest.json";
import halflifeJson from "@/public/data/halflife.json";

const s = STORY_SHARE["cursed-spot"];
export const metadata: Metadata = pageMeta(s.title, s.description, "/cursed-spot");

export default function Page() {
  return (
    <StoryPage slug="cursed-spot">
      <CursedTest data={cursedTestJson as unknown as CursedTestData} grid={(halflifeJson as unknown as HalfLifeData).grid} />
    </StoryPage>
  );
}
