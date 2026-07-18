"use client";

import { getExperiments, type Experiment } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { formatCount, formatDate, labelize } from "@/lib/format";
import { CadenceBars } from "@/components/charts";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
} from "@/components/ui";

const STATUS_ORDER = ["running", "concluded", "draft"];

/** Starts per month, gap months filled with 0, ascending. */
function cadence(exps: Experiment[]): { month: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const e of exps) {
    if (!e.started_at) continue;
    const m = e.started_at.slice(0, 7);
    counts.set(m, (counts.get(m) ?? 0) + 1);
  }
  if (counts.size === 0) return [];
  const months = [...counts.keys()].sort();
  const out: { month: string; count: number }[] = [];
  const [y0, m0] = months[0].split("-").map(Number);
  const [y1, m1] = months[months.length - 1].split("-").map(Number);
  for (let i = y0 * 12 + (m0 - 1); i <= y1 * 12 + (m1 - 1); i++) {
    const key = `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`;
    out.push({ month: key, count: counts.get(key) ?? 0 });
  }
  return out;
}

const DECISION_TONE: Record<string, string> = {
  shipped: "border-teal/40 text-teal",
  killed: "border-graphite text-graphite",
  inconclusive: "border-marigold/40 text-marigold",
};

function DecisionBadge({ decision }: { decision: string | null }) {
  if (!decision) return <span className="text-graphite">—</span>;
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs ${
        DECISION_TONE[decision] ?? "border-line text-muted"
      }`}
    >
      {labelize(decision)}
    </span>
  );
}

function ExperimentTable({ rows }: { rows: Experiment[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wider text-graphite">
            <th className="py-2 pr-3 font-medium">Experiment</th>
            <th className="py-2 pr-3 font-medium">Target</th>
            <th className="num py-2 pr-3 text-right font-medium">Started</th>
            <th className="num py-2 pr-3 text-right font-medium">Concluded</th>
            <th className="num py-2 pr-3 text-right font-medium">Sample</th>
            <th className="num py-2 pr-3 text-right font-medium">Lift</th>
            <th className="py-2 pr-3 text-center font-medium">Significant</th>
            <th className="py-2 font-medium">Decision</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id} className="border-b border-line/50">
              <td
                className="max-w-72 truncate py-2.5 pr-3 text-bone"
                title={e.hypothesis ?? e.name}
              >
                {e.name}
              </td>
              <td className="py-2.5 pr-3 text-muted">
                {e.score_target ? labelize(e.score_target) : "—"}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {formatDate(e.started_at)}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {formatDate(e.concluded_at)}
              </td>
              <td className="num py-2.5 pr-3 text-right text-muted">
                {e.sample_size != null ? formatCount(e.sample_size) : "—"}
              </td>
              <td
                className={`num py-2.5 pr-3 text-right ${
                  e.lift_pct == null
                    ? "text-graphite"
                    : e.lift_pct >= 0
                      ? "text-teal"
                      : "text-ember"
                }`}
              >
                {e.lift_pct != null
                  ? `${e.lift_pct >= 0 ? "+" : ""}${e.lift_pct.toFixed(1)}%`
                  : "—"}
              </td>
              <td className="py-2.5 pr-3 text-center">
                {e.significant == null ? (
                  <span className="text-graphite">—</span>
                ) : e.significant ? (
                  <span className="text-teal">✓</span>
                ) : (
                  <span className="text-muted">✗</span>
                )}
              </td>
              <td className="py-2.5">
                <DecisionBadge decision={e.decision} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ExperimentsPage() {
  const { data, loading, offline, error, retry } = useApi((t) =>
    getExperiments(t.id),
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
          title="Experiments"
          sub="The Loop Ledger — every test, its readout, and the decision"
        />
        <EmptyState note="Experiments endpoint not available on this API build." />
      </>
    );

  const exps = data;
  const concluded = exps.filter((e) => e.status === "concluded");
  const shipped = concluded.filter((e) => e.decision === "shipped").length;
  const killed = concluded.filter((e) => e.decision === "killed").length;
  const monthly = cadence(exps);

  return (
    <>
      <PageHeader
        title="Experiments"
        sub={
          exps.length
            ? `The Loop Ledger · ${exps.length} experiments · ${shipped} shipped / ${killed} killed`
            : "The Loop Ledger — every test, its readout, and the decision"
        }
      />

      {exps.length === 0 ? (
        <EmptyState note="No experiments yet — the Loop Ledger fills as tests ship." />
      ) : (
        <>
          <Card title="Cadence — experiments started per month">
            {monthly.length ? (
              <>
                <CadenceBars data={monthly} />
                <p className="mt-2 text-xs text-graphite">
                  Velocity commitment: 2 per month. Killed tests count — decided
                  beats undecided.
                </p>
              </>
            ) : (
              <EmptyState note="No dated experiments yet." />
            )}
          </Card>

          {STATUS_ORDER.map((status) => {
            const rows = exps.filter((e) => e.status === status);
            if (rows.length === 0) return null;
            return (
              <Card
                key={status}
                title={`${labelize(status)} (${rows.length})`}
                className="mt-4"
              >
                <ExperimentTable rows={rows} />
              </Card>
            );
          })}
        </>
      )}
    </>
  );
}
