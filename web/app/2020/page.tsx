import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import Covid from "@/components/sections/Covid";
import type { CovidData } from "@/lib/types";
import covidJson from "@/public/data/covid.json";

export const metadata: Metadata = { title: "The 2020 shock — NYC Turnover" };

export default function Page() {
  return (
    <StoryPage slug="2020">
      <Covid data={covidJson as CovidData} />
    </StoryPage>
  );
}
