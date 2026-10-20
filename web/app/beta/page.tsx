import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import { pageMeta } from "../_og/meta";
import { STORY_SHARE } from "../_og/stories";
import Beta from "@/components/sections/Beta";
import type { BetaData } from "@/lib/types";
import betaJson from "@/public/data/beta.json";

const s = STORY_SHARE["beta"];
export const metadata: Metadata = pageMeta(s.title, s.description, "/beta");

export default function Page() {
  return (
    <StoryPage slug="beta">
      <Beta data={betaJson as unknown as BetaData} />
    </StoryPage>
  );
}
