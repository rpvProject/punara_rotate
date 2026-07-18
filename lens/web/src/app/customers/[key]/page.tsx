"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, getCustomer, type CustomerDetail } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { formatDate, formatINR, labelize } from "@/lib/format";
import { CiqDial } from "@/components/charts";
import {
  Card,
  ChurnBandBadge,
  ConsentBadge,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
  StageBadge,
  StatTile,
} from "@/components/ui";

/** Orders + tickets + reviews + NPS, one timeline, newest first. */
function timelineOf(c: CustomerDetail): { at: string; node: React.ReactNode }[] {
  const events: { at: string; node: React.ReactNode }[] = c.orders.map((o) => ({
    at: o.placed_at,
    node: (
      <>
        <span
          className={`absolute -left-[1.85rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-nightfall ${
            o.financial_status === "paid" || o.fulfillment_status === "delivered"
              ? "bg-teal"
              : o.financial_status === "refunded" || o.fulfillment_status === "rto"
                ? "bg-ember"
                : "bg-graphite"
          }`}
        />
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <span className="num text-sm text-bone">{o.order_number}</span>
            <span className="ml-3 text-xs text-graphite">{formatDate(o.placed_at)}</span>
            {o.cod && (
              <span className="ml-2 rounded border border-line px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted">
                COD
              </span>
            )}
          </div>
          <div className="num text-sm">
            <span className="text-bone">{formatINR(o.total_paise)}</span>
            <span className="ml-3 text-xs text-muted">
              {labelize(o.financial_status)} · {labelize(o.fulfillment_status)}
            </span>
          </div>
        </div>
      </>
    ),
  }));

  for (const t of c.tickets ?? []) {
    events.push({
      at: t.opened_at,
      node: (
        <>
          <span className="absolute -left-[1.85rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-nightfall bg-marigold" />
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <span className="text-sm text-bone">Ticket · {labelize(t.category)}</span>
              <span className="ml-3 text-xs text-graphite">{formatDate(t.opened_at)}</span>
            </div>
            <div className="text-xs text-muted">
              {labelize(t.status)}
              {t.resolved_at && ` · resolved ${formatDate(t.resolved_at)}`}
              {t.csat != null && <span className="num"> · CSAT {t.csat}/5</span>}
            </div>
          </div>
        </>
      ),
    });
  }

  for (const r of c.reviews ?? []) {
    events.push({
      at: r.submitted_at,
      node: (
        <>
          <span
            className={`absolute -left-[1.85rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-nightfall ${
              r.rating >= 4 ? "bg-teal" : r.rating <= 2 ? "bg-ember" : "bg-graphite"
            }`}
          />
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <span className="text-sm text-bone">
                Review · <span className="num">{r.rating}/5</span>
                {r.title && <span className="ml-2 text-muted">“{r.title}”</span>}
              </span>
              <span className="ml-3 text-xs text-graphite">
                {formatDate(r.submitted_at)}
              </span>
            </div>
            {r.verified && <span className="text-xs text-muted">verified</span>}
          </div>
        </>
      ),
    });
  }

  for (const n of c.nps ?? []) {
    events.push({
      at: n.responded_at,
      node: (
        <>
          <span
            className={`absolute -left-[1.85rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-nightfall ${
              n.score >= 9 ? "bg-teal" : n.score <= 6 ? "bg-ember" : "bg-graphite"
            }`}
          />
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <span className="text-sm text-bone">
                NPS · <span className="num">{n.score}/10</span>
              </span>
              <span className="ml-3 text-xs text-graphite">
                {formatDate(n.responded_at)}
              </span>
            </div>
            <span className="text-xs text-muted">
              {n.score >= 9 ? "promoter" : n.score <= 6 ? "detractor" : "passive"}
            </span>
          </div>
        </>
      ),
    });
  }

  return events.sort((a, b) => (a.at < b.at ? 1 : -1));
}

export default function CustomerDetailPage() {
  const params = useParams<{ key: string }>();
  const key = Number(params.key);

  const { data, loading, offline, error, retry } = useApi(
    async (t) => {
      try {
        return await getCustomer(t.id, key);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    [key],
  );

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={3} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error) return <ErrorPanel message={error} />;
  if (!data)
    return (
      <>
        <EmptyState note={`Customer #${key} not found.`} />
        <p className="mt-4 text-center">
          <Link href="/customers" className="text-sm text-muted hover:text-marigold">
            &larr; Back to customers
          </Link>
        </p>
      </>
    );

  const c = data;
  const events = timelineOf(c);

  return (
    <>
      <div className="mb-2">
        <Link href="/customers" className="text-xs text-graphite hover:text-marigold">
          &larr; Customers
        </Link>
      </div>
      <PageHeader
        title={c.name || `Customer #${c.id}`}
        sub={`${c.email} · ${c.phone}`}
        right={
          <div className="flex items-center gap-2">
            <StageBadge stage={c.lifecycle_stage} />
            <span className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted">
              {labelize(c.rfm_segment)}
            </span>
            {c.prediction && <ChurnBandBadge band={c.prediction.churn_band} />}
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Orders" value={String(c.orders_count)} />
        <StatTile label="LTV to date" value={formatINR(c.total_spent_paise)} />
        <StatTile label="First order" value={formatDate(c.first_order_at)} />
        <StatTile label="Last order" value={formatDate(c.last_order_at)} />
      </div>

      {c.prediction !== undefined && (
        <Card
          title={
            c.prediction
              ? `Prediction · model ${c.prediction.model_version}`
              : "Prediction"
          }
          className="mt-4"
        >
          {c.prediction ? (
            <div className="grid items-center gap-4 sm:grid-cols-2 md:grid-cols-4">
              <CiqDial
                value={c.prediction.p_alive * 100}
                display={c.prediction.p_alive.toFixed(2)}
                label="P(ALIVE)"
              />
              <StatTile
                label="Expected orders (90d)"
                value={c.prediction.expected_orders_90d.toFixed(2)}
              />
              <StatTile
                label="Predicted 12-mo LTV"
                value={formatINR(c.prediction.ltv_12m_paise)}
              />
              <div className="px-1">
                <div className="text-xs font-medium uppercase tracking-[0.14em] text-muted">
                  Churn band
                </div>
                <div className="mt-2">
                  <ChurnBandBadge band={c.prediction.churn_band} />
                </div>
                <div className="num mt-2 text-xs text-graphite">
                  scored {formatDate(c.prediction.scored_at)}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-graphite">
              No prediction yet — the nightly ML run writes one.
            </p>
          )}
        </Card>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card title="Consent">
          <div className="flex flex-wrap gap-2">
            {(Object.entries(c.consent) as [string, boolean][]).map(([ch, on]) => (
              <ConsentBadge key={ch} channel={ch} on={on} />
            ))}
          </div>
        </Card>
        <Card title="Identities">
          <dl className="space-y-1.5">
            {c.identities.map((id) => (
              <div
                key={`${id.identity_type}:${id.identity_value}`}
                className="flex justify-between gap-4 text-sm"
              >
                <dt className="text-muted">{labelize(id.identity_type)}</dt>
                <dd className="num text-bone">{id.identity_value}</dd>
              </div>
            ))}
            {c.identities.length === 0 && (
              <div className="text-xs text-graphite">No resolved identities.</div>
            )}
          </dl>
        </Card>
      </div>

      <Card title="Timeline" className="mt-4">
        {events.length ? (
          <ol className="relative ml-2 space-y-4 border-l border-line pl-6">
            {events.map((e, i) => (
              <li key={i} className="relative">
                {e.node}
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState note="No activity on record." />
        )}
      </Card>
    </>
  );
}
