import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import { IBM_Plex_Mono, Newsreader } from "next/font/google";
import "./globals.css";
import { HOME, SITE_NAME, SITE_URL } from "./_og/meta";
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
  metadataBase: new URL(SITE_URL),
  ...HOME,
  openGraph: { title: HOME.title, description: HOME.description, siteName: SITE_NAME, type: "website", locale: "en_US" },
  twitter: { card: "summary_large_image", title: HOME.title, description: HOME.description },
};

export const viewport: Viewport = { themeColor: [
  { media: "(prefers-color-scheme: light)", color: "#F3EEE4" },
  { media: "(prefers-color-scheme: dark)", color: "#161826" },
] };

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
