"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChatCircleText, PaperPlaneRight, X } from "@phosphor-icons/react";
import { fetchPlace } from "@/lib/places";

const SUGGESTIONS = [
  "What does “beta” mean here?",
  "How do you know when a restaurant closed?",
  "Why would a storefront be cursed?",
  "Is rent the reason places close?",
];

interface Turn {
  q: string;
  a?: string;
  error?: string;
}

/** On an address page, a compact summary of what the visitor is looking at. */
async function pageContext(path: string): Promise<string | undefined> {
  const m = path.match(/^\/place\/([^/]+)/);
  if (!m) return undefined;
  const p = await fetchPlace(decodeURIComponent(m[1]));
  if (!p) return undefined;
  const lines = p.businesses.slice(0, 12).map((b) =>
    `${b.name} (${b.cuisine}; ${b.isOpen ? `open since ${Math.floor(b.open ?? 0)}` : `${Math.floor(b.open ?? 0)}-${Math.floor(b.close ?? 0)}`}${b.inspections?.grade ? `; grade ${b.inspections.grade}` : ""})`);
  return [`Address page: ${p.address}, ${p.ntaName ?? p.boro ?? ""}`,
    `${p.tenants} businesses since 2012; median life here ${p.medianLife ?? "n/a"} years; area 3-yr closure odds ${p.hood.closure3y != null ? Math.round(p.hood.closure3y * 100) + "%" : "n/a"}; area rent ${p.hood.rent != null ? "$" + Math.round(p.hood.rent) + "/sq ft/yr" : "n/a"}; area beta ${p.hood.beta ?? "n/a"}`,
    `Businesses (newest first): ${lines.join("; ")}`].join("\n").slice(0, 1500);
}

/** A side tab that opens a small "ask about the data" panel. */
export default function AskPanel() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  const ask = async (question: string) => {
    const text = question.trim();
    if (text.length < 3 || busy) return;
    setQ("");
    setBusy(true);
    setTurns((t) => [...t, { q: text }]);
    let result: Turn = { q: text };
    try {
      const context = await pageContext(path).catch((e) => {
        console.error("ask: page context failed", e);
        return undefined;
      });
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: text, context }),
      });
      const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      result = res.ok && body.answer ? { q: text, a: body.answer } : { q: text, error: body.error ?? `HTTP ${res.status}` };
    } catch (e) {
      console.error("ask: request failed", e);
      result = { q: text, error: "Couldn't reach the server." };
    }
    setTurns((t) => [...t.slice(0, -1), result]);
    setBusy(false);
  };

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} aria-label="Ask about the data"
        className="mono fixed right-0 top-1/2 z-40 flex -translate-y-1/2 items-center gap-1.5 border border-r-0 border-ink bg-paper-raised px-2 py-3 text-[11px] uppercase tracking-[0.06em] [writing-mode:vertical-rl] hover:bg-paper">
        <ChatCircleText size={14} className="rotate-90" /> Ask about the data
      </button>
    );
  }

  return (
    <aside role="dialog" aria-label="Ask about the data"
      className="fixed inset-x-0 bottom-0 z-50 flex max-h-[75svh] flex-col border-t border-ink bg-paper-raised md:inset-x-auto md:bottom-auto md:right-0 md:top-0 md:h-svh md:max-h-none md:w-[380px] md:border-l md:border-t-0">
      <div className="flex items-center justify-between border-b border-rule px-4 py-3">
        <div>
          <div className="kicker">Ask about the data</div>
          <div className="label mt-0.5">Answers come from Claude, grounded in how this site was built</div>
        </div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="flex h-9 w-9 items-center justify-center border border-ink"><X size={14} /></button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {turns.length === 0 && (
          <div className="space-y-2">
            <p className="text-[15px] text-ink-2">What the numbers mean, how closures were measured, or what a chart is showing.</p>
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" onClick={() => ask(s)} className="block w-full border border-rule px-3 py-2 text-left text-[14px] hover:bg-paper">{s}</button>
            ))}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className="mb-4">
            <p className="mono text-[12px] text-muted">{t.q}</p>
            {t.a && <p className="mt-1.5 whitespace-pre-line text-[15px] leading-relaxed">{t.a}</p>}
            {t.error && <p className="mt-1.5 text-[14px] text-awning">{t.error}</p>}
            {!t.a && !t.error && <p className="label mt-1.5">Thinking…</p>}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form className="flex border-t border-ink" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} placeholder="Ask a question…" aria-label="Your question"
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-[15px] outline-none" />
        <button type="submit" disabled={busy || q.trim().length < 3} aria-label="Send" className="flex w-12 items-center justify-center border-l border-ink disabled:opacity-40">
          <PaperPlaneRight size={16} />
        </button>
      </form>
    </aside>
  );
}
