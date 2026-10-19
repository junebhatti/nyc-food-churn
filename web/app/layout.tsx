import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { IBM_Plex_Mono, Newsreader } from "next/font/google";
import "./globals.css";
import AskPanel from "@/components/ask/AskPanel";

const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-newsreader",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
});

export const metadata: Metadata = {
  title: "Half-Life — an atlas of NYC restaurant churn",
  description:
    "Every NYC restaurant, bar, café, bakery and bodega since 2012: which storefronts can't keep a tenant, how long places last, and whether the rent is worth the risk.",
};

export const viewport: Viewport = { themeColor: "#F3EEE4" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${newsreader.variable} ${plexMono.variable}`}>
      <body>
        {children}
        {/* reads the URL, so it needs its own Suspense boundary under Cache Components */}
        <Suspense fallback={null}>
          <AskPanel />
        </Suspense>
      </body>
    </html>
  );
}
