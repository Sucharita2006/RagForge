"use client";

import { use, useState } from "react";

import { Arrow } from "@/components/icons";
import { Forest } from "@/components/plots";
import {
  Empty,
  Lead,
  Mark,
  PageHead,
  Problem,
  Rows,
  Scroll,
  Section,
  Sign,
  type Tone,
} from "@/components/ui";
import { message, send, useApi } from "@/lib/api";
import { measure, signed, when } from "@/lib/format";

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
  deltas: Record<string, MetricDelta> | null;
  created_at: string;
}

interface EvalRun {
  id: string;
  name: string;
  status: string;
  started_at: string;
}

function tone(d: MetricDelta): Tone {
  if (!d.significant) return "neutral";
  return d.improved ? "good" : "bad";
}

const VERDICT: Record<Tone, string> = {
  good: "Improved",
  bad: "Regressed",
  neutral: "No significant change",
};

export default function AB({ searchParams }: { searchParams: Promise<{ a?: string }> }) {
  // A Golden set sign arrives with ?a=<run id> as the baseline.
  const { a } = use(searchParams);
  const past = useApi<Experiment[]>("/experiments");
  const allRuns = useApi<EvalRun[]>("/eval/runs");
  const experiments = past.data ?? [];
  const runs = (allRuns.data ?? []).filter((r) => r.status === "completed");
  const [selected, setSelected] = useState<Experiment | null>(null);
  const [name, setName] = useState("");
  const [runA, setRunA] = useState(a ?? "");
  const [runB, setRunB] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const error = createError ?? past.error ?? allRuns.error;

  async function createExperiment(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !runA || !runB || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await send<Experiment>("/experiments", {
        name,
        run_a_id: runA,
        run_b_id: runB,
      });
      setSelected(created);
      setName("");
      past.reload();
    } catch (err) {
      setCreateError(message(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <PageHead
        title="A/B"
        purpose="Compare two evaluation runs question by question. A metric counts as changed only when the 95% interval on the difference excludes zero."
      />

      {error && <Problem>{error}</Problem>}

      <form onSubmit={createExperiment} className="grid max-w-4xl gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <label htmlFor="name" className="label">
            Name
          </label>
          <input
            id="name"
            className="field"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="run-a" className="label">
            Baseline run (A)
          </label>
          <select
            id="run-a"
            className="field"
            value={runA}
            onChange={(e) => setRunA(e.target.value)}
          >
            <option value="">Choose a completed run</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}, {when(r.started_at)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="run-b" className="label">
            Candidate run (B)
          </label>
          <select
            id="run-b"
            className="field"
            value={runB}
            onChange={(e) => setRunB(e.target.value)}
          >
            <option value="">Choose a completed run</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}, {when(r.started_at)}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={creating || !name.trim() || !runA || !runB}
            className="btn btn-primary pl-2"
          >
            <Lead />
            {creating ? "Comparing" : "Compare"}
          </button>
        </div>
      </form>

      <Section title="Comparisons">
        {past.loading ? (
          <Rows />
        ) : experiments.length === 0 ? (
          <Empty title="Nothing compared yet">
            <p>
              Pick a baseline run and a candidate run above. Both must have finished and should
              cover the same questions, because the comparison is paired: only questions present in
              both runs are used.
            </p>
          </Empty>
        ) : (
          <Scroll label="Past comparisons">
            <table className="data min-w-[44rem]">
              <colgroup>
                <col />
                <col className="w-32" />
                <col className="w-40" />
                <col className="w-48" />
              </colgroup>
              <thead>
                <tr>
                  <th>Comparison</th>
                  <th className="num">Metrics</th>
                  <th className="num">Significant</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {experiments.map((exp) => {
                  const deltas = Object.values(exp.deltas ?? {});
                  const current = selected?.id === exp.id;
                  return (
                    <tr key={exp.id} className={current ? "bg-concourse" : undefined}>
                      <td>
                        <button
                          type="button"
                          onClick={() => setSelected(exp)}
                          aria-current={current ? "true" : undefined}
                          className="flex w-full items-center gap-2 text-left font-semibold underline decoration-rule decoration-2 hover:decoration-ink"
                        >
                          {current && (
                            <span className="sq sq-sm">
                              <Arrow to="down" />
                            </span>
                          )}
                          <span className="truncate">{exp.name}</span>
                        </button>
                      </td>
                      <td className="num">{deltas.length}</td>
                      <td className="num">{deltas.filter((d) => d.significant).length}</td>
                      <td className="text-ink-2">{when(exp.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Scroll>
        )}
      </Section>

      {selected?.deltas && (
        <Section
          title={selected.name}
          note="The black line is zero. An interval that crosses it is not a change, whichever way the dot leans."
        >
          <Scroll label="Metric differences">
            <table className="data stack md:min-w-[72rem]">
              <colgroup>
                <col />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-24" />
                <col className="w-56" />
                <col className="w-44" />
                <col className="w-16" />
                <col className="w-52" />
              </colgroup>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="num">A</th>
                  <th className="num">B</th>
                  <th className="num">B − A</th>
                  <th>Difference and interval</th>
                  <th className="num">95% interval</th>
                  <th className="num">n</th>
                  <th>Verdict</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(selected.deltas).map(([metric, d]) => (
                  <tr key={metric}>
                    <td>
                      <span className="font-semibold">{metric}</span>
                      {d.lower_is_better && (
                        <span className="block text-sm text-ink-3">lower is better</span>
                      )}
                    </td>
                    <td className="num" data-label="A">
                      {measure(d.mean_a)}
                    </td>
                    <td className="num" data-label="B">
                      {measure(d.mean_b)}
                    </td>
                    <td className="num font-bold" data-label="B − A">
                      {signed(d.delta)}
                    </td>
                    <td className="wide-only">
                      <Forest delta={d.delta} low={d.ci_low} high={d.ci_high} tone={tone(d)} />
                    </td>
                    <td className="num text-ink-2" data-label="95% interval">
                      [{signed(d.ci_low)}, {signed(d.ci_high)}]
                    </td>
                    <td className="num text-ink-2" data-label="n">
                      {d.n}
                    </td>
                    <td data-label="Verdict">
                      <Mark tone={tone(d)}>{VERDICT[tone(d)]}</Mark>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        </Section>
      )}

      {selected?.deltas && (
        <div className="mt-12 max-w-xl">
          <Sign
            href="/feedback-loop"
            title="Decide whether a candidate ships"
            detail="The promotion gate runs this comparison on held-out questions"
          />
        </div>
      )}
    </>
  );
}
