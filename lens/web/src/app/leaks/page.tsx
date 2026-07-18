"use client";

import { getLeaks } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { formatCount, formatINR, formatINRCompact, formatPct, labelize } from "@/lib/format";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
} from "@/components/ui";

const LEAK_NOTES: Record<string, string> = {
  rto_cod: "COD orders returned to origin, net of recovered value",
  preventable_churn: "Expected-value gap of slipping customers vs run-rate",
  failed_payments: "Failed attempts on orders never subsequently paid",
  discount_abuse: "Discounting beyond 30% of subtotal, per order",
};

export default function LeaksPage() {
  const { data, loading, offline, error, retry } = useApi((t) => getLeaks(t.id), []);

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={2} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error || !data) return <ErrorPanel message={error ?? "no data"} />;

  const leaks = [...data.leaks].sort((a, b) => b.amount_paise - a.amount_paise);
  const max = Math.max(1, ...leaks.map((l) => l.amount_paise));

  return (
    <>
      <PageHeader
        title="Revenue leaks"
        sub={`Watertight leak map · trailing ${data.window_months} months`}
      />

      <Card>
        <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
          <div>
            <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted">
              Annualized leak
            </div>
            <div className="num mt-1 text-5xl text-ember">
              {formatINRCompact(data.annualized_paise)}
            </div>
          </div>
          <div className="num text-sm text-muted">
            {formatPct(data.revenue_share)} of revenue ·{" "}
            <span className="text-bone">{formatINR(data.total_paise)}</span> in window
          </div>
        </div>
      </Card>

      <Card title="Leak lines" className="mt-4">
        {leaks.length ? (
          <div className="space-y-5">
            {leaks.map((l) => (
              <div key={l.leak_type}>
                <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <span className="text-sm text-bone">{labelize(l.leak_type)}</span>
                    <span className="ml-3 text-xs text-graphite">
                      {LEAK_NOTES[l.leak_type] ?? ""}
                    </span>
                  </div>
                  <div className="num text-sm">
                    <span className="text-ember">{formatINRCompact(l.amount_paise)}</span>
                    <span className="ml-3 text-graphite">
                      {l.orders_affected > 0
                        ? `${formatCount(l.orders_affected)} orders`
                        : "modelled"}
                      {" · "}
                      {formatPct(l.revenue_share)} of revenue
                    </span>
                  </div>
                </div>
                <div className="h-4 rounded bg-line/60">
                  <div
                    className="h-4 rounded bg-ember/80"
                    style={{ width: `${Math.max(1.5, (l.amount_paise / max) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState note="No leaks quantified yet — run the nightly pipeline." />
        )}
      </Card>

      <p className="mt-4 text-xs text-graphite">
        Every line is a rupee-quantified, addressable loss — sealing them is the
        fastest Watertight gain. Fix ranked top-down.
      </p>
    </>
  );
}
