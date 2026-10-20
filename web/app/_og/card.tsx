import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

// Share images in the site's light look (app/globals.css). Static TTFs because the image renderer
// can't read woff2 or variable fonts; both families are OFL.
export const OG_SIZE = { width: 1200, height: 630 };
export const C = { paper: "#f3eee4", ink: "#1c1b18", muted: "#5a554c", rule: "#cfc6b6", awning: "#b8321d" };

const font = (file: string) => readFile(join(process.cwd(), "app/_og/fonts", file));
const fonts = Promise.all([font("Newsreader-Regular.ttf"), font("Newsreader-Medium.ttf"), font("IBMPlexMono-Medium.ttf")]);

/** Kicker, headline and the masthead strip; `children` sits between the headline and the strip. */
export async function card({ kicker, headline, size = 76, children }: {
  kicker: string;
  headline: string;
  size?: number;
  children?: React.ReactNode;
}) {
  const [regular, medium, mono] = await fonts;
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: C.paper, color: C.ink, padding: "64px 72px 48px", fontFamily: "Newsreader" }}>
        <div style={{ display: "flex", fontFamily: "Plex Mono", fontSize: 24, letterSpacing: 2, textTransform: "uppercase", color: C.awning }}>{kicker}</div>
        <div style={{ display: "flex", marginTop: 28, fontSize: size, fontWeight: 500, lineHeight: 1.04, letterSpacing: -1.5 }}>{headline}</div>
        <div style={{ display: "flex", flexDirection: "column", flexGrow: 1, justifyContent: "flex-end" }}>{children}</div>
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 36, paddingTop: 20, borderTop: `3px solid ${C.ink}`, fontFamily: "Plex Mono", fontSize: 22, letterSpacing: 2, textTransform: "uppercase" }}>
          <span>NYC Turnover</span>
          <span style={{ color: C.muted }}>An atlas of restaurant churn</span>
        </div>
      </div>
    ),
    {
      ...OG_SIZE,
      fonts: [
        { name: "Newsreader", data: regular, weight: 400, style: "normal" },
        { name: "Newsreader", data: medium, weight: 500, style: "normal" },
        { name: "Plex Mono", data: mono, weight: 500, style: "normal" },
      ],
    },
  );
}
