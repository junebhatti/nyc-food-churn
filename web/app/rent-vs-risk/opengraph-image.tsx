import { card, OG_SIZE } from "../_og/card";
import { STORY_SHARE } from "../_og/stories";

const s = STORY_SHARE["rent-vs-risk"];
export const alt = `${s.kicker}: ${s.headline}`;
export const size = OG_SIZE;
export const contentType = "image/png";

export default function Image() {
  return card(s);
}
