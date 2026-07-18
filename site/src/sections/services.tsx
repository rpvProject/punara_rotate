import { BodyText, Card, Eyebrow, H2, Section } from "@/components/ui";

/* Copy verbatim from site/COPY.md §6. */

const services: Array<{ title: string; body: string; chip: string }> = [
  {
    title: "Retention Marketing",
    body: "Repeat-purchase strategy tied to your unit economics: which customers, what cadence, what offer depth — designed against a baseline, not a festival calendar.",
    chip: "Moves: Gravity Score",
  },
  {
    title: "Lifecycle Marketing",
    body: "Stage architecture from new to loyal to dormant, with rupee-valued transition rules and an owned flow for every slip.",
    chip: "Moves: Flow Score",
  },
  {
    title: "Customer Analytics",
    body: "Your order graph — orders, margins, RTO, repeat cycles — joined across sources, resolved to one identity per customer, and made queryable.",
    chip: "Moves: Signal Score",
  },
  {
    title: "WhatsApp Marketing",
    body: "Opt-in economics, revenue per conversation, and COD-confirmation flows that intercept RTO before the parcel ships.",
    chip: "Moves: Watertight Score",
  },
  {
    title: "Email Marketing",
    body: "Deliverability remediation, list hygiene, and lifecycle flows scored on inbox placement and attributed revenue — not opens.",
    chip: "Moves: Vitals Score",
  },
  {
    title: "CRM Automation",
    body: "The twelve high-value lifecycle moments, each covered by a measured always-on automation instead of a manual blast.",
    chip: "Moves: Autopilot Score",
  },
  {
    title: "Customer Segmentation",
    body: "Behavioural and predictive segments — not demographic guesses — synced straight into Klaviyo, Interakt, and your BSP.",
    chip: "Moves: Flow Score",
  },
  {
    title: "LTV Optimization",
    body: "Which levers move predicted lifetime value for which segments, at what rupee value — ranked before you spend a rupee.",
    chip: "Moves: Gravity Score",
  },
  {
    title: "Predictive Analytics",
    body: "Churn-risk and next-order-timing models (BG/NBD, XGBoost) tested against a naive baseline — and we publish the lift either way.",
    chip: "Moves: Punara CIQ",
  },
  {
    title: "CRO & Experimentation",
    body: "Repeat-purchase CRO with holdouts, sample-size discipline, and a kill rule: winners banked, losers buried, both logged.",
    chip: "Moves: Velocity Score",
  },
  {
    title: "Executive Dashboards",
    body: "One operating view for your team, one board view for you: CIQ trend, repeat-revenue mix, leak ledger — weekly and quarterly.",
    chip: "Moves: Altitude Score",
  },
  {
    title: "AI Insights",
    body: "Ask Veda why a score moved; get the decomposition, the driver, and the next experiment — never a vibe, always a number.",
    chip: "Moves: all ten",
  },
];

/* Three anchor practices as full cards; the other nine as a dense divider
   list — twelve identical cards was the page's longest monotony stretch and
   ~4 screens of the same stacked card at 390px. */
const ANCHOR_TITLES = new Set([
  "Retention Marketing",
  "Customer Analytics",
  "Predictive Analytics",
]);
const anchors = services.filter((s) => ANCHOR_TITLES.has(s.title));
const rest = services.filter((s) => !ANCHOR_TITLES.has(s.title));

export function Services() {
  return (
    <Section id="services">
      <Eyebrow>WHAT WE DO</Eyebrow>
      <H2 className="mt-4">If it can&rsquo;t move a score, we don&rsquo;t sell it.</H2>
      <BodyText className="mt-4">
        Twelve capabilities, each mapped to the Punara Ten score it exists to
        move. Sold as engagements, never à la carte — &ldquo;just run our
        emails&rdquo; is how retention got broken in the first place.
      </BodyText>

      <ul className="mt-12 grid gap-4 md:grid-cols-3" role="list">
        {anchors.map((s) => (
          <li key={s.title} className="h-full">
            <Card className="flex h-full flex-col gap-3 transition-[transform,border-color] duration-200 motion-safe:hover:-translate-y-0.5 hover:border-graphite/50">
              <h3 className="font-display text-lg tracking-tight text-ink">
                {s.title}
              </h3>
              <p className="text-sm leading-relaxed text-ink/80">{s.body}</p>
              <span className="mt-auto inline-block w-fit rounded border border-line px-2 py-0.5 font-mono text-xs text-muted">
                {s.chip}
              </span>
            </Card>
          </li>
        ))}
      </ul>

      <ul className="mt-10 grid gap-x-12 md:grid-cols-2" role="list">
        {rest.map((s) => (
          <li key={s.title} className="border-b border-line py-4">
            <div className="flex items-baseline justify-between gap-4">
              <h3 className="font-display text-base tracking-tight text-ink">
                {s.title}
              </h3>
              <span className="shrink-0 font-mono text-xs text-muted">
                {s.chip}
              </span>
            </div>
            <p className="mt-1 text-sm leading-relaxed text-ink/70">{s.body}</p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
