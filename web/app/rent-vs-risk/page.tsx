import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import { pageMeta } from "../_og/meta";
import { STORY_SHARE } from "../_og/stories";
import RentVsRisk from "@/components/risk/RentVsRisk";

const s = STORY_SHARE["rent-vs-risk"];
export const metadata: Metadata = pageMeta(s.title, s.description, "/rent-vs-risk");

export default function Page() {
  return (
    <StoryPage slug="rent-vs-risk">
      <RentVsRisk />
    </StoryPage>
  );
}
