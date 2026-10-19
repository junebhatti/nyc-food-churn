import Link from "next/link";
import { ArrowLeft, ArrowRight } from "@phosphor-icons/react/dist/ssr";
import { neighbours, storyHref } from "@/lib/stories";
import TopBar from "./TopBar";
import Footer from "./Footer";

/** Frame for one story page: header, the section, then links to the previous and next stories. */
export default function StoryPage({ slug, children }: { slug: string; children: React.ReactNode }) {
  const { prev, next } = neighbours(slug);
  return (
    <>
      <TopBar current={slug} />
      {/* The header's rule already sits above the section, so drop the section's own top rule. */}
      <main className="[&>section]:border-t-0">{children}</main>
      <nav aria-label="More stories" className="grid border-t border-ink md:grid-cols-2">
        <Link href={prev ? storyHref(prev.slug) : "/"} className="group flex flex-col gap-1 px-4 py-6 hover:bg-paper-raised md:px-10">
          <span className="label flex items-center gap-1.5"><ArrowLeft size={12} /> {prev ? `${prev.num} · Previous` : "Back to"}</span>
          <span className="text-[22px]">{prev ? prev.label : "The map"}</span>
        </Link>
        {next && (
          <Link href={storyHref(next.slug)} className="group flex flex-col items-end gap-1 border-t border-rule px-4 py-6 text-right hover:bg-paper-raised md:border-l md:border-t-0 md:border-ink md:px-10">
            <span className="label flex items-center gap-1.5">{next.num} · Next <ArrowRight size={12} /></span>
            <span className="text-[22px]">{next.label}</span>
          </Link>
        )}
      </nav>
      <Footer />
    </>
  );
}
