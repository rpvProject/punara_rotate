"use client";

import { useEffect, useRef, useState } from "react";
import { config } from "@/lib/config";
import { BodyText, Eyebrow, H2, Section, StatNum } from "@/components/ui";

/* Booking — copy verbatim from site/COPY.md §12 (anchor id `book` per
   SITE_CONTRACTS.md §1). Nightfall closing block, mirror of the hero.

   Inline embed architecture — provider swap is a pure URL swap:
   NEXT_PUBLIC_BOOKING_URL is used as-is as the iframe `src`. Cal.com and
   Calendly share links are directly iframe-embeddable, so when the URL's
   host matches either, we render a lazy-loaded inline calendar (client-side
   IntersectionObserver; the iframe mounts only when the section scrolls
   near, with min-height reserved so nothing shifts). Any other provider
   whose share URL is iframe-embeddable (Google appointment scheduling
   pages, Microsoft Bookings pages) just needs its host added to
   EMBEDDABLE_HOSTS below — no other code changes. Unknown hosts fall back
   to link-only, and the Marigold link button is always present regardless,
   so booking never depends on the embed. */

const EMBEDDABLE_HOSTS = [/(^|\.)cal\.com$/i, /(^|\.)calendly\.com$/i];

function bookingHost(): string {
  try {
    return new URL(config.bookingUrl).hostname;
  } catch {
    return "";
  }
}

/* The embed renders only when a REAL booking URL is configured — the default
   placeholder would show the provider's 404 page at the conversion moment.
   The Marigold button above always books regardless. */
const canEmbed =
  config.bookingUrlSet && EMBEDDABLE_HOSTS.some((re) => re.test(bookingHost()));

function BookingEmbed() {
  const ref = useRef<HTMLDivElement>(null);
  const [load, setLoad] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    /* IntersectionObserver is baseline in every browser this site targets;
       if it were ever absent the Marigold link button above still books. */
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setLoad(true);
          io.disconnect();
        }
      },
      { rootMargin: "600px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    /* min-height reserved up front (CLS) — but as a visible, intentional
       panel, never an empty void: bordered surface with a mono label the
       iframe paints over when it arrives. */
    <div
      ref={ref}
      className="relative mx-auto mt-12 min-h-[640px] max-w-3xl rounded-lg border border-line bg-surface"
    >
      <p className="absolute inset-0 flex items-center justify-center px-6 text-center font-mono text-xs uppercase tracking-[0.2em] text-muted">
        Calendar — the button above books the same slots
      </p>
      {load ? (
        <iframe
          src={config.bookingUrl}
          title="Book a Strategy Call — scheduling calendar"
          className="relative h-[640px] w-full rounded-lg bg-bone"
          loading="lazy"
        />
      ) : null}
    </div>
  );
}

const bullets: { lead: string; rest: string }[] = [
  {
    lead: "We ask about your numbers.",
    rest: " Order volume, repeat rate, COD share, who owns retention. Rough answers are fine — not knowing them is itself a finding, and a common one.",
  },
  {
    lead: "We disqualify out loud, both ways.",
    rest: " Under ₹10 crore, marketplace-only, or looking for pure execution? We'll say so on the call and point you somewhere useful — expect a hard no if the leak isn't there.",
  },
  {
    lead: "Nothing is pitched.",
    rest: " No deck, no proposal, no follow-up sequence. If the leak looks real, the only thing we'll suggest is the Decode — ₹1,95,000 / $2,900, priced right here so the call never has to become a negotiation.",
  },
];

export function Book() {
  return (
    <Section id="book" dark>
      <div className="mx-auto max-w-2xl text-center">
        <Eyebrow>THE NEXT STEP</Eyebrow>
        <H2 className="mt-4">Thirty minutes. Your numbers, not our deck.</H2>
        <BodyText className="mx-auto mt-5">
          A strategy call with the founder — not an SDR — that decides,
          together, whether there&rsquo;s enough leak in your business to be
          worth finding.
        </BodyText>
      </div>

      <ul className="mx-auto mt-10 max-w-2xl space-y-5">
        {bullets.map(({ lead, rest }) => (
          <li key={lead} className="leading-relaxed text-ink/80">
            <strong className="font-medium text-ink">{lead}</strong>
            {rest}
          </li>
        ))}
      </ul>

      {/* Founder note — the person the call is with, in their own register.
          Name + headshot land with the real founder profile at launch. */}
      <div className="mx-auto mt-12 max-w-2xl border-t border-line pt-8">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
          A note from the founder
        </p>
        <p className="mt-3 leading-relaxed text-ink/80">
          Punara means &ldquo;again&rdquo; — the second order, the returning
          customer, the retainer re-earned every quarter. I published the
          Punara Ten rubrics before selling a single retainer because
          I&rsquo;d rather be graded than believed. The call is with me, and
          your numbers set the agenda.
        </p>
        <p className="mt-3 text-sm">
          <a
            href="https://linkedin.com/company/punara"
            target="_blank"
            rel="noopener noreferrer"
            className="text-ink underline"
          >
            Punara on LinkedIn
          </a>
        </p>
      </div>

      <div className="mt-12 text-center">
        {/* Not CTAButton: the microcopy promises a new tab and the shared
            primitive has no `target` prop (flagged as a primitive gap).
            Classes mirror CTAButton primary exactly. */}
        <a
          href={config.bookingUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block rounded-md bg-marigold px-6 py-3 text-sm font-medium text-nightfall transition-colors hover:bg-marigold/90"
        >
          Book a Strategy Call
        </a>
        <p className="mt-4 font-mono text-xs tracking-[0.15em] text-muted">
          30 MIN · VIDEO CALL · FOUNDER-LED — calendar opens in a new tab
        </p>
        <p className="mt-2 font-mono text-xs uppercase tracking-[0.15em] text-muted">
          FOUNDING COHORT — <StatNum>3</StatNum> SLOTS · A TRADE, NOT A
          DISCOUNT
        </p>
        <p className="mt-6 text-sm text-ink/70">
          <a href="#contact" className="underline">
            Not ready to book? Write to us first ↓
          </a>
        </p>
      </div>

      {canEmbed && <BookingEmbed />}
    </Section>
  );
}
