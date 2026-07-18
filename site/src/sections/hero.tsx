import { CTAButton, Eyebrow, Section, StatNum } from "@/components/ui";
import { DashboardMockup } from "@/components/dashboard-mockup";
import { config } from "@/lib/config";

/* Copy verbatim from site/COPY.md §2. */
export function Hero() {
  return (
    <Section id="hero" dark>
      <Eyebrow className="text-muted">
        RETENTION INTELLIGENCE · PUNARA ADVISORY × PUNARA LENS
      </Eyebrow>
      <h1 className="mt-6 max-w-4xl font-display text-[clamp(2.5rem,6.5vw,4.75rem)] leading-[1.05] tracking-tight text-ink">
        Your first order is a cost. Your second order is a business.
      </h1>
      <p className="mt-6 max-w-2xl text-base leading-relaxed text-ink/80 md:text-lg">
        Punara is the Retention Intelligence firm for Shopify and D2C brands
        doing <StatNum>₹10–200 crore ($1M–$25M)</StatNum>. Ten published
        scores rolled into one number — the CIQ — and every recommendation
        priced in rupees, with a baseline and a deadline, before you spend
        anything acting on it.
      </p>
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <CTAButton>Book a Strategy Call</CTAButton>
        <CTAButton variant="secondary" href={config.platformUrl}>
          Explore the platform
        </CTAButton>
      </div>
      <p className="mt-4 font-mono text-xs tracking-[0.08em] text-muted">
        No free audits. No success fees. No 40-slide decks.
      </p>
      <figure className="mt-12 md:mt-16">
        <DashboardMockup />
        <figcaption className="mt-4 max-w-2xl text-xs leading-relaxed text-muted md:text-sm">
          Punara Lens, our customer intelligence platform — working product,
          not concept art. It computes the same ten scores our consultants are
          judged on.
        </figcaption>
      </figure>
    </Section>
  );
}
