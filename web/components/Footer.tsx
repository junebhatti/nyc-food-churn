/** Sources and credit, at the foot of the map and every story. */
export default function Footer() {
  return (
    <footer className="border-t border-ink px-4 py-10 md:px-10">
      <p className="label max-w-3xl leading-relaxed">
        Sources: NYC DOHMH restaurant inspections (about 75 archived copies, 2012–2026), NY State Liquor Authority licences, USDA SNAP
        retailers, NYC storefront registry rents (LL157), NYC Planning boundaries, MTA, TLC and Census data for foot traffic, and
        Census Business Dynamics for validation. A place counts as closed when it leaves the inspection data; closure dates are
        estimated to within about a season. Built by Junaid Bhatti.
      </p>
    </footer>
  );
}
