"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ApiError,
  getScoreHistory,
  getScores,
  type ScoreHistoryPoint,
  type ScoresPayload,
} from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { bandColor, formatDate, formatINR, labelize } from "@/lib/format";
import { ScoreHistoryLine } from "@/components/charts";
import {
  Card,
  EmptyState,
  ErrorPanel,
  OfflinePanel,
  PageHeader,
  Skeleton,
} from "@/components/ui";

const VALID = [
  "gravity",
  "flow",
  "signal",
  "watertight",
  "vitals",
  "velocity",
  "autopilot",
  "pulse",
  "altitude",
  "ciq",
  "ciq_partial",
];

export default function ScoreHistoryPage() {
  const params = useParams<{ name: string }>();
  const name = params.name;

  const { data, loading, offline, error, retry } = useApi<{
    history: ScoreHistoryPoint[];
    scores: ScoresPayload;
  } | null>(
    async (t) => {
      if (!VALID.includes(name)) return null;
      try {
        const [history, scores] = await Promise.all([
          getScoreHistory(t.id, name),
          getScores(t.id),
        ]);
        return { history, scores };
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    [name],
  );

  if (offline) return <OfflinePanel retry={retry} />;
  if (loading) return <Skeleton blocks={2} />;
  if (error === "no tenants")
    return <EmptyState note="No tenants yet — seed the demo tenant first." />;
  if (error) return <ErrorPanel message={error} />;
  if (!data)
    return (
      <>
        <EmptyState note={`No score named "${name}".`} />
        <p className="mt-4 text-center">
          <Link href="/" className="text-sm text-muted hover:text-marigold">
            &larr; Back to overview
          </Link>
        </p>
      </>
    );

  const { history, scores } = data;
  const latest = scores.scores.find((s) => s.score === name);
  const value = latest?.value ?? history.at(-1)?.value ?? null;
  const first = history[0]?.value;
  const delta = value !== null && first !== undefined ? value - first : null;

  return (
    <>
      <div className="mb-2">
        <Link href="/" className="text-xs text-graphite hover:text-marigold">
          &larr; Overview
        </Link>
      </div>
      <PageHeader
        title={`${labelize(name)} score`}
        sub={`Definition ${scores.definition_version} · recomputed by the nightly pipeline`}
        right={
          value !== null ? (
            <div className="text-right">
              <div className="num text-4xl" style={{ color: bandColor(value) }}>
                {value.toFixed(1)}
              </div>
              {delta !== null && (
                <div className={`num text-xs ${delta >= 0 ? "text-teal" : "text-ember"}`}>
                  {delta >= 0 ? "+" : ""}
                  {delta.toFixed(1)} since {formatDate(history[0].computed_at)}
                </div>
              )}
            </div>
          ) : undefined
        }
      />

      <Card title="History">
        {history.length ? (
          <ScoreHistoryLine data={history} />
        ) : (
          <EmptyState note="No score runs yet — run the nightly pipeline." />
        )}
      </Card>

      {latest && Object.keys(latest.components).length > 0 && (
        <Card title="Latest components" className="mt-4">
          <dl className="space-y-2.5">
            {Object.entries(latest.components).map(([k, v]) => (
              <div key={k} className="flex items-center gap-3 text-sm">
                <dt className="w-56 shrink-0 truncate text-muted" title={labelize(k)}>
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
                    <dd className="h-1.5 flex-1 rounded-full bg-line">
                      <div
                        className="h-1.5 rounded-full"
                        style={{
                          width: `${Math.max(0, Math.min(100, v))}%`,
                          background: bandColor(v),
                        }}
                      />
                    </dd>
                    <dd className="num w-12 text-right text-bone">{v.toFixed(1)}</dd>
                  </>
                )}
              </div>
            ))}
          </dl>
        </Card>
      )}
    </>
  );
}
