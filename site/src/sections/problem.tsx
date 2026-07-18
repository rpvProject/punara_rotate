import type { ReactNode } from "react";
import { BodyText, Card, Eyebrow, H2, H3, Section, StatNum } from "@/components/ui";

/* Copy verbatim from site/COPY.md §4. Ember is semantic (a leak), never
   decorative — it appears only on the leak figures. */

const failures: Array<{ title: string; body: ReactNode }> = [
  {
    title: "Fragmented data.",
    body: (
      <>
        Shopify, Razorpay, Shiprocket, Klaviyo, Interakt each hold a piece of
        the customer; nobody joins them — so one buyer appears as three
        profiles and every number downstream inherits the error.
      </>
    ),
  },
  {
    title: "Guesswork segmentation.",
    body: (
      <>
        Demographic hunches send the same <StatNum>10%</StatNum> code to a
        full-price loyalist and a lapsed discount-hunter — margin lost in both
        directions at once.
      </>
    ),
  },
  {
    title: "Dead lifecycle flows.",
    body: (
      <>
        The welcome series someone built in <StatNum>2023</StatNum> still runs;
        replenishment, winback, and COD confirmation — the moments with money
        in them — have nothing running at all.
      </>
    ),
  },
  {
    title: "No experimentation.",
    body: (
      <>
        Changes ship on opinion, so wins can&rsquo;t be repeated and losses
        can&rsquo;t be found; revenue moves and nobody can say why.
      </>
    ),
  },
  {
    title: "Report theatre.",
    body: (
      <>
        Monthly decks count sends and opens. Activity gets reported, outcomes
        don&rsquo;t, and the deck&rsquo;s real job is to renew the deck.
      </>
    ),
  },
  {
    title: "One-blast-fits-all.",
    body: (
      <>
        Every send to everyone borrows revenue from next week, trains buyers to
        wait for codes, and burns the deliverability you&rsquo;ll later pay to
        rebuild.
      </>
    ),
  },
];

const leaks: Array<{ title: string; body: ReactNode }> = [
  {
    title: "COD returns-to-origin.",
    body: (
      <>
        A <StatNum>₹40cr</StatNum> brand with half its orders on COD and a{" "}
        <StatNum>20%</StatNum> RTO rate has <StatNum>~₹4cr</StatNum> of
        dispatched orders coming back every year. Freight, reverse logistics,
        and written-off stock on those parcels typically burn{" "}
        <StatNum className="font-semibold text-ember-text">₹1.2–1.5cr/yr</StatNum>{" "}—
        a line most P&amp;Ls never itemise.
      </>
    ),
  },
  {
    title: "Silent churn.",
    body: (
      <>
        At a <StatNum>22%</StatNum> repeat rate, <StatNum>78</StatNum> of every{" "}
        <StatNum>100</StatNum> customers you paid <StatNum>~₹400</StatNum> each
        to acquire never come back — no complaint, no unsubscribe, no signal.
        One point of repeat rate at this scale is worth roughly{" "}
        <StatNum className="font-semibold text-ember-text">₹44L/yr</StatNum>{" "}
        <StatNum className="text-muted">
          (15,000 orders/mo × 1 pt × ₹2,200 AOV × 1.1 repeat-order multiplier ×
          12)
        </StatNum>
        .
      </>
    ),
  },
  {
    title: "Discount-only buyers.",
    body: (
      <>
        When a third of &ldquo;repeat&rdquo; revenue only converts with a code,
        that isn&rsquo;t loyalty — it&rsquo;s margin leaving in instalments. On{" "}
        <StatNum>₹12cr</StatNum> of repeat revenue at <StatNum>25%</StatNum>{" "}
        average code depth, the discount-dependent slice costs about{" "}
        <StatNum className="font-semibold text-ember-text">₹1cr/yr</StatNum> in
        contribution.
      </>
    ),
  },
];

export function Problem() {
  return (
    <Section id="problem">
      <Eyebrow>WHY BRANDS LOSE REPEAT REVENUE</Eyebrow>
      <H2 className="mt-4 max-w-3xl">
        You can see every ad click. You can&rsquo;t see who&rsquo;s coming
        back.
      </H2>
      <BodyText className="mt-6">
        You&rsquo;ve industrialised acquisition — attribution, creative
        testing, daily ROAS. Meanwhile the customers you already paid for, the
        only ones with margin left in them, sit in a list nobody models. Six
        failures, one pattern:
      </BodyText>

      <ol className="mt-14 grid gap-x-10 gap-y-9 sm:grid-cols-2 lg:grid-cols-3">
        {failures.map((f, i) => (
          <li key={f.title} className="border-t border-line pt-5">
            <p className="flex items-baseline gap-3">
              <StatNum className="text-xs text-muted">
                {String(i + 1).padStart(2, "0")}
              </StatNum>
              <strong className="font-semibold text-ink">{f.title}</strong>
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink/80">{f.body}</p>
          </li>
        ))}
      </ol>

      <H3 className="mt-20">What the leaks look like in rupees</H3>
      <div className="mt-8 grid gap-6 md:grid-cols-3">
        {leaks.map((l) => (
          <Card key={l.title}>
            <strong className="font-semibold text-ink">{l.title}</strong>
            <p className="mt-3 text-sm leading-relaxed text-ink/80">{l.body}</p>
          </Card>
        ))}
      </div>

      <BodyText className="mt-12">
        None of this is a creativity problem. It&rsquo;s a measurement problem
        — and measurement problems have engineering answers.
      </BodyText>
    </Section>
  );
}
