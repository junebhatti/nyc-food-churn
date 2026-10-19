import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import CursedAddresses from "@/components/cursed/CursedAddresses";
import type { CursedAddress } from "@/lib/types";
import cursedJson from "@/public/data/cursed.json";

export const metadata: Metadata = { title: "Cursed addresses — NYC Turnover" };

export default function Page() {
  return (
    <StoryPage slug="cursed">
      <CursedAddresses addresses={cursedJson as CursedAddress[]} />
    </StoryPage>
  );
}
