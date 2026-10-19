import Link from "next/link";
import SearchBox from "./search/SearchBox";
import StoriesMenu from "./StoriesMenu";

/** Header on every page: name, address search and the stories menu. */
export default function TopBar({ current }: { current?: string }) {
  return (
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-rule px-4 py-3 md:h-14 md:flex-nowrap md:px-10 md:py-0">
      <Link href="/" className="flex items-baseline gap-4">
        <span className="text-[22px] font-medium">NYC Turnover</span>
        <span className="label hidden lg:inline">An atlas of restaurant churn, 2012–2026</span>
      </Link>
      <div className="order-last w-full md:order-none md:ml-auto md:w-[300px]"><SearchBox compact /></div>
      <StoriesMenu current={current} />
    </header>
  );
}
