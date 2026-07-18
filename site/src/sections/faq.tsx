import type { ReactNode } from "react";
import { BodyText, Eyebrow, H2, Section, StatNum } from "@/components/ui";
import { faqItems } from "@/lib/faq-data";

/* FAQ — rendered from src/lib/faq-data.ts, the SAME strings the FAQPage
   JSON-LD serializes, so page and schema cannot drift (Google requires the
   marked-up text to be visible on the page). Native <details>/<summary>
   accordion: keyboard + screen-reader accessible out of the box, no JS.
   First item open by default. */

/* Wrap figure runs (₹1,95,000, $2,900, 100%, +1.4, 90-day …) in StatNum so
   the mono-numeral rule holds without duplicating the copy as JSX. */
const NUM_RE =
  /(?<![A-Za-z])([+~]?[₹$]?\d+(?:[,.]\d+)*(?:%|L|cr)?(?:\/mo)?)(?![A-Za-z\d])/g;

function withStatNums(text: string): ReactNode[] {
  return text
    .split(NUM_RE)
    .map((part, i) => (i % 2 ? <StatNum key={i}>{part}</StatNum> : part));
}

export function Faq() {
  return (
    <Section id="faq">
      <Eyebrow>THE QUESTIONS WE ACTUALLY HEAR</Eyebrow>
      <H2 className="mt-4">Asked and answered, before the call.</H2>
      <div className="mt-10 max-w-3xl divide-y divide-line border-y border-line">
        {faqItems.map(({ q, a }, i) => (
          <details key={q} className="group py-5" open={i === 0}>
            <summary className="flex cursor-pointer list-none items-baseline justify-between gap-6 font-display text-lg tracking-tight text-ink md:text-xl [&::-webkit-details-marker]:hidden">
              <span>{q}</span>
              <span
                aria-hidden="true"
                className="num shrink-0 text-muted transition-transform group-open:rotate-45"
              >
                +
              </span>
            </summary>
            <BodyText className="mt-3">{withStatNums(a)}</BodyText>
          </details>
        ))}
      </div>
    </Section>
  );
}
