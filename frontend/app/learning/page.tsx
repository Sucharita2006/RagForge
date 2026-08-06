"use client";

import { useCallback, useEffect, useState } from "react";

interface ModelRow {
  id: string;
  kind: string;
  base_model: string;
  artifact_path: string | null;
  train_config: Record<string, unknown>;
  eval_metrics: Record<string, unknown> | null;
  status: string;
  promoted_at: string | null;
  created_at: string;
}

interface FeedbackRow {
  id: string;
  answer_id: string;
  rating: number;
  correction: string | null;
  created_at: string;
}

interface FailureCluster {
  id: string;
  window: string;
  cluster_label: string;
  size: number;
  sample_query_ids: string[];
  suggested_action: string;
  created_at: string;
}

interface EvalRun {
  id: string;
  name: string;
  status: string;
  started_at: string;
}

interface GateMetric {
  delta: number;
  ci_low: number;
  ci_high: number;
  n: number;
  significant: boolean;
  improved: boolean;
}

interface PromoteResult {
  promoted: boolean;
  improved_metrics: string[];
  gate: Record<string, GateMetric>;
  reason: string | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STATUS_STYLES: Record<string, string> = {
  active: "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200",
  candidate: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  retired: "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400",
};

const LABEL_STYLES: Record<string, string> = {
  retrieval_miss: "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200",
  generation_error: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
  parsing_gap: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  knowledge_gap: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
};

export default function Learning() {
  const [models, setModels] = useState<ModelRow[]>([]);
  const [feedback, setFeedback] = useState<FeedbackRow[]>([]);
  const [clusters, setClusters] = useState<FailureCluster[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [promoting, setPromoting] = useState<string | null>(null);
  const [result, setResult] = useState<PromoteResult | null>(null);
  const [runActive, setRunActive] = useState("");
  const [runCandidate, setRunCandidate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setError(null);
    try {
      const [m, f, c, r] = await Promise.all([
        fetch(`${API_URL}/api/models`),
        fetch(`${API_URL}/api/feedback`),
        fetch(`${API_URL}/api/failures/clusters`),
        fetch(`${API_URL}/api/eval/runs`),
      ]);
      if (!m.ok || !f.ok || !c.ok || !r.ok) throw new Error("Failed to load learning data");
      setModels((await m.json()) as ModelRow[]);
      setFeedback((await f.json()) as FeedbackRow[]);
      setClusters((await c.json()) as FailureCluster[]);
      setRuns(((await r.json()) as EvalRun[]).filter((x) => x.status === "completed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchAll();
  }, [fetchAll]);

  async function promote(modelId: string) {
    if (!runActive || !runCandidate) {
      setError("Select both an active-model run and a candidate run first");
      return;
    }
    setPromoting(modelId);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/api/models/${modelId}/promote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_active_id: runActive, run_candidate_id: runCandidate }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail ?? `Request failed: ${res.status}`);
      setResult(body as PromoteResult);
      await fetchAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setPromoting(null);
    }
  }

  async function startFinetune() {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/finetune/reranker`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ epochs: 1, batch_size: 32 }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setError("Fine-tune queued — it runs in the worker; refresh in a few minutes.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Learning</h1>
        <p className="text-sm text-neutral-500">
          Feedback, failure clusters, and the model registry. A candidate is promoted{" "}
          <strong>only</strong> if its ΔNDCG@10 / Δhit-rate 95% CI excludes zero (SPEC.md §3.5).
        </p>
      </div>

      {error && <p className="text-sm text-amber-600">{error}</p>}

      <div className="flex flex-col gap-3 rounded border border-neutral-200 p-4 dark:border-neutral-800">
        <h2 className="text-sm font-medium">A/B runs used by the promotion gate</h2>
        <div className="flex flex-col gap-2 md:flex-row">
          <select
            className="flex-1 rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={runActive}
            onChange={(e) => setRunActive(e.target.value)}
          >
            <option value="">Run for ACTIVE model...</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <select
            className="flex-1 rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={runCandidate}
            onChange={(e) => setRunCandidate(e.target.value)}
          >
            <option value="">Run for CANDIDATE model...</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <button
            onClick={startFinetune}
            className="rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700"
          >
            Train new candidate
          </button>
        </div>
      </div>

      {result && (
        <div
          className={`rounded border p-4 ${
            result.promoted
              ? "border-green-300 bg-green-50 dark:border-green-900 dark:bg-green-950/40"
              : "border-amber-300 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/40"
          }`}
        >
          <h3 className="font-medium">
            {result.promoted ? "Promoted" : "Promotion refused by the gate"}
          </h3>
          {result.reason && <p className="mt-1 text-sm">{result.reason}</p>}
          {result.improved_metrics.length > 0 && (
            <p className="mt-1 text-sm">Improved: {result.improved_metrics.join(", ")}</p>
          )}
          {Object.keys(result.gate).length > 0 && (
            <table className="mt-2 w-full border-collapse text-xs">
              <thead>
                <tr className="text-left">
                  <th className="py-1">Metric</th>
                  <th className="py-1 text-right">Δ</th>
                  <th className="py-1 text-right">95% CI</th>
                  <th className="py-1 text-right">n</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.gate).map(([metric, g]) => (
                  <tr key={metric}>
                    <td className="py-1 font-mono">{metric}</td>
                    <td className="py-1 text-right tabular-nums">
                      {g.delta >= 0 ? "+" : ""}
                      {g.delta.toFixed(4)}
                    </td>
                    <td className="py-1 text-right font-mono tabular-nums">
                      [{g.ci_low.toFixed(4)}, {g.ci_high.toFixed(4)}]
                    </td>
                    <td className="py-1 text-right tabular-nums">{g.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div className="overflow-x-auto">
        <h2 className="mb-2 text-sm font-medium">Model registry</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
              <th className="p-2">Kind</th>
              <th className="p-2">Base model</th>
              <th className="p-2">Trained on</th>
              <th className="p-2">Status</th>
              <th className="p-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.id} className="border-b border-neutral-100 dark:border-neutral-900">
                <td className="p-2 font-mono">{m.kind}</td>
                <td className="max-w-[240px] truncate p-2" title={m.artifact_path ?? m.base_model}>
                  {m.base_model}
                </td>
                <td className="p-2 tabular-nums text-neutral-500">
                  {typeof m.train_config.n_examples === "number"
                    ? `${m.train_config.n_examples} examples`
                    : "—"}
                </td>
                <td className="p-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_STYLES[m.status]}`}
                  >
                    {m.status}
                  </span>
                </td>
                <td className="p-2">
                  {m.status === "candidate" && (
                    <button
                      onClick={() => promote(m.id)}
                      disabled={promoting === m.id}
                      className="rounded bg-neutral-900 px-2 py-1 text-xs text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
                    >
                      {promoting === m.id ? "Testing..." : "Run gate & promote"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {clusters.length > 0 && (
        <div className="overflow-x-auto">
          <h2 className="mb-2 text-sm font-medium">Failure clusters</h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                <th className="p-2">Label</th>
                <th className="p-2 text-right">Size</th>
                <th className="p-2">Suggested action</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map((c) => (
                <tr key={c.id} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="p-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs font-medium ${LABEL_STYLES[c.cluster_label] ?? ""}`}
                    >
                      {c.cluster_label}
                    </span>
                  </td>
                  <td className="p-2 text-right tabular-nums">{c.size}</td>
                  <td className="p-2 text-neutral-500">{c.suggested_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="overflow-x-auto">
        <h2 className="mb-2 text-sm font-medium">Recent feedback ({feedback.length})</h2>
        {feedback.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No feedback yet — rate an answer in the Playground.
          </p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                <th className="p-2">Rating</th>
                <th className="p-2">Correction</th>
                <th className="p-2">When</th>
              </tr>
            </thead>
            <tbody>
              {feedback.map((f) => (
                <tr key={f.id} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="p-2">{f.rating > 0 ? "👍" : "👎"}</td>
                  <td className="max-w-[400px] truncate p-2 text-neutral-500">
                    {f.correction ?? "—"}
                  </td>
                  <td className="p-2 text-neutral-500">
                    {new Date(f.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
