import type { ReactNode } from "react";
import { CTAButton, Eyebrow, H2, H3, Section, StatNum } from "@/components/ui";

/* Copy verbatim from site/COPY.md §9. Step numbers oversized in IBM Plex
   Mono; the Decode price set large — radical price transparency is the
   design moment here. */

const steps: Array<{ title: string; body: ReactNode }> = [
  {
    title: "The Decode.",
    body: (
      <>
        <p className="text-sm leading-relaxed text-ink/80">
          A <StatNum>3</StatNum>-week paid audit.
        </p>
        <p className="mt-3">
          <StatNum className="text-3xl font-medium text-ink md:text-4xl">
            ₹1,95,000
          </StatNum>{" "}
          <span className="text-muted">/</span>{" "}
          <StatNum className="text-xl text-ink/80 md:text-2xl">$2,900</StatNum>
        </p>
        {/* Price and credit read as one unit — never let the number anchor
            without its offset. */}
        <p className="mt-2 text-sm font-semibold leading-relaxed text-ink">
          <StatNum>100%</StatNum> creditable against any retainer signed
          within <StatNum>60</StatNum> days.
        </p>
        <p className="mt-4 text-sm leading-relaxed text-ink/80">
          Week one: full read access to orders and customers, ingested into
          Lens, Signal Score computed first — if your data can&rsquo;t be
          trusted, that&rsquo;s finding number one. Week two: all ten scores
          plus your CIQ, the leak map quantified in rupees. Week three: a{" "}
          <StatNum>90</StatNum>-day Loop Ledger and a <StatNum>90</StatNum>
          -minute readout with your leadership. Never free — a free audit is a
          lead magnet wearing a lab coat.
        </p>
      </>
    ),
  },
  {
    title: "Strategy.",
    body: (
      <p className="text-sm leading-relaxed text-ink/80">
        Lever selection ratified with your leadership against the leak map, not
        against our preferences. Segment architecture, lifecycle blueprint, and
        Loop Ledger v1: every experiment with a forecast rupee value, a
        baseline, and a deadline. This document is what the quarterly review
        will be judged against.
      </p>
    ),
  },
  {
    title: "Data Integration.",
    body: (
      <p className="text-sm leading-relaxed text-ink/80">
        The Decode&rsquo;s one-time ingest becomes permanent plumbing:
        automated syncs from Shopify, Razorpay, Shiprocket, and your messaging
        platforms; identity resolution maintained continuously; the ten scores
        recomputed monthly without anyone exporting a CSV.
      </p>
    ),
  },
  {
    title: "Automation.",
    body: (
      <p className="text-sm leading-relaxed text-ink/80">
        The uncovered lifecycle moments get always-on flows, built inside your
        stack — Klaviyo, Interakt, your BSP — each tagged to the score it
        should move and measured against a holdout. We add no sending
        infrastructure of our own, ever.
      </p>
    ),
  },
  {
    title: "Optimization.",
    body: (
      <p className="text-sm leading-relaxed text-ink/80">
        Weekly experiment cadence from the Loop Ledger: pre-registered
        hypotheses, holdouts, win/kill decisions inside one cycle. Winners get
        hardened into always-on systems; losers get killed and logged with what
        they cost. You see both lists.
      </p>
    ),
  },
  {
    title: "Continuous Growth.",
    body: (
      <p className="text-sm leading-relaxed text-ink/80">
        Quarterly rebaseline: CIQ against target, rupees banked against fees
        paid, targets raised, Ledger renewed. The tier recommendation is honest
        in both directions — including downgrade when your team can run the
        Loop without us. The Altitude Score measures exactly that.
      </p>
    ),
  },
];

export function Process() {
  return (
    <Section id="process">
      <Eyebrow>HOW AN ENGAGEMENT RUNS</Eyebrow>
      <H2 className="mt-4 max-w-3xl">
        Start with the Decode. Stay for the compounding.
      </H2>

      <ol className="mt-14">
        {steps.map((s, i) => (
          <li
            key={s.title}
            className="grid gap-3 border-t border-line py-10 md:grid-cols-[7rem_1fr] md:gap-10"
          >
            <StatNum
              aria-hidden="true"
              className="text-4xl leading-none text-muted/50 md:text-5xl"
            >
              {String(i + 1).padStart(2, "0")}
            </StatNum>
            <div className="max-w-prose">
              <H3>{s.title}</H3>
              <div className="mt-3">{s.body}</div>
            </div>
          </li>
        ))}
      </ol>

      <p className="num max-w-prose border-t border-line pt-8 text-sm leading-relaxed text-ink/80">
        Retainers from ₹1,50,000/mo ($2,500) to ₹9,00,000/mo ($14,000) · flat
        fee · 3-month minimum · no success fees · annual prepay 10% off — the
        only discount that exists.
      </p>

      <CTAButton className="mt-10">Book a Strategy Call</CTAButton>
    </Section>
  );
}
