import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import { pageMeta } from "../_og/meta";
import { STORY_SHARE } from "../_og/stories";
import Covid from "@/components/sections/Covid";
import type { CovidData } from "@/lib/types";
import covidJson from "@/public/data/covid.json";

const s = STORY_SHARE["2020"];
export const metadata: Metadata = pageMeta(s.title, s.description, "/2020");

export default function Page() {
  return (
    <StoryPage slug="2020">
      <Covid data={covidJson as CovidData} />
    </StoryPage>
  );
}
