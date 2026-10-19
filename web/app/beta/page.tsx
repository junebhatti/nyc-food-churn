import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import Beta from "@/components/sections/Beta";
import type { BetaData } from "@/lib/types";
import betaJson from "@/public/data/beta.json";

export const metadata: Metadata = { title: "Beta — Half-Life" };

export default function Page() {
  return (
    <StoryPage slug="beta">
      <Beta data={betaJson as unknown as BetaData} />
    </StoryPage>
  );
}
