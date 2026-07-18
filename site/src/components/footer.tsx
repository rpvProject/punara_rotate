import { Container } from "@/components/ui";

/* Copy verbatim from site/COPY.md §14. The Legal column ships only when the
   real pages exist — a dead link labeled "placeholder" alarms procurement. */

const site = [
  { href: "#solution", label: "Method" },
  { href: "#services", label: "Services" },
  { href: "#platform", label: "Platform" },
  { href: "#process", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
  { href: "#book", label: "Book a Strategy Call" },
  { href: "#contact", label: "Contact" },
];

export function Footer() {
  return (
    <footer className="dark-section border-t border-line">
      {/* promise strip */}
      <div className="border-b border-line">
        <Container className="py-6">
          <p className="text-center font-mono text-xs tracking-[0.08em] text-muted">
            Every recommendation ships with a number, a baseline, and a
            deadline.
          </p>
        </Container>
      </div>

      <Container className="grid gap-10 py-14 md:grid-cols-[1fr_auto_auto] md:gap-16">
        <div>
          <p className="font-display text-lg tracking-tight text-ink">Punara</p>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted">
            Punara is the Retention Intelligence firm for Shopify D2C brands —
            ten scores, one CIQ, and recommendations priced in rupees. The
            science of the second order.
          </p>
        </div>

        <nav aria-label="Site">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            Site
          </p>
          <ul className="mt-4 space-y-3 text-sm">
            {site.map((l) => (
              <li key={l.label}>
                <a href={l.href} className="text-muted hover:text-ink">
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div>
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            Contact
          </p>
          <ul className="mt-4 space-y-3 text-sm">
            <li>
              <a
                href="mailto:hello@punara.com"
                className="text-muted hover:text-ink"
              >
                hello@punara.com
              </a>
            </li>
            <li>
              <a
                href="https://linkedin.com/company/punara"
                className="text-muted hover:text-ink"
              >
                LinkedIn
              </a>
            </li>
          </ul>
        </div>
      </Container>

      <div className="border-t border-line">
        <Container className="py-5">
          <p className="num text-xs text-muted">
            Built on Punara Lens · © 2026 Punara. All rights reserved.
          </p>
        </Container>
      </div>
    </footer>
  );
}
