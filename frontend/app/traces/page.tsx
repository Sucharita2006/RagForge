"use client";

import { useCallback, useEffect, useState } from "react";

interface TraceSummary {
  trace_id: string;
  root_name: string;
  started_at: string;
  latency_ms: number;
  span_count: number;
  status: string;
  question: string | null;
  cache_hit: boolean | null;
  abstained: boolean | null;
  cost_usd: number | null;
}

interface Span {
  id: string;
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  kind: string;
  name: string;
  started_at: string;
  ended_at: string;
  latency_ms: number;
  attributes: Record<string, unknown>;
  status: string;
}

interface TraceDetail {
  trace_id: string;
  spans: Span[];
  question: string | null;
  total_latency_ms: number;
  total_cost_usd: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const KIND_COLORS: Record<string, string> = {
  CHAIN: "bg-neutral-400 dark:bg-neutral-500",
  RETRIEVER: "bg-blue-500",
  RERANKER: "bg-indigo-500",
  EMBEDDING: "bg-cyan-500",
  LLM: "bg-violet-500",
  EVALUATOR: "bg-emerald-500",
  GUARDRAIL: "bg-amber-500",
};

function Waterfall({ detail }: { detail: TraceDetail }) {
  const spans = detail.spans;
  if (spans.length === 0) return null;

  // Anchor every bar to the trace's own start so offsets are relative to the
  // request, not to epoch.
  const t0 = Math.min(...spans.map((s) => new Date(s.started_at).getTime()));
  const t1 = Math.max(...spans.map((s) => new Date(s.ended_at).getTime()));
  const totalMs = Math.max(1, t1 - t0);

  return (
    <div className="flex flex-col gap-1">
      {spans.map((span) => {
        const start = new Date(span.started_at).getTime() - t0;
        const width = Math.max(0.5, (span.latency_ms / totalMs) * 100);
        const offset = (start / totalMs) * 100;
        return (
          <div key={span.id} className="flex items-center gap-2 text-xs">
            <div className="w-40 shrink-0 truncate font-mono" title={span.name}>
              {span.name}
            </div>
            <div className="w-24 shrink-0">
              <span
                className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium text-white ${
                  KIND_COLORS[span.kind] ?? "bg-neutral-500"
                }`}
              >
                {span.kind}
              </span>
            </div>
            <div className="relative h-4 flex-1 rounded bg-neutral-100 dark:bg-neutral-900">
              <div
                className={`absolute h-4 rounded ${KIND_COLORS[span.kind] ?? "bg-neutral-500"}`}
                style={{ left: `${offset}%`, width: `${width}%` }}
                title={`${span.name}: ${span.latency_ms} ms`}
              />
            </div>
            <div className="w-20 shrink-0 text-right tabular-nums text-neutral-500">
              {span.latency_ms} ms
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SpanAttributes({ span }: { span: Span }) {
  const entries = Object.entries(span.attributes);
  if (entries.length === 0) return null;
  return (
    <details className="rounded border border-neutral-200 p-2 text-xs dark:border-neutral-800">
      <summary className="cursor-pointer font-medium">
        {span.name} <span className="text-neutral-500">({entries.length} attributes)</span>
      </summary>
      <table className="mt-2 w-full border-collapse">
        <tbody>
          {entries.map(([key, value]) => (
            <tr key={key} className="border-b border-neutral-100 dark:border-neutral-900">
              <td className="py-1 pr-3 font-mono text-neutral-500">{key}</td>
              <td className="py-1 break-all font-mono">{String(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

export default function Traces() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selected, setSelected] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTraces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/traces?limit=50`);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setTraces((await res.json()) as TraceSummary[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // fetch-on-mount; single render pass, so the cascading-render rule
    // doesn't apply here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchTraces();
  }, [fetchTraces]);

  async function selectTrace(traceId: string) {
    setSelected(null);
    try {
      const res = await fetch(`${API_URL}/api/traces/${traceId}`);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setSelected((await res.json()) as TraceDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Traces</h1>
        <p className="text-sm text-neutral-500">
          Every query&apos;s full span waterfall (SPEC.md §3.8) — step durations, token/cost per
          span, retrieved chunks with scores.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading && <p className="text-sm text-neutral-500">Loading traces...</p>}

      {!loading && traces.length === 0 && (
        <p className="text-sm text-neutral-500">
          No traces yet. Run a query from the Playground to generate one.
        </p>
      )}

      {traces.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                <th className="p-2">Question</th>
                <th className="p-2">Spans</th>
                <th className="p-2 text-right">Latency</th>
                <th className="p-2 text-right">Cost</th>
                <th className="p-2">Flags</th>
                <th className="p-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr
                  key={t.trace_id}
                  onClick={() => selectTrace(t.trace_id)}
                  className="cursor-pointer border-b border-neutral-100 hover:bg-neutral-50 dark:border-neutral-900 dark:hover:bg-neutral-900"
                >
                  <td className="max-w-[320px] truncate p-2" title={t.question ?? t.trace_id}>
                    {t.question ?? <span className="font-mono text-neutral-500">{t.trace_id}</span>}
                  </td>
                  <td className="p-2 tabular-nums text-neutral-500">{t.span_count}</td>
                  <td className="p-2 text-right tabular-nums">{t.latency_ms} ms</td>
                  <td className="p-2 text-right tabular-nums text-neutral-500">
                    {t.cost_usd !== null ? `$${t.cost_usd.toFixed(6)}` : "—"}
                  </td>
                  <td className="p-2">
                    {t.cache_hit && (
                      <span className="mr-1 rounded bg-cyan-100 px-1.5 py-0.5 text-xs text-cyan-900 dark:bg-cyan-950 dark:text-cyan-200">
                        cached
                      </span>
                    )}
                    {t.abstained && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                        abstained
                      </span>
                    )}
                  </td>
                  <td className="p-2 text-neutral-500">
                    {new Date(t.started_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="flex flex-col gap-4 border-t border-neutral-200 pt-6 dark:border-neutral-800">
          <div>
            <h2 className="text-lg font-semibold">{selected.question ?? "Trace detail"}</h2>
            <p className="font-mono text-xs text-neutral-500">{selected.trace_id}</p>
            <p className="mt-1 text-sm text-neutral-500">
              {selected.spans.length} spans · {selected.total_latency_ms} ms total ·{" "}
              ${selected.total_cost_usd.toFixed(6)}
            </p>
          </div>

          <Waterfall detail={selected} />

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">Span attributes</h3>
            {selected.spans.map((span) => (
              <SpanAttributes key={span.id} span={span} />
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
