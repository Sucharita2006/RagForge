"use client";

import { useCallback, useEffect, useState } from "react";

interface MetricDelta {
  delta: number;
  ci_low: number;
  ci_high: number;
  n: number;
  significant: boolean;
  improved: boolean;
  lower_is_better: boolean;
  mean_a: number;
  mean_b: number;
}

interface Experiment {
  id: string;
  name: string;
  config_a: Record<string, unknown>;
  config_b: Record<string, unknown>;
  run_a_id: string;
  run_b_id: string;
  deltas: Record<string, MetricDelta> | null;
  created_at: string;
}

interface EvalRun {
  id: string;
  name: string;
  status: string;
  started_at: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function VerdictBadge({ metric }: { metric: MetricDelta }) {
  if (!metric.significant) {
    return (
      <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400">
        no significant change
      </span>
    );
  }
  return metric.improved ? (
    <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-900 dark:bg-green-950 dark:text-green-200">
      improved
    </span>
  ) : (
    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-900 dark:bg-red-950 dark:text-red-200">
      regressed
    </span>
  );
}

export default function Experiments() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [name, setName] = useState("");
  const [runA, setRunA] = useState("");
  const [runB, setRunB] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setError(null);
    try {
      const [expRes, runRes] = await Promise.all([
        fetch(`${API_URL}/api/experiments`),
        fetch(`${API_URL}/api/eval/runs`),
      ]);
      if (!expRes.ok || !runRes.ok) throw new Error("Failed to load experiments or runs");
      setExperiments((await expRes.json()) as Experiment[]);
      setRuns(((await runRes.json()) as EvalRun[]).filter((r) => r.status === "completed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchAll();
  }, [fetchAll]);

  async function createExperiment(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !runA || !runB || creating) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/experiments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, run_a_id: runA, run_b_id: runB }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Request failed: ${res.status}`);
      }
      const created = (await res.json()) as Experiment;
      setSelected(created);
      setName("");
      await fetchAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Experiments</h1>
        <p className="text-sm text-neutral-500">
          A/B compare two eval runs with paired bootstrap 95% CIs. A metric counts as changed only
          when its CI excludes zero (SPEC.md §3.5 promotion gate).
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <form
        onSubmit={createExperiment}
        className="flex flex-col gap-3 rounded border border-neutral-200 p-4 dark:border-neutral-800"
      >
        <h2 className="text-sm font-medium">New comparison</h2>
        <input
          className="rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="Experiment name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div className="flex flex-col gap-2 md:flex-row">
          <select
            className="flex-1 rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={runA}
            onChange={(e) => setRunA(e.target.value)}
          >
            <option value="">Baseline run (A)...</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · {new Date(r.started_at).toLocaleDateString()}
              </option>
            ))}
          </select>
          <select
            className="flex-1 rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
            value={runB}
            onChange={(e) => setRunB(e.target.value)}
          >
            <option value="">Candidate run (B)...</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · {new Date(r.started_at).toLocaleDateString()}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={creating || !name.trim() || !runA || !runB}
          className="self-start rounded bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {creating ? "Comparing..." : "Compare"}
        </button>
      </form>

      {experiments.length > 0 && (
        <div className="overflow-x-auto">
          <h2 className="mb-2 text-sm font-medium">Past comparisons</h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                <th className="p-2">Name</th>
                <th className="p-2">Metrics compared</th>
                <th className="p-2">Significant changes</th>
                <th className="p-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map((exp) => {
                const deltas = Object.values(exp.deltas ?? {});
                return (
                  <tr
                    key={exp.id}
                    onClick={() => setSelected(exp)}
                    className="cursor-pointer border-b border-neutral-100 hover:bg-neutral-50 dark:border-neutral-900 dark:hover:bg-neutral-900"
                  >
                    <td className="p-2 font-medium">{exp.name}</td>
                    <td className="p-2 tabular-nums text-neutral-500">{deltas.length}</td>
                    <td className="p-2 tabular-nums">
                      {deltas.filter((d) => d.significant).length}
                    </td>
                    <td className="p-2 text-neutral-500">
                      {new Date(exp.created_at).toLocaleString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && selected.deltas && (
        <div className="flex flex-col gap-3 border-t border-neutral-200 pt-6 dark:border-neutral-800">
          <h2 className="text-lg font-semibold">{selected.name}</h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                  <th className="p-2">Metric</th>
                  <th className="p-2 text-right">A (baseline)</th>
                  <th className="p-2 text-right">B (candidate)</th>
                  <th className="p-2 text-right">Δ</th>
                  <th className="p-2 text-right">95% CI</th>
                  <th className="p-2 text-right">n</th>
                  <th className="p-2">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(selected.deltas).map(([metric, d]) => (
                  <tr key={metric} className="border-b border-neutral-100 dark:border-neutral-900">
                    <td className="p-2 font-mono">
                      {metric}
                      {d.lower_is_better && (
                        <span className="ml-1 text-xs text-neutral-400">(lower better)</span>
                      )}
                    </td>
                    <td className="p-2 text-right tabular-nums">{d.mean_a.toFixed(3)}</td>
                    <td className="p-2 text-right tabular-nums">{d.mean_b.toFixed(3)}</td>
                    <td
                      className={`p-2 text-right tabular-nums ${
                        d.significant
                          ? d.improved
                            ? "text-green-600"
                            : "text-red-600"
                          : "text-neutral-500"
                      }`}
                    >
                      {d.delta >= 0 ? "+" : ""}
                      {d.delta.toFixed(3)}
                    </td>
                    <td className="p-2 text-right font-mono text-xs tabular-nums text-neutral-500">
                      [{d.ci_low.toFixed(3)}, {d.ci_high.toFixed(3)}]
                    </td>
                    <td className="p-2 text-right tabular-nums text-neutral-500">{d.n}</td>
                    <td className="p-2">
                      <VerdictBadge metric={d} />
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
