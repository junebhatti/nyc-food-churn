// The seven story pages, in reading order. The home page is the map on its own.

export interface Story {
  slug: string;
  num: string;
  label: string;
}

export const STORIES: Story[] = [
  { slug: "cursed", num: "01", label: "Cursed addresses" },
  { slug: "half-life", num: "02", label: "Half-life" },
  { slug: "rent-vs-risk", num: "03", label: "Rent vs risk" },
  { slug: "beta", num: "04", label: "Beta" },
  { slug: "cursed-spot", num: "05", label: "The cursed spot test" },
  { slug: "2020", num: "06", label: "The 2020 shock" },
];

export const storyHref = (slug: string) => `/${slug}`;

/** Neighbours in reading order, for the prev/next links at the foot of each story. */
export function neighbours(slug: string): { prev: Story | null; next: Story | null } {
  const i = STORIES.findIndex((s) => s.slug === slug);
  if (i === -1) throw new Error(`Unknown story "${slug}"`);
  return { prev: STORIES[i - 1] ?? null, next: STORIES[i + 1] ?? null };
}
