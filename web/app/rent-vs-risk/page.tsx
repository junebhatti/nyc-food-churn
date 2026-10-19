import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import RentVsRisk from "@/components/risk/RentVsRisk";

export const metadata: Metadata = { title: "Rent vs risk — Half-Life" };

export default function Page() {
  return (
    <StoryPage slug="rent-vs-risk">
      <RentVsRisk />
    </StoryPage>
  );
}
