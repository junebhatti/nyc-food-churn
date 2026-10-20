import type { Metadata } from "next";

export const SITE_NAME = "NYC Turnover";
export const SITE_URL = "https://half-life-nyc.vercel.app";

export const HOME = {
  title: "NYC Turnover — an atlas of restaurant churn",
  description:
    "Every NYC restaurant, bar, café, bakery and bodega since 2012: which storefronts can't keep a tenant, how long places last, and whether the rent is worth the risk.",
};

/**
 * Title, description and share tags for one page. Next merges metadata shallowly, so a page that
 * only set `title` would share with the site's og:title; this keeps all three in step.
 */
export function pageMeta(title: string, description: string, path: string): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { title, description, url: path, siteName: SITE_NAME, type: "website", locale: "en_US" },
    twitter: { card: "summary_large_image", title, description },
  };
}
