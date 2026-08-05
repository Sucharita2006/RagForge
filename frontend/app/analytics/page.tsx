"use client";

import { useCallback, useEffect, useState } from "react";

interface LatencyPercentiles {
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

interface AnalyticsBucket {
  bucket_start: string;
  query_count: number;
  p50_ms: number;
  p95_ms: number;
  cache_hit_rate: number;
  abstention_rate: number;
  cost_usd: number;
}

interface AnalyticsSummary {
  window_hours: number;
  query_count: number;
  latency: LatencyPercentiles;
  cache_hit_rate: number;
  abstention_rate: number;
  mean_confidence: number | null;
  total_cost_usd: number;
  cost_per_query_usd: number;
  buckets: AnalyticsBucket[];
  by_span_kind: Record<string, LatencyPercentiles>;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WINDOWS = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 24 * 7 },
  { label: "30d", hours: 24 * 30 },
];

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="text-xs uppercase text-neutral-500">{label}</div>
      <div className="font-mono text-lg">{value}</div>
      {hint && <div className="text-xs text-neutral-400">{hint}</div>}
    </div>
  );
}

/** Minimal inline bar chart — avoids pulling a charting dependency into the
 *  bundle for what is a handful of buckets. */
function BucketBars({ buckets }: { buckets: AnalyticsBucket[] }) {
  if (buckets.length === 0) return null;
  const maxP95 = Math.max(...buckets.map((b) => b.p95_ms), 1);
  return (
    <div className="flex h-32 items-end gap-1">
      {buckets.map((b) => (
        <div
          key={b.bucket_start}
          className="flex-1 rounded-t bg-violet-500/70 hover:bg-violet-500"
          style={{ height: `${Math.max(2, (b.p95_ms / maxP95) * 100)}%` }}
          title={`${new Date(b.bucket_start).toLocaleString()}\n${b.query_count} queries\np50 ${b.p50_ms.toFixed(0)} ms · p95 ${b.p95_ms.toFixed(0)} ms`}
        />
      ))}
    </div>
  );
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [windowHours, setWindowHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/analytics/summary?window_hours=${windowHours}`);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setData((await res.json()) as AnalyticsSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, [windowHours]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSummary();
  }, [fetchSummary]);

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Analytics</h1>
          <p className="text-sm text-neutral-500">
            Latency, cost, cache and abstention rates over time (SPEC.md §3.8).
          </p>
        </div>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              onClick={() => setWindowHours(w.hours)}
              className={`rounded px-2 py-1 text-xs ${
                windowHours === w.hours
                  ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                  : "border border-neutral-300 dark:border-neutral-700"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading && <p className="text-sm text-neutral-500">Loading...</p>}

      {data && data.query_count === 0 && !loading && (
        <p className="text-sm text-neutral-500">
          No queries in this window. Run one from the Playground.
        </p>
      )}

      {data && data.query_count > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard label="Queries" value={String(data.query_count)} />
            <StatCard
              label="p50 / p95 latency"
              value={`${(data.latency.p50_ms / 1000).toFixed(1)}s / ${(data.latency.p95_ms / 1000).toFixed(1)}s`}
              hint={`p99 ${(data.latency.p99_ms / 1000).toFixed(1)}s`}
            />
            <StatCard
              label="Cache hit rate"
              value={`${(data.cache_hit_rate * 100).toFixed(0)}%`}
            />
            <StatCard
              label="Abstention rate"
              value={`${(data.abstention_rate * 100).toFixed(0)}%`}
              hint={
                data.mean_confidence !== null
                  ? `mean confidence ${data.mean_confidence.toFixed(2)}`
                  : undefined
              }
            />
            <StatCard label="Total cost" value={`$${data.total_cost_usd.toFixed(4)}`} />
            <StatCard
              label="Cost / query"
              value={`$${data.cost_per_query_usd.toFixed(6)}`}
              hint="$0 = self-hosted"
            />
          </div>

          {data.buckets.length > 0 && (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">p95 latency over time</h2>
              <BucketBars buckets={data.buckets} />
              <p className="text-xs text-neutral-400">
                {data.buckets.length} buckets · hover a bar for detail
              </p>
            </div>
          )}

          {Object.keys(data.by_span_kind).length > 0 && (
            <div className="overflow-x-auto">
              <h2 className="mb-2 text-sm font-medium">Latency by pipeline stage</h2>
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                    <th className="p-2">Span kind</th>
                    <th className="p-2 text-right">p50</th>
                    <th className="p-2 text-right">p95</th>
                    <th className="p-2 text-right">p99</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.by_span_kind).map(([kind, p]) => (
                    <tr
                      key={kind}
                      className="border-b border-neutral-100 dark:border-neutral-900"
                    >
                      <td className="p-2 font-mono">{kind}</td>
                      <td className="p-2 text-right tabular-nums">{p.p50_ms.toFixed(0)} ms</td>
                      <td className="p-2 text-right tabular-nums">{p.p95_ms.toFixed(0)} ms</td>
                      <td className="p-2 text-right tabular-nums">{p.p99_ms.toFixed(0)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}
