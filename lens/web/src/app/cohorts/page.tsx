"use client";

import { useState } from "react";
import { getCohorts, type Cohort } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import {
  formatCount,
  formatINRCompact,
  formatMonth,
  formatPct,
} from "@/lib/format";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
} from "@/components/ui";

type Mode = "customers" | "revenue";

function cellShade(intensity: number): string {
  // sequential single-hue: transparent -> Loop Teal
  return `rgba(15, 162, 132, ${0.08 + 0.72 * Math.max(0, Math.min(1, intensity))})`;
}

function Heatmap({ cohorts, mode }: { cohorts: Cohort[]; mode: Mode }) {
  const maxM = Math.max(...cohorts.map((c) => Math.max(...c.cells.map((x) => x.months_since))));
  // scale on months_since >= 1 so M0 (100%) doesn't flatten the ramp
  const later = cohorts.flatMap((c) => c.cells.filter((x) => x.months_since >= 1));
  const maxVal = Math.max(
    1e-9,
    ...later.map((x) => (mode === "customers" ? x.retention_rate : x.repeat_revenue_paise)),
  );

  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-fit gap-px text-[11px]"
        style={{ gridTemplateColumns: `7rem 3.5rem repeat(${maxM + 1}, 3.5rem)` }}
      >
        <div className="px-2 py-1.5 text-muted">Cohort</div>
        <div className="num px-2 py-1.5 text-right text-muted">Size</div>
        {Array.from({ length: maxM + 1 }, (_, m) => (
          <div key={m} className="num px-1 py-1.5 text-center text-graphite">
            M{m}
          </div>
        ))}
        {cohorts.map((c) => {
          const byM = new Map(c.cells.map((x) => [x.months_since, x]));
          return (
            <div key={c.cohort_month} className="contents">
              <div className="num px-2 py-1.5 text-muted">{formatMonth(c.cohort_month)}</div>
              <div className="num px-2 py-1.5 text-right text-bone">
                {formatCount(c.cohort_size)}
              </div>
              {Array.from({ length: maxM + 1 }, (_, m) => {
                const cell = byM.get(m);
                if (!cell)
                  return <div key={m} className="rounded-[3px] bg-panel/40" />;
                const val =
                  mode === "customers" ? cell.retention_rate : cell.repeat_revenue_paise;
                const intensity = m === 0 ? 1 : val / maxVal;
                return (
                  <div key={m} className="group relative">
                    <div
                      className="num cursor-default rounded-[3px] px-1 py-1.5 text-center text-bone/90"
                      style={{
                        background: m === 0 ? "rgba(90,98,114,0.25)" : cellShade(intensity),
                      }}
                    >
                      {mode === "customers"
                        ? formatPct(cell.retention_rate, cell.retention_rate >= 1 ? 0 : 1)
                        : formatINRCompact(cell.repeat_revenue_paise)}
                    </div>
                    {/* hover detail */}
                    <div className="num pointer-events-none absolute left-1/2 top-full z-10 hidden w-44 -translate-x-1/2 rounded border border-line bg-nightfall/95 p-2.5 text-left text-[11px] shadow-lg group-hover:block">
                      <div className="mb-1 text-graphite">
                        {formatMonth(c.cohort_month)} · month {m}
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Active</span>
                        <span className="text-bone">{formatCount(cell.active_customers)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Retention</span>
                        <span className="text-bone">{formatPct(cell.retention_rate)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Repeat rev</span>
                        <span className="text-teal">
                          {formatINRCompact(cell.repeat_revenue_paise)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function CohortsPage() {
  const [mode, setMode] = useState<Mode>("customers");
  const { data, loading, offline, error, retry } = useApi(
    (t) => getCohorts(t.id),
    [],
  );

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={2} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error || !data) return <ErrorPanel message={error ?? "no data"} />;

  const cohorts = data.cohorts;

  return (
    <>
      <PageHeader
        title="Cohort retention"
        sub="Acquisition month × months since first order"
        right={
          <div className="flex rounded border border-line text-xs">
            {(["customers", "revenue"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1.5 transition-colors ${
                  mode === m ? "bg-panel2 text-bone" : "text-muted hover:text-bone"
                }`}
              >
                {m === "customers" ? "Customers %" : "Revenue"}
              </button>
            ))}
          </div>
        }
      />
      <Card>
        {cohorts.length ? (
          <Heatmap cohorts={cohorts} mode={mode} />
        ) : (
          <EmptyState note="No cohorts yet — run the nightly pipeline." />
        )}
      </Card>
      <p className="mt-4 text-xs text-graphite">
        Colour scales within the view: deepest teal is the strongest{" "}
        {mode === "customers" ? "retention rate" : "repeat revenue"} after month
        0. Hover any cell for detail.
      </p>
    </>
  );
}
