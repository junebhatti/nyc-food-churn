import { card, OG_SIZE } from "./_og/card";

export const alt = "NYC Turnover: every NYC restaurant, bar, café, bakery and bodega since 2012, and how long they lasted.";
export const size = OG_SIZE;
export const contentType = "image/png";

export default function Image() {
  return card({
    kicker: "The map · five boroughs",
    headline: "Every NYC restaurant, bar, café, bakery and bodega since 2012, and how long it lasted.",
    size: 72,
  });
}
