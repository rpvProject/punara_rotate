import type { ReactNode } from "react";
import { BodyText, Eyebrow, H2, Section, StatNum } from "@/components/ui";

/* Copy verbatim from site/COPY.md §10. Metric names in Fraunces, measurement
   definitions in Inter with figures in mono via StatNum — mono is reserved
   for numerals and labels, not running sentences. */

const tiles: Array<{ metric: ReactNode; measure: ReactNode; mechanism: string }> = [
  {
    metric: "Repeat purchase rate",
    measure: (
      <>
        <StatNum>90</StatNum>-day and <StatNum>365</StatNum>-day, against a
        baseline locked before work begins.
      </>
    ),
    mechanism:
      "lifecycle coverage plus segment-conditioned offers — the right message at the right stage, not more messages.",
  },
  {
    metric: (
      <>
        <StatNum>12</StatNum>-month LTV
      </>
    ),
    measure: (
      <>
        Predicted per customer, reconciled against actuals monthly, forecast
        error published to you.
      </>
    ),
    mechanism:
      "an LTV-lever plan per segment — cadence, cross-sell, offer depth — ranked by forecast rupee value.",
  },
  {
    metric: "Churn-risk saves",
    measure: (
      <>
        Revenue retained from model-flagged customers, measured against a
        holdout that received nothing.
      </>
    ),
    mechanism:
      "churn-risk scoring plus save flows triggered before the silence becomes permanent.",
  },
  {
    metric: "Campaign ROI",
    measure: (
      <>
        Experiment-attributed contribution with holdouts; winners&rsquo; value
        banked as annualised rupees.
      </>
    ),
    mechanism:
      "the Loop Ledger — forecast value per test before funding, win/kill decisions inside one cycle.",
  },
  {
    metric: "Segmentation precision",
    measure: (
      <>
        Model lift over a recency-only baseline; predicted-vs-actual repeat
        revenue error, stated plainly.
      </>
    ),
    mechanism:
      "order-graph features and identity resolution — models fed clean data beat guesses fed everything.",
  },
  {
    metric: "Decision speed",
    measure: (
      <>
        Days from question to numbered answer; share of retention decisions
        made with a baseline attached.
      </>
    ),
    mechanism:
      "Lens computes, Veda decomposes, the monthly re-score keeps the scoreboard current.",
  },
];

export function Outcomes() {
  return (
    <Section id="outcomes">
      <Eyebrow>WHAT WE MEASURE</Eyebrow>
      <H2 className="mt-4 max-w-3xl">
        The six numbers we ask to be judged on.
      </H2>
      <BodyText className="mt-6">
        We don&rsquo;t promise percentages before your baseline exists — a
        forecast without a baseline is a horoscope. These are the metrics every
        engagement is scored against, each with the mechanism that moves it and
        the way it&rsquo;s measured.
      </BodyText>

      <ol className="mt-14 grid gap-x-10 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t, i) => (
          <li key={i} className="border-t border-line pt-6">
            <h3 className="font-display text-xl tracking-tight text-ink">
              {t.metric}
            </h3>
            <p className="mt-3 text-sm leading-relaxed text-ink/80">
              {t.measure}
            </p>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              <span className="font-mono text-[10px] uppercase tracking-[0.15em]">
                Mechanism ·{" "}
              </span>
              {t.mechanism}
            </p>
          </li>
        ))}
      </ol>
    </Section>
  );
}
