import type { ReactNode } from "react";

/* Shared primitives — see site/SITE_CONTRACTS.md for the API contract.
   One vertical rhythm for every section lives in <Section>. Do not add
   your own py-* to sections. */

const cx = (...parts: Array<string | false | undefined>) =>
  parts.filter(Boolean).join(" ");

export function Container({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx("mx-auto w-full max-w-6xl px-6 md:px-10", className)}>
      {children}
    </div>
  );
}

export function Section({
  id,
  dark,
  className,
  children,
}: {
  id: string;
  dark?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cx(dark && "dark-section", "py-20 md:py-28", className)}
    >
      <Container>{children}</Container>
    </section>
  );
}

export function Eyebrow({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <p
      className={cx(
        "font-mono text-xs uppercase tracking-[0.2em] text-muted",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function H2({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <h2
      className={cx(
        "font-display text-3xl tracking-tight text-ink md:text-4xl",
        className,
      )}
    >
      {children}
    </h2>
  );
}

export function H3({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <h3
      className={cx(
        "font-display text-xl tracking-tight text-ink md:text-2xl",
        className,
      )}
    >
      {children}
    </h3>
  );
}

export function BodyText({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <p className={cx("max-w-prose leading-relaxed text-ink/80", className)}>
      {children}
    </p>
  );
}

/** href defaults to "#book" — mid-page CTAs scroll to the booking section
    (which sets expectations before the external calendar link). Only #book
    itself links out to config.bookingUrl.
    `className` must NOT carry utilities that conflict with the base classes
    (padding, text size) — stylesheet order, not className order, wins ties.
    Use `compact` for the small variant. */
export function CTAButton({
  variant = "primary",
  href = "#book",
  compact,
  className,
  children,
}: {
  variant?: "primary" | "secondary";
  href?: string;
  compact?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      className={cx(
        "inline-block rounded-md text-sm font-medium transition-colors",
        compact ? "px-4 py-2" : "px-6 py-3",
        variant === "primary"
          ? "bg-marigold text-nightfall hover:bg-marigold/90"
          : "border border-line text-ink hover:border-graphite",
        className,
      )}
    >
      {children}
    </a>
  );
}

/** Mono, tabular numerals — use for every figure on the page. */
export function StatNum({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <span className={cx("num", className)}>{children}</span>;
}

/** Single border on surface. Never nest a Card inside a Card. */
export function Card({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cx("rounded-lg border border-line bg-surface p-6", className)}
    >
      {children}
    </div>
  );
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cx("border-line", className)} />;
}
