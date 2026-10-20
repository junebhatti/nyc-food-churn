import { card, C, OG_SIZE } from "../../_og/card";
import { getPlace } from "./data";

export const alt = "An NYC address and every food and drink business there since 2012";
export const size = OG_SIZE;
export const contentType = "image/png";

const START = 2012;
const WIDTH = OG_SIZE.width - 144;
const HEIGHT = 120;

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await getPlace(id);
  if (!p) return new Response("Not found", { status: 404 });

  // One lane per tenant, oldest at the top. Closed places with no close date end at open + life.
  const bars = [...p.businesses].reverse().flatMap((b) =>
    b.open == null ? [] : [{ open: b.open, end: b.isOpen ? null : (b.close ?? b.open + b.life), isOpen: b.isOpen }],
  );
  const end = Math.max(2026, ...bars.map((b) => b.end ?? b.open));
  const x = (t: number) => ((Math.max(t, START) - START) / (end - START)) * WIDTH;
  const lane = HEIGHT / Math.max(bars.length, 1);

  return card({
    kicker: [p.ntaName, p.boro].filter(Boolean).join(", ") || "New York City",
    headline: p.address,
    size: p.address.length > 28 ? 72 : 88,
    children: (
      <div style={{ display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", gap: 48, fontSize: 34, marginBottom: 24 }}>
          <span>{`${p.tenants} business${p.tenants === 1 ? "" : "es"} since 2012`}</span>
          {p.medianLife != null && <span style={{ color: C.muted }}>{`median life ${p.medianLife.toFixed(1)} yrs`}</span>}
        </div>
        <div style={{ display: "flex", position: "relative", width: WIDTH, height: HEIGHT, borderBottom: `1px solid ${C.rule}` }}>
          {bars.map((b, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                left: x(b.open),
                top: i * lane + lane * 0.15,
                width: Math.max(x(b.end ?? end) - x(b.open), 3),
                height: Math.max(lane * 0.7, 2),
                background: b.isOpen ? C.awning : C.ink,
              }}
            />
          ))}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontFamily: "Plex Mono", fontSize: 18, color: C.muted }}>
          <span>{START}</span>
          <span>{Math.floor(end)}</span>
        </div>
      </div>
    ),
  });
}
