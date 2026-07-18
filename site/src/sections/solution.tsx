import { BodyText, Eyebrow, H2, Section } from "@/components/ui";

/* Copy verbatim from site/COPY.md §5. The Loop is the one place teal appears
   outside a data figure — the loop closing is the win. Connectors are pure
   CSS (a continuous teal rail with node dots): vertical on mobile,
   horizontal from md up. */

const stages = [
  {
    name: "DECODE",
    line: "forensic diagnosis of your customer data: all ten scores computed, every revenue leak sized in rupees.",
  },
  {
    name: "DESIGN",
    line: "segment architecture, lifecycle blueprint, and the Loop Ledger: an experiment backlog with a forecast rupee value per test.",
  },
  {
    name: "DRIVE",
    line: "experiments and automations operated inside your stack, weekly cadence, every action tagged to a score.",
  },
  {
    name: "COMPOUND",
    line: "measure lift, bank winners into always-on systems, kill losers, re-score, raise targets. Return to Decode.",
  },
];

export function Solution() {
  return (
    <Section id="solution">
      <Eyebrow>WHAT PUNARA IS</Eyebrow>
      <H2 className="mt-4 max-w-3xl">
        Agencies execute campaigns. Dashboards report the past. Retention
        Intelligence prices the future.
      </H2>

      <BodyText className="mt-6">
        Punara is one firm with two inseparable halves.{" "}
        <strong className="font-semibold text-ink">Punara Advisory</strong> —
        consultants who run the method inside your stack and stake their fees
        on a public score.{" "}
        <strong className="font-semibold text-ink">Punara Lens</strong> — the
        customer intelligence platform that computes the same ten scores those
        consultants answer to. One scoring engine underneath both, so{" "}
        <strong className="font-semibold text-ink">
          our advice and our analytics cannot disagree.
        </strong>
      </BodyText>
      <BodyText className="mt-4">
        At Punara, CRM is not software you buy. It&rsquo;s a method you run:
        the{" "}
        <strong className="font-semibold text-ink">
          Compound Retention Method
        </strong>
        , executed as a loop that never terminates.
      </BodyText>

      <ol
        className="relative mt-14 grid gap-10 before:absolute before:bottom-2 before:left-[5px] before:top-2 before:w-px before:bg-teal/40 md:grid-cols-4 md:gap-8 md:before:bottom-auto md:before:left-2 md:before:right-2 md:before:top-[5px] md:before:h-px md:before:w-auto"
        aria-label="The Compounding Loop"
      >
        {stages.map((s) => (
          <li key={s.name} className="relative pl-8 md:pl-0 md:pt-8">
            <span
              aria-hidden="true"
              className="absolute left-0 top-1 h-[11px] w-[11px] rounded-full border-2 border-teal bg-bg md:top-0"
            />
            <strong className="font-mono text-sm font-semibold uppercase tracking-[0.2em] text-ink">
              {s.name}
            </strong>
            <p className="mt-2 text-sm leading-relaxed text-ink/80">{s.line}</p>
          </li>
        ))}
      </ol>
      <Eyebrow className="mt-10">ONE FULL REVOLUTION = ONE QUARTER</Eyebrow>

      <BodyText className="mt-10">
        <em>Punara</em>{" "}means &ldquo;again&rdquo; in Sanskrit. The second
        order, the returning customer, the loop run again — that&rsquo;s the
        whole company.
      </BodyText>
    </Section>
  );
}
