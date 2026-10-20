import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import { pageMeta } from "../_og/meta";
import { STORY_SHARE } from "../_og/stories";
import HalfLife from "@/components/sections/HalfLife";
import type { HalfLifeData } from "@/lib/types";
import halflifeJson from "@/public/data/halflife.json";

const s = STORY_SHARE["half-life"];
export const metadata: Metadata = pageMeta(s.title, s.description, "/half-life");

export default function Page() {
  return (
    <StoryPage slug="half-life">
      <HalfLife data={halflifeJson as unknown as HalfLifeData} />
    </StoryPage>
  );
}
