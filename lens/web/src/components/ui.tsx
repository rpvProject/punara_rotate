"use client";

import { churnBandColor, labelize } from "@/lib/format";

/** Full-page panel when the API process is unreachable. */
export function OfflinePanel({ retry }: { retry?: () => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 text-center">
      <div className="h-2 w-2 rounded-full bg-ember" />
      <h2 className="font-display text-2xl text-bone">Lens API offline</h2>
      <p className="text-sm text-muted">
        The dashboard reads a local API on{" "}
        <span className="num">127.0.0.1:8010</span>. Start it with
      </p>
      <code className="num rounded border border-line bg-panel px-4 py-2 text-sm text-marigold">
        python -m lens api
      </code>
      {retry && (
        <button
          onClick={retry}
          className="mt-2 rounded border border-line px-4 py-1.5 text-sm text-muted transition-colors hover:border-graphite hover:text-bone"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
      <h2 className="font-display text-xl text-bone">Something went wrong</h2>
      <p className="num text-sm text-ember">{message}</p>
    </div>
  );
}

export function EmptyState({ note }: { note: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel px-6 py-16 text-center">
      <p className="text-sm text-muted">{note}</p>
      <p className="mt-2 num text-xs text-graphite">
        seed &rarr; nightly pipeline &rarr; refresh
      </p>
    </div>
  );
}

/** Loading skeleton: a header bar plus n pulsing blocks. */
export function Skeleton({ blocks = 3 }: { blocks?: number }) {
  return (
    <div className="animate-pulse space-y-6" aria-busy>
      <div className="h-8 w-64 rounded bg-panel2" />
      {Array.from({ length: blocks }, (_, i) => (
        <div key={i} className="h-40 rounded-lg bg-panel" />
      ))}
    </div>
  );
}

export function PageHeader({
  title,
  sub,
  right,
}: {
  title: string;
  sub?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl font-medium tracking-tight text-bone">
          {title}
        </h1>
        {sub && <p className="mt-1.5 text-sm text-muted">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-line bg-panel p-5 ${className}`}>
      {title && (
        <h3 className="mb-4 text-xs font-medium uppercase tracking-[0.14em] text-muted">
          {title}
        </h3>
      )}
      {children}
    </section>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "good" | "warn" | "risk";
}) {
  const color =
    tone === "good"
      ? "text-teal"
      : tone === "risk"
        ? "text-ember"
        : tone === "warn"
          ? "text-marigold"
          : "text-bone";
  return (
    <div className="rounded-lg border border-line bg-panel px-5 py-4">
      <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted">
        {label}
      </div>
      <div className={`num mt-2 text-2xl ${color}`}>{value}</div>
      {sub && <div className="num mt-1 text-xs text-graphite">{sub}</div>}
    </div>
  );
}

const STAGE_TONES: Record<string, string> = {
  new: "text-series-new border-series-new/40",
  active: "text-teal border-teal/40",
  loyal: "text-teal border-teal/40",
  slipping: "text-marigold border-marigold/40",
  dormant: "text-ember border-ember/40",
  lost: "text-graphite border-graphite/40",
};

export function StageBadge({ stage }: { stage: string }) {
  const tone = STAGE_TONES[stage] ?? "text-muted border-line";
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs ${tone}`}>
      {labelize(stage)}
    </span>
  );
}

/** Churn-risk band chip: high ember, medium marigold, low teal. */
export function ChurnBandBadge({ band }: { band: string }) {
  const c = churnBandColor(band);
  return (
    <span
      className="inline-block rounded-full border px-2.5 py-0.5 text-xs"
      style={{ color: c, borderColor: `${c}66` }}
    >
      {labelize(band)} risk
    </span>
  );
}

export function ConsentBadge({ channel, on }: { channel: string; on: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
        on ? "border-teal/40 text-teal" : "border-line text-graphite line-through"
      }`}
    >
      <span aria-hidden>{on ? "✓" : "✗"}</span>
      {labelize(channel)}
    </span>
  );
}
