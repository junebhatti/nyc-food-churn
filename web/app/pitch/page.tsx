import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import Pitch from "@/components/sections/Pitch";
import type { HalfLifeData, PitchData } from "@/lib/types";
import halflifeJson from "@/public/data/halflife.json";
import pitchJson from "@/public/data/pitch.json";

export const metadata: Metadata = { title: "Pitch yours — NYC Turnover" };

export default function Page() {
  return (
    <StoryPage slug="pitch">
      <Pitch data={pitchJson as unknown as PitchData} city={(halflifeJson as unknown as HalfLifeData).groups.all.rows[0]} />
    </StoryPage>
  );
}
