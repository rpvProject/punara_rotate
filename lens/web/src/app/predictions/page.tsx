"use client";

import Link from "next/link";
import { useState } from "react";
import { getPredictions } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import {
  formatCount,
  formatDate,
  formatINR,
  formatINRCompact,
  labelize,
} from "@/lib/format";
import { DecileBars } from "@/components/charts";
import {
  Card,
  ChurnBandBadge,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
  StageBadge,
  StatTile,
} from "@/components/ui";

const PAGE_SIZE = 50;

export default function PredictionsPage() {
  const [page, setPage] = useState(1);

  const { data, loading, offline, error, retry } = useApi(
    (t) => getPredictions(t.id, page, PAGE_SIZE),
    [page],
  );

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={3} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error) return <ErrorPanel message={error} />;
  if (!data)
    return (
      <>
        <PageHeader
          title="Predictions"
          sub="BG/NBD + Gamma-Gamma · churn risk and 12-month LTV per customer"
        />
        <EmptyState note="No predictions yet — the nightly ML run (python -m lens nightly) writes them." />
      </>
    );

  const p = data;
  const totalPages = Math.max(1, Math.ceil(p.total / p.page_size));

  return (
    <>
      <PageHeader
        title="Predictions"
        sub={`Model ${p.model_version} · ${formatCount(p.customers_scored)} customers scored · ${formatDate(p.scored_at)}`}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="High risk"
          value={formatCount(p.band_counts.high ?? 0)}
          tone="risk"
          sub={`${formatINRCompact(p.at_risk_ltv_paise)} 12-mo LTV at risk`}
        />
        <StatTile
          label="Medium risk"
          value={formatCount(p.band_counts.medium ?? 0)}
          tone="warn"
          sub="0.35 ≤ p(alive) < 0.65"
        />
        <StatTile
          label="Low risk"
          value={formatCount(p.band_counts.low ?? 0)}
          tone="good"
          sub="p(alive) ≥ 0.65"
        />
        <StatTile
          label="Expected orders (90d)"
          value={formatCount(Math.round(p.expected_orders_90d_total))}
          sub="sum across all customers"
        />
      </div>

      <Card title="12-month LTV — decile distribution" className="mt-4">
        {p.ltv_12m_deciles_paise.length ? (
          <>
            <DecileBars deciles={p.ltv_12m_deciles_paise} />
            <p className="mt-2 text-xs text-graphite">
              D1–D10: predicted 12-month LTV at each decile boundary across scored
              customers.
            </p>
          </>
        ) : (
          <EmptyState note="No LTV distribution in this run." />
        )}
      </Card>

      <Card title="Top risk — high band, most rupees first" className="mt-4">
        {p.top_risk.length === 0 ? (
          <EmptyState note="No high-risk customers in this run." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-graphite">
                    <th className="py-2 pr-3 font-medium">Customer</th>
                    <th className="py-2 pr-3 font-medium">Band</th>
                    <th className="num py-2 pr-3 text-right font-medium">P(alive)</th>
                    <th className="num py-2 pr-3 text-right font-medium">Orders 90d</th>
                    <th className="num py-2 pr-3 text-right font-medium">12-mo LTV</th>
                    <th className="num py-2 pr-3 text-right font-medium">Orders</th>
                    <th className="num py-2 pr-3 text-right font-medium">Last order</th>
                    <th className="py-2 font-medium">Segment</th>
                  </tr>
                </thead>
                <tbody>
                  {p.top_risk.map((r) => (
                    <tr key={r.customer_id} className="border-b border-line/50">
                      <td className="py-2.5 pr-3">
                        <Link
                          href={`/customers/${r.customer_id}`}
                          className="num text-bone underline-offset-2 hover:text-marigold"
                        >
                          #{r.customer_id}
                        </Link>
                      </td>
                      <td className="py-2.5 pr-3">
                        <ChurnBandBadge band={r.churn_band} />
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-ember">
                        {r.p_alive.toFixed(2)}
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-muted">
                        {r.expected_orders_90d.toFixed(2)}
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-bone">
                        {formatINR(r.ltv_12m_paise)}
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-muted">
                        {r.orders_count}
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-muted">
                        {formatDate(r.last_order_at ?? null)}
                      </td>
                      <td className="py-2.5">
                        <span className="mr-2 text-xs text-muted">
                          {labelize(r.rfm_segment)}
                        </span>
                        <StageBadge stage={r.lifecycle_stage} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between text-xs text-muted">
              <span className="num">
                Page {p.page} of {totalPages} · {formatCount(p.total)} high-risk
                customers
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((n) => n - 1)}
                  className="rounded border border-line px-3 py-1.5 transition-colors hover:border-graphite hover:text-bone disabled:opacity-40 disabled:hover:border-line"
                >
                  &larr; Prev
                </button>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage((n) => n + 1)}
                  className="rounded border border-line px-3 py-1.5 transition-colors hover:border-graphite hover:text-bone disabled:opacity-40 disabled:hover:border-line"
                >
                  Next &rarr;
                </button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
