"use client";

import Link from "next/link";
import { useState } from "react";
import {
  getCx,
  getMessaging,
  getOverview,
  getRevenue,
  getScores,
  type CxMonth,
  type MessagingPayload,
  type Overview,
  type RevenueMonth,
  type ScoreEntry,
  type ScoresPayload,
} from "@/lib/api";
import { useApi } from "@/lib/use-api";
import {
  bandColor,
  formatCount,
  formatDate,
  formatINR,
  formatINRCompact,
  formatPct,
  labelize,
} from "@/lib/format";
import { CiqDial, RevenueSparkline } from "@/components/charts";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
  StatTile,
} from "@/components/ui";

/** The nine Punara scores grouped by Compounding Loop stage (_canon.md §7). */
const LOOP_STAGES: { stage: string; note: string; scores: string[] }[] = [
  { stage: "Decode", note: "see the truth", scores: ["signal", "altitude"] },
  { stage: "Design", note: "build the engine", scores: ["vitals", "autopilot"] },
  { stage: "Drive", note: "ship and learn", scores: ["velocity", "flow"] },
  { stage: "Compound", note: "keep the gains", scores: ["gravity", "watertight", "pulse"] },
];

function ScoreTile({ entry }: { entry: ScoreEntry }) {
  const [open, setOpen] = useState(false);
  const value = entry.value ?? 0;
  const color = bandColor(value);
  const components = Object.entries(entry.components);
  return (
    <div className="rounded-lg border border-line bg-panel">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
        aria-expanded={open}
      >
        <div>
          <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted">
            {labelize(entry.score)}
          </div>
          <div className="num mt-1 text-3xl" style={{ color }}>
            {value.toFixed(1)}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href={`/scores/${entry.score}`}
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-graphite underline-offset-2 hover:text-marigold hover:underline"
          >
            history
          </Link>
          <span className="text-graphite">{open ? "−" : "+"}</span>
        </div>
      </button>
      {/* band track */}
      <div className="mx-5 h-1 rounded-full bg-line">
        <div
          className="h-1 rounded-full"
          style={{ width: `${value}%`, background: color }}
        />
      </div>
      {open && (
        <dl className="space-y-2 px-5 py-4">
          {components.length === 0 && (
            <div className="text-xs text-graphite">No component detail.</div>
          )}
          {components.map(([k, v]) => (
            <div key={k} className="flex items-center gap-3 text-xs">
              <dt className="w-40 shrink-0 truncate text-muted" title={labelize(k)}>
                {labelize(k)}
              </dt>
              {typeof v === "string" ? (
                <dd className="truncate text-graphite" title={v}>
                  {v}
                </dd>
              ) : k.endsWith("_paise") ? (
                <dd className="num text-ember">{formatINR(v)}</dd>
              ) : k.endsWith("_raw") ? (
                <dd className="num text-graphite">{v}</dd>
              ) : (
                <>
                  <dd className="h-1 flex-1 rounded-full bg-line">
                    <div
                      className="h-1 rounded-full"
                      style={{
                        width: `${Math.max(0, Math.min(100, v))}%`,
                        background: bandColor(v),
                      }}
                    />
                  </dd>
                  <dd className="num w-10 text-right text-bone">{v.toFixed(0)}</dd>
                </>
              )}
            </div>
          ))}
        </dl>
      )}
      {!open && <div className="pb-4" />}
    </div>
  );
}

export default function OverviewPage() {
  const { data, tenant, loading, offline, error, retry } = useApi<{
    overview: Overview;
    scores: ScoresPayload;
    revenue: RevenueMonth[];
    cx: CxMonth[] | null;
    messaging: MessagingPayload | null;
  }>(async (t) => {
    const [overview, scores, revenue, cx, messaging] = await Promise.all([
      getOverview(t.id),
      getScores(t.id),
      getRevenue(t.id),
      getCx(t.id),
      getMessaging(t.id),
    ]);
    return { overview, scores, revenue, cx, messaging };
  });

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={3} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error || !data) return <ErrorPanel message={error ?? "no data"} />;

  const { overview: o, scores, revenue, cx, messaging } = data;
  const byName = new Map(scores.scores.map((s) => [s.score, s]));
  const computed = (n: string) => {
    const s = byName.get(n);
    return s && s.status === "computed" ? s : null;
  };
  const pending = scores.scores.filter((s) => s.status === "phase_2");

  // full CIQ when the v2 engine has landed; fall back to v0's ciq_partial
  const ciqEntry = byName.get("ciq");
  const ciqValue = ciqEntry?.value ?? o.scores.ciq ?? o.scores.ciq_partial ?? null;
  const full = ciqEntry != null || o.scores.ciq != null;
  const coverage =
    typeof ciqEntry?.components.coverage === "string"
      ? ciqEntry.components.coverage
      : full
        ? "9/9"
        : null;

  const cxNow = cx?.length ? cx[cx.length - 1] : null;
  const wa = messaging?.whatsapp_summary ?? null;

  return (
    <>
      <PageHeader
        title={tenant?.name ?? "Overview"}
        sub={`Retention intelligence · trailing ${o.window_months} months`}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Customer Intelligence Quotient" className="lg:row-span-2">
          {ciqValue !== null ? (
            <CiqDial
              value={ciqValue}
              label={full ? `CIQ · ${coverage ?? "FULL"}` : "CIQ · PARTIAL"}
            />
          ) : (
            <p className="py-10 text-center text-sm text-graphite">
              No CIQ yet — run the nightly pipeline.
            </p>
          )}
          <p className="mt-4 text-center text-xs leading-relaxed text-graphite">
            {full ? (
              <>
                Weighted composite of all nine Punara scores.
                <br />
                0–40 Leaking · 40–70 Building · 70–100 Compounding.
              </>
            ) : (
              <>
                Partial CIQ from Gravity, Flow, Signal and Watertight.
                <br />
                The full nine-score composite lands with Phase 2.
              </>
            )}
          </p>
        </Card>
        <div className="space-y-5 lg:col-span-2">
          {LOOP_STAGES.map(({ stage, note, scores: names }) => {
            const tiles = names
              .map(computed)
              .filter((s): s is ScoreEntry => s !== null);
            if (tiles.length === 0) return null;
            return (
              <section key={stage}>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-graphite">
                  <span className="text-muted">{stage}</span> · {note}
                </h3>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {tiles.map((s) => (
                    <ScoreTile key={s.score} entry={s} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
        {pending.length > 0 && (
          <Card title="Pending scores" className="lg:col-span-2">
            <div className="flex flex-wrap gap-2">
              {pending.map((s) => (
                <span
                  key={s.score}
                  className="rounded-full border border-line px-3 py-1 text-xs text-graphite"
                >
                  {labelize(s.score)} · Phase 2
                </span>
              ))}
            </div>
          </Card>
        )}
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Repeat rate" value={formatPct(o.repeat_rate)} tone="good" />
        <StatTile label="AOV" value={formatINR(o.aov_paise)} />
        <StatTile
          label="Revenue"
          value={formatINRCompact(o.total_revenue_paise)}
          sub={`repeat ${formatINRCompact(o.repeat_revenue_paise)}`}
        />
        <StatTile label="Orders" value={formatCount(o.orders)} />
        <StatTile
          label="Customers"
          value={formatCount(o.customers)}
          sub={`+${formatCount(o.new_customers_last_month)} last month`}
        />
        <StatTile
          label="Revenue leak"
          value={formatINRCompact(o.leak_total_paise)}
          tone="risk"
        />
      </div>

      {(cxNow || wa) && (
        <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
          {cxNow && (
            <>
              <StatTile
                label="Delivery (median)"
                value={
                  cxNow.median_delivery_days != null
                    ? `${cxNow.median_delivery_days.toFixed(1)}d`
                    : "—"
                }
                sub="latest month"
              />
              <StatTile
                label="RTO rate"
                value={formatPct(cxNow.rto_rate)}
                tone="risk"
                sub="latest month"
              />
              <StatTile
                label="Resolution (median)"
                value={
                  cxNow.median_resolution_hours != null
                    ? `${cxNow.median_resolution_hours.toFixed(0)}h`
                    : "—"
                }
                sub="support tickets"
              />
              <StatTile
                label="NPS"
                value={cxNow.nps != null ? cxNow.nps.toFixed(0) : "—"}
                tone={cxNow.nps != null && cxNow.nps > 0 ? "good" : undefined}
                sub={`${formatCount(cxNow.nps_responses)} responses`}
              />
            </>
          )}
          {wa && (
            <StatTile
              label="Rev / conversation"
              value={formatINR(wa.revenue_per_conversation_paise)}
              tone="warn"
              sub="WhatsApp · trailing 12mo"
            />
          )}
        </div>
      )}

      <Card title="Monthly revenue" className="mt-8">
        {revenue.length ? (
          <RevenueSparkline data={revenue} />
        ) : (
          <EmptyState note="No revenue history yet." />
        )}
        <div className="mt-3 flex justify-between text-xs text-graphite">
          <span>
            <Link href="/revenue" className="hover:text-marigold">
              Full revenue view &rarr;
            </Link>
          </span>
          <span className="num">
            Data as of {formatDate(o.as_of)} · scores {scores.definition_version}
          </span>
        </div>
      </Card>
    </>
  );
}
