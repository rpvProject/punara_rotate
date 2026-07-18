import type { ReactNode } from "react";
import { BodyText, CTAButton, Eyebrow, H2, Section } from "@/components/ui";

/* Copy verbatim from site/COPY.md §8. The Punara column renders FIRST (right
   of the sticky row label) so the payoff column is inside the initial
   viewport on every breakpoint — the competitor columns are what scrolls. */

const No = ({ children }: { children: ReactNode }) => (
  <>
    <span aria-hidden="true" className="mr-1.5 text-muted">
      —
    </span>
    {children}
  </>
);

const Yes = ({ children }: { children: ReactNode }) => (
  <>
    <span aria-hidden="true" className="mr-1.5 text-teal">
      ✓
    </span>
    {children}
  </>
);

const rows: Array<{ label: string; cells: [ReactNode, ReactNode, ReactNode, ReactNode] }> = [
  {
    label: "Proprietary platform",
    cells: [
      "None — your data lives in their slides",
      "None — a folder of tool logins",
      "White-labels someone else's tool",
      "Punara Lens: one engine for scores, predictions, journeys",
    ],
  },
  {
    label: "Data-first method",
    cells: [
      "Campaign calendar first, data after",
      "Whatever worked at the last client",
      "The vendor's playbook templates",
      "Ten scores computed from your order graph before any recommendation",
    ],
  },
  {
    label: "Published scoring rubrics",
    cells: [
      <No key="t">No — activity reports</No>,
      <No key="f">No</No>,
      <No key="g">No</No>,
      <Yes key="p">Yes — the Punara Ten rubrics are public; grade us with them</Yes>,
    ],
  },
  {
    label: "AI on governed data",
    cells: [
      "Generic copy tools",
      "ChatGPT and a prayer",
      "The vendor's black-box “AI”",
      "Veda answers on your resolved, scored data — a number with a source",
    ],
  },
  {
    label: "Executive reporting",
    cells: [
      "A 40-slide monthly deck",
      "A WhatsApp message",
      "Platform screenshots",
      "One page: CIQ delta, banked value, kills, next bets",
    ],
  },
  {
    label: "Measurable ROI accountability",
    cells: [
      "Counts sends and opens",
      "Counts hours",
      "Counts messages delivered",
      "A fire-us-against-it number: the CIQ, re-scored monthly by software — not by us grading our own work",
    ],
  },
  {
    label: "Continuous experimentation",
    cells: [
      "Subject-line A/B tests, sometimes",
      "Rare",
      "The vendor's built-in tests",
      "The Loop Ledger: holdouts, forecast ₹ per test, winners banked, losers killed on schedule",
    ],
  },
];

const colHeaders = [
  "Traditional agency",
  "Freelance operator",
  "Generic CRM agency",
];

export function Difference() {
  return (
    <Section id="difference">
      <Eyebrow>WHY NOT AN AGENCY</Eyebrow>
      <H2 className="mt-4">
        Agencies have hands without models. Tools have models without hands.
      </H2>
      <BodyText className="mt-4">
        We built the third thing: operators accountable to a number that
        software computes. The honest comparison:
      </BodyText>

      <div className="relative mt-12">
        <div
          tabIndex={0}
          role="region"
          aria-label="Punara versus agencies comparison"
          className="overflow-x-auto rounded-lg border border-line"
        >
          <table className="w-full min-w-[900px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-line">
                <th scope="col" className="sticky left-0 z-[1] bg-bg px-4 py-3">
                  <span className="sr-only">Capability</span>
                </th>
                <th
                  scope="col"
                  className="border-r border-marigold/50 bg-marigold/[0.04] px-4 py-3 align-bottom font-mono text-xs font-semibold uppercase tracking-[0.15em] text-ink"
                >
                  Punara
                </th>
                {colHeaders.map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-3 align-bottom font-mono text-xs font-normal uppercase tracking-[0.15em] text-muted"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className="border-b border-line last:border-b-0">
                  <th
                    scope="row"
                    className="sticky left-0 z-[1] w-28 min-w-28 bg-bg px-4 py-4 align-top text-sm font-medium text-ink md:w-44 md:min-w-44"
                  >
                    {row.label}
                  </th>
                  <td className="border-r border-marigold/50 bg-marigold/[0.04] px-4 py-4 align-top leading-relaxed text-ink">
                    {row.cells[3]}
                  </td>
                  {row.cells.slice(0, 3).map((cell, i) => (
                    <td
                      key={i}
                      className="px-4 py-4 align-top leading-relaxed text-ink/70"
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Right-edge fade — signals more columns off-screen where the table
            clips (container max-w-6xl fits 900px only from lg up). */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 right-0 w-12 rounded-r-lg bg-gradient-to-l from-bg to-transparent lg:hidden"
        />
      </div>
      <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted lg:hidden">
        Scroll → for the agency columns
      </p>

      <BodyText className="mt-10">
        We also refuse the work that defines an agency — creative-only
        projects, paid-ads management, execution-only campaigns. If the
        deliverable is an asset, we&rsquo;re the wrong firm. If the deliverable
        is a number that goes up, we&rsquo;re the only firm.
      </BodyText>

      <div className="mt-10">
        <CTAButton>Book a Strategy Call</CTAButton>
        <p className="mt-3 font-mono text-xs tracking-[0.15em] text-muted">
          30 MIN · FOUNDER-LED · NOTHING PITCHED
        </p>
      </div>
    </Section>
  );
}
