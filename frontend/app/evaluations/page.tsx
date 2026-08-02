"use client";

import { useCallback, useEffect, useState } from "react";

interface MetricCI {
  mean: number;
  ci_low: number;
  ci_high: number;
  n: number;
}

interface EvalRun {
  id: string;
  name: string;
  dataset_version: string;
  status: string;
  metrics: Record<string, MetricCI> | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

interface EvalResult {
  id: string;
  question_id: string;
  question_type: string;
  metrics: Record<string, number | boolean>;
  retrieved: { candidates: { document_external_id: string | null; rerank_score: number | null }[] };
  answer: { text?: string; insufficient_context?: boolean };
  judge_notes: string | null;
}

interface EvalRunDetail extends EvalRun {
  results: EvalResult[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function fmtMetric(m: MetricCI | undefined): string {
  if (!m) return "—";
  return `${m.mean.toFixed(3)} [${m.ci_low.toFixed(3)}, ${m.ci_high.toFixed(3)}] (n=${m.n})`;
}

const KEY_METRICS = [
  "hit_rate",
  "reciprocal_rank",
  "ndcg@10",
  "faithfulness",
  "answer_correctness",
  "context_precision",
  "context_recall",
  "abstention_recall_unanswerable",
  "answered_precision",
];

export default function Evaluations() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selected, setSelected] = useState<EvalRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/eval/runs`);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setRuns((await res.json()) as EvalRun[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // fetch-on-mount with no data-fetching library in this project yet;
    // eslint-plugin-react-hooks' cascading-render warning doesn't apply here
    // since there's only ever one render pass for this initial load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchRuns();
  }, [fetchRuns]);

  async function selectRun(id: string) {
    setSelected(null);
    try {
      const res = await fetch(`${API_URL}/api/eval/runs/${id}`);
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setSelected((await res.json()) as EvalRunDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Evaluations</h1>
        <p className="text-sm text-neutral-500">
          Eval runs against the golden set (SPEC.md §3.7) — retrieval, faithfulness,
          answer-correctness, and abstention metrics with bootstrap 95% CIs.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading && <p className="text-sm text-neutral-500">Loading runs...</p>}

      {!loading && runs.length === 0 && (
        <p className="text-sm text-neutral-500">
          No eval runs yet. Trigger one via <code>POST /api/eval/run</code>.
        </p>
      )}

      {runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                <th className="p-2">Name</th>
                <th className="p-2">Dataset</th>
                <th className="p-2">Status</th>
                <th className="p-2 text-right">NDCG@10</th>
                <th className="p-2 text-right">Faithfulness</th>
                <th className="p-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => selectRun(run.id)}
                  className="cursor-pointer border-b border-neutral-100 hover:bg-neutral-50 dark:border-neutral-900 dark:hover:bg-neutral-900"
                >
                  <td className="p-2 font-medium">{run.name}</td>
                  <td className="p-2 text-neutral-500">{run.dataset_version}</td>
                  <td className="p-2">
                    <span
                      className={
                        run.status === "completed"
                          ? "text-green-600"
                          : run.status === "failed"
                            ? "text-red-600"
                            : "text-neutral-500"
                      }
                    >
                      {run.status}
                    </span>
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {run.metrics?.["ndcg@10"]?.mean.toFixed(3) ?? "—"}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {run.metrics?.["faithfulness"]?.mean.toFixed(3) ?? "—"}
                  </td>
                  <td className="p-2 text-neutral-500">
                    {new Date(run.started_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <div className="flex flex-col gap-4 border-t border-neutral-200 pt-6 dark:border-neutral-800">
          <h2 className="text-lg font-semibold">
            {selected.name} <span className="text-sm text-neutral-500">({selected.status})</span>
          </h2>
          {selected.error && <p className="text-sm text-red-600">{selected.error}</p>}

          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {KEY_METRICS.filter((k) => selected.metrics?.[k]).map((k) => (
              <div
                key={k}
                className="rounded border border-neutral-200 p-3 dark:border-neutral-800"
              >
                <div className="text-xs uppercase text-neutral-500">{k}</div>
                <div className="font-mono text-sm">{fmtMetric(selected.metrics?.[k])}</div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                  <th className="p-2">Question</th>
                  <th className="p-2">Type</th>
                  <th className="p-2">Answer preview</th>
                  <th className="p-2">Judge notes</th>
                </tr>
              </thead>
              <tbody>
                {selected.results.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-neutral-100 dark:border-neutral-900"
                  >
                    <td className="p-2 text-neutral-500">{r.question_id}</td>
                    <td className="p-2">{r.question_type}</td>
                    <td className="max-w-[280px] truncate p-2" title={r.answer.text ?? ""}>
                      {r.answer.insufficient_context
                        ? "(abstained)"
                        : (r.answer.text ?? "(retrieval-only)")}
                    </td>
                    <td className="max-w-[280px] truncate p-2 text-neutral-500" title={r.judge_notes ?? ""}>
                      {r.judge_notes ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  );
}
