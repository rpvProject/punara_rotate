"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { getCustomers } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { formatCount, formatDate, formatINR, labelize } from "@/lib/format";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
  StageBadge,
} from "@/components/ui";

const SEGMENTS = [
  "champions",
  "loyal",
  "potential_loyalist",
  "new",
  "promising",
  "needs_attention",
  "about_to_sleep",
  "at_risk",
  "cant_lose",
  "hibernating",
];

const PAGE_SIZE = 50;

function CustomersInner() {
  const router = useRouter();
  const params = useSearchParams();
  const segment = params.get("segment") ?? "";
  const [page, setPage] = useState(1);

  const { data, loading, offline, error, retry } = useApi(
    (t) => getCustomers(t.id, { segment: segment || undefined, page, page_size: PAGE_SIZE }),
    [segment, page],
  );

  if (offline) return <OfflinePanel retry={retry} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error) return <ErrorPanel message={error} />;

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader
        title="Customers"
        sub={data ? `${formatCount(data.total)} customers · pseudonymous list` : undefined}
        right={
          <select
            value={segment}
            onChange={(e) => {
              setPage(1);
              router.replace(
                e.target.value ? `/customers?segment=${e.target.value}` : "/customers",
              );
            }}
            className="rounded border border-line bg-panel px-3 py-1.5 text-sm text-bone"
            aria-label="Filter by RFM segment"
          >
            <option value="">All segments</option>
            {SEGMENTS.map((s) => (
              <option key={s} value={s}>
                {labelize(s)}
              </option>
            ))}
          </select>
        }
      />

      {loading || !data ? (
        <Skeleton blocks={2} />
      ) : data.data.length === 0 ? (
        <EmptyState
          note={
            segment
              ? `No customers in "${labelize(segment)}".`
              : "No customers yet — run the pipeline."
          }
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-graphite">
                  <th className="py-2 pr-3 font-medium">Customer</th>
                  <th className="py-2 pr-3 font-medium">Stage</th>
                  <th className="py-2 pr-3 font-medium">Segment</th>
                  <th className="num py-2 pr-3 text-right font-medium">Orders</th>
                  <th className="num py-2 pr-3 text-right font-medium">LTV to date</th>
                  <th className="num py-2 pr-3 text-right font-medium">Last order</th>
                  <th className="py-2 text-right font-medium">WhatsApp</th>
                </tr>
              </thead>
              <tbody>
                {data.data.map((c) => (
                  <tr
                    key={c.id}
                    className="cursor-pointer border-b border-line/50 transition-colors hover:bg-panel2"
                    onClick={() => router.push(`/customers/${c.id}`)}
                  >
                    <td className="py-2.5 pr-3">
                      <Link
                        href={`/customers/${c.id}`}
                        className="num text-bone underline-offset-2 hover:text-marigold"
                        onClick={(e) => e.stopPropagation()}
                      >
                        #{c.id}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-3">
                      <StageBadge stage={c.lifecycle_stage} />
                    </td>
                    <td className="py-2.5 pr-3 text-muted">{labelize(c.rfm_segment)}</td>
                    <td className="num py-2.5 pr-3 text-right">{c.orders_count}</td>
                    <td className="num py-2.5 pr-3 text-right">
                      {formatINR(c.total_spent_paise)}
                    </td>
                    <td className="num py-2.5 pr-3 text-right text-muted">
                      {formatDate(c.last_order_at)}
                      <span className="ml-2 text-graphite">({c.recency_days}d)</span>
                    </td>
                    <td className="py-2.5 text-right">
                      <span className={c.whatsapp_opted_in ? "text-teal" : "text-graphite"}>
                        {c.whatsapp_opted_in ? "✓" : "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between text-xs text-muted">
            <span className="num">
              Page {data.page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="rounded border border-line px-3 py-1.5 transition-colors hover:border-graphite hover:text-bone disabled:opacity-40 disabled:hover:border-line"
              >
                &larr; Prev
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded border border-line px-3 py-1.5 transition-colors hover:border-graphite hover:text-bone disabled:opacity-40 disabled:hover:border-line"
              >
                Next &rarr;
              </button>
            </div>
          </div>
        </Card>
      )}
    </>
  );
}

export default function CustomersPage() {
  return (
    <Suspense fallback={<Skeleton blocks={2} />}>
      <CustomersInner />
    </Suspense>
  );
}
