import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import HalfLife from "@/components/sections/HalfLife";
import type { HalfLifeData } from "@/lib/types";
import halflifeJson from "@/public/data/halflife.json";

export const metadata: Metadata = { title: "Half-life — Half-Life" };

export default function Page() {
  return (
    <StoryPage slug="half-life">
      <HalfLife data={halflifeJson as unknown as HalfLifeData} />
    </StoryPage>
  );
}
