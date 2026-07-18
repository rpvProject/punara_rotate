"use client";

import Link from "next/link";
import { getRfm, type RfmCell } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import {
  formatCount,
  formatDate,
  formatINR,
  formatINRCompact,
  labelize,
} from "@/lib/format";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
} from "@/components/ui";

function Grid({ grid }: { grid: RfmCell[] }) {
  const byKey = new Map(grid.map((c) => [`${c.r_quintile}-${c.f_quintile}`, c]));
  const max = Math.max(1, ...grid.map((c) => c.customers));
  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-fit gap-1"
        style={{ gridTemplateColumns: "5.5rem repeat(5, minmax(4.5rem, 1fr))" }}
      >
        <div />
        {[1, 2, 3, 4, 5].map((f) => (
          <div key={f} className="num pb-1 text-center text-[11px] text-graphite">
            F{f}
          </div>
        ))}
        {[5, 4, 3, 2, 1].map((r) => (
          <div key={r} className="contents">
            <div className="num flex items-center text-[11px] text-graphite">
              R{r}
              {r === 5 && <span className="ml-1.5 text-muted">recent</span>}
              {r === 1 && <span className="ml-1.5 text-muted">lapsed</span>}
            </div>
            {[1, 2, 3, 4, 5].map((f) => {
              const cell = byKey.get(`${r}-${f}`);
              const n = cell?.customers ?? 0;
              return (
                <div key={f} className="group relative">
                  <div
                    className="num rounded px-2 py-3 text-center text-xs text-bone/90"
                    style={{
                      background: `rgba(15, 162, 132, ${0.06 + 0.7 * (n / max)})`,
                    }}
                  >
                    {n ? formatCount(n) : "·"}
                  </div>
                  {cell && (
                    <div className="num pointer-events-none absolute left-1/2 top-full z-10 hidden w-40 -translate-x-1/2 rounded border border-line bg-nightfall/95 p-2.5 text-[11px] shadow-lg group-hover:block">
                      <div className="mb-1 text-graphite">
                        R{r} × F{f}
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Customers</span>
                        <span className="text-bone">{formatCount(cell.customers)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Revenue</span>
                        <span className="text-teal">{formatINRCompact(cell.revenue_paise)}</span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-2 text-right text-[11px] text-graphite">
        frequency quintile &rarr;
      </div>
    </div>
  );
}

export default function SegmentsPage() {
  const { data, loading, offline, error, retry } = useApi((t) => getRfm(t.id), []);

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={2} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error || !data) return <ErrorPanel message={error ?? "no data"} />;

  const segments = [...data.segments].sort((a, b) => b.revenue_paise - a.revenue_paise);

  return (
    <>
      <PageHeader
        title="RFM segments"
        sub={`Recency × frequency quintiles · as of ${formatDate(data.as_of)}`}
      />
      <div className="grid gap-4 xl:grid-cols-5">
        <Card title="R × F grid" className="xl:col-span-2">
          {data.grid.length ? (
            <Grid grid={data.grid} />
          ) : (
            <EmptyState note="No RFM data yet — run the nightly pipeline." />
          )}
        </Card>
        <Card title="Segments" className="xl:col-span-3">
          {segments.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-graphite">
                    <th className="py-2 pr-3 font-medium">Segment</th>
                    <th className="num py-2 pr-3 text-right font-medium">Customers</th>
                    <th className="num py-2 pr-3 text-right font-medium">Revenue</th>
                    <th className="num py-2 pr-3 text-right font-medium">Recency</th>
                    <th className="num py-2 pr-3 text-right font-medium">Freq</th>
                    <th className="num py-2 text-right font-medium">Avg spend</th>
                  </tr>
                </thead>
                <tbody>
                  {segments.map((s) => (
                    <tr key={s.segment} className="border-b border-line/50">
                      <td className="py-2.5 pr-3">
                        <Link
                          href={`/customers?segment=${s.segment}`}
                          className="text-bone underline-offset-2 hover:text-marigold hover:underline"
                        >
                          {labelize(s.segment)}
                        </Link>
                      </td>
                      <td className="num py-2.5 pr-3 text-right">{formatCount(s.customers)}</td>
                      <td className="num py-2.5 pr-3 text-right">
                        {formatINRCompact(s.revenue_paise)}
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-muted">
                        {Math.round(s.avg_recency_days)}d
                      </td>
                      <td className="num py-2.5 pr-3 text-right text-muted">
                        {s.avg_frequency.toFixed(1)}
                      </td>
                      <td className="num py-2.5 text-right">{formatINR(s.avg_monetary_paise)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState note="No segments yet — run the nightly pipeline." />
          )}
        </Card>
      </div>
    </>
  );
}
