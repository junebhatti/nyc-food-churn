/** Shared section frame: ink top rule, kicker, H2 and prose, matching Cursed addresses and Rent vs risk. */
export default function Section({
  id,
  kicker,
  title,
  children,
  intro,
}: {
  id: string;
  kicker: string;
  title: React.ReactNode;
  intro?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="border-t border-ink px-4 py-14 md:px-10">
      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <p className="kicker">{kicker}</p>
          <h1 className="mt-3 text-[34px] leading-[1.04] tracking-[-0.015em] md:text-[42px]">{title}</h1>
        </div>
        {intro && <div className="prose-hl self-end">{intro}</div>}
      </div>
      <div className="mt-10">{children}</div>
    </section>
  );
}

export function Stat({ label, value, tone }: { label: string; value: string; tone?: "red" | "green" | "muted" }) {
  const c = tone === "red" ? "text-awning" : tone === "green" ? "text-deli" : tone === "muted" ? "text-muted" : "";
  return (
    <div>
      <div className="label">{label}</div>
      <div className={`mono tnum text-[26px] leading-tight ${c}`}>{value}</div>
    </div>
  );
}

export const pct = (v: number) => `${Math.round(v * 100)}%`;
