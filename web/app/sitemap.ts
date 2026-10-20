import type { MetadataRoute } from "next";
import { STORIES, storyHref } from "@/lib/stories";
import cursedJson from "@/public/data/cursed.json";
import { SITE_URL } from "./_og/meta";

// Home, the stories, and the 50 cursed addresses (the prerendered ones). The other ~45k address
// pages are reachable from search and the map, so they stay out.
export default function sitemap(): MetadataRoute.Sitemap {
  const paths = ["/", ...STORIES.map((s) => storyHref(s.slug)), ...(cursedJson as { id: string }[]).map((c) => `/place/${c.id}`)];
  return paths.map((p) => ({ url: `${SITE_URL}${p}` }));
}
