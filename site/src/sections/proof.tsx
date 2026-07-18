import { BodyText, Eyebrow, H2, Section, StatNum } from "@/components/ui";
import { config } from "@/lib/config";
import type { ReactNode } from "react";

/* Copy verbatim from site/COPY.md §3. Flat tiles — no cards-in-cards. */

const TILES: { title: string; body: ReactNode }[] = [
  {
    title: "The method is public.",
    body: (
      <>
        The Punara Ten scoring rubrics — every component, every weight — are{" "}
        <a href={config.platformUrl} className="underline">
          published in full
        </a>
        . Grade our work with our own rubric.
      </>
    ),
  },
  {
    title: "The price is public.",
    body: (
      <>
        The Decode audit is <StatNum>₹1,95,000 / $2,900</StatNum>, on this
        page, never free, never discounted — and <StatNum>100%</StatNum> of it
        credits against a retainer signed within <StatNum>60 days</StatNum>.
        Retainers run{" "}
        <StatNum>₹1,50,000–₹9,00,000/mo ($2,500–$14,000)</StatNum>. Nothing on
        this site says “contact us for pricing.”
      </>
    ),
  },
  {
    title:
      "Every recommendation ships with a number, a baseline, and a deadline.",
    body: (
      <>
        It is the enforceable clause of every proposal. A deliverable that
        violates it gets rewritten before it leaves the building.
      </>
    ),
  },
];

export function Proof() {
  return (
    <Section id="proof">
      <Eyebrow>PROOF — THE PRE-LAUNCH VERSION</Eyebrow>
      <H2 className="mt-4 max-w-2xl">
        No client logos yet. Here’s what we show you instead.
      </H2>
      <BodyText className="mt-6 max-w-3xl">
        Punara is new, and we won’t rent credibility — no stock testimonials,
        no borrowed logos, no invented numbers. The founding client cohort is
        capped at <strong>three brands</strong>, on trade terms: named
        case-study and reference rights in exchange for founding conditions.
        Until those case studies exist, judge us on what you can verify today:
      </BodyText>
      <div className="mt-12 grid gap-8 md:grid-cols-3 md:gap-10">
        {TILES.map((t) => (
          <div key={t.title} className="border-t border-line pt-6">
            <h3 className="font-display text-lg tracking-tight text-ink">
              {t.title}
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-ink/80">{t.body}</p>
          </div>
        ))}
      </div>
      {/* Scarcity strip — a full-width hairline band, not a floating caption. */}
      <div className="mt-12 border-y border-line py-6">
        <p className="text-center font-mono text-xs uppercase tracking-[0.2em] text-muted">
          FOUNDING CLIENT COHORT —{" "}
          <StatNum className="text-lg text-ink">3</StatNum> SLOTS · A TRADE,
          NOT A DISCOUNT
        </p>
      </div>
    </Section>
  );
}
