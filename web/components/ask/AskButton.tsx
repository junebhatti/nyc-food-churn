"use client";

import { ChatCircleText } from "@phosphor-icons/react";

/** Event the header button sends; AskPanel (mounted once in the root layout) listens for it. */
export const OPEN_ASK = "ask:open";

/** "Ask" button in the header: opens the ask-about-the-data panel. Icon only on phones. */
export default function AskButton() {
  return (
    <button type="button" onClick={() => window.dispatchEvent(new Event(OPEN_ASK))} aria-label="Ask about the data"
      className="mono flex h-11 items-center justify-center gap-1.5 text-[11px] uppercase tracking-[0.06em] max-md:w-11 md:h-9 md:border md:border-ink md:px-3 md:hover:bg-paper-raised">
      <ChatCircleText size={16} className="max-md:h-[22px] max-md:w-[22px]" />
      <span className="hidden md:inline">Ask</span>
    </button>
  );
}
