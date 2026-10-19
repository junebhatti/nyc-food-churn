import Link from "next/link";
import SearchBox from "./search/SearchBox";

/** Header used on the address pages (the home page header lives in Hero). */
export default function TopBar() {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-4 py-3 md:h-14 md:px-10 md:py-0">
      <Link href="/" className="flex items-baseline gap-4">
        <span className="text-[22px] font-medium">Half-Life</span>
        <span className="label hidden md:inline">An atlas of NYC restaurant churn, 2012–2026</span>
      </Link>
      <div className="w-full md:w-auto"><SearchBox compact /></div>
    </header>
  );
}
