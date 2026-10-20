import type { Metadata } from "next";
import StoryPage from "@/components/StoryPage";
import { pageMeta } from "../_og/meta";
import { STORY_SHARE } from "../_og/stories";
import CursedAddresses from "@/components/cursed/CursedAddresses";
import type { CursedAddress } from "@/lib/types";
import cursedJson from "@/public/data/cursed.json";

const s = STORY_SHARE["cursed"];
export const metadata: Metadata = pageMeta(s.title, s.description, "/cursed");

export default function Page() {
  return (
    <StoryPage slug="cursed">
      <CursedAddresses addresses={cursedJson as CursedAddress[]} />
    </StoryPage>
  );
}
