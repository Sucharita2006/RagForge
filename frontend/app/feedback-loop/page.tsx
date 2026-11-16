"use client";

import { useState } from "react";

import { Forest } from "@/components/plots";
import { Empty, Mark, PageHead, Problem, Scroll, Section, Sign, type Tone } from "@/components/ui";
import { message, send, useApi } from "@/lib/api";
import { signed, when } from "@/lib/format";

interface ModelRow {
  id: string;
  kind: string;
  base_model: string;
  artifact_path: string | null;
  train_config: Record<string, unknown>;
  status: string;
}

interface FeedbackRow {
  id: string;
  rating: number;
  correction: string | null;
  created_at: string;
}

interface FailureCluster {
  id: string;
  cluster_label: string;
  size: number;
  suggested_action: string;
}

interface EvalRun {
  id: string;
  name: string;
  status: string;
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

const CLUSTER_NAMES: Record<string, string> = {
  retrieval_miss: "Retrieval miss",
  generation_error: "Generation error",
  parsing_gap: "Parsing gap",
  knowledge_gap: "Knowledge gap",
};

function tone(g: GateMetric): Tone {
  if (!g.significant) return "neutral";
  return g.improved ? "good" : "bad";
}

function ModelStatus({ status }: { status: string }) {
  if (status === "active") return <Mark tone="good">Active</Mark>;
  return <Mark tone="neutral">{status === "candidate" ? "Candidate" : "Retired"}</Mark>;
}

export default function FeedbackLoop() {
  const registry = useApi<ModelRow[]>("/models");
  const received = useApi<FeedbackRow[]>("/feedback");
  const grouped = useApi<FailureCluster[]>("/failures/clusters");
  const allRuns = useApi<EvalRun[]>("/eval/runs");
  const models = registry.data ?? [];
  const feedback = received.data ?? [];
  const clusters = grouped.data ?? [];
  const runs = (allRuns.data ?? []).filter((run) => run.status === "completed");
  const [promoting, setPromoting] = useState<string | null>(null);
  const [result, setResult] = useState<PromoteResult | null>(null);
  const [runActive, setRunActive] = useState("");
  const [runCandidate, setRunCandidate] = useState("");
  const [queued, setQueued] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const error =
    actionError ?? registry.error ?? received.error ?? grouped.error ?? allRuns.error;

  const ready = Boolean(runActive && runCandidate);

  async function promote(modelId: string) {
    setPromoting(modelId);
    setActionError(null);
    setResult(null);
    try {
      setResult(
        await send<PromoteResult>(`/models/${modelId}/promote`, {
          run_active_id: runActive,
          run_candidate_id: runCandidate,
        }),
      );
      registry.reload();
    } catch (err) {
      setActionError(message(err));
    } finally {
      setPromoting(null);
    }
  }

  async function startFinetune() {
    setActionError(null);
    try {
      await send("/finetune/reranker", { epochs: 1, batch_size: 32 });
      setQueued(true);
    } catch (err) {
      setActionError(message(err));
    }
  }

  return (
    <>
      <PageHead
        title="Feedback loop"
        purpose="Corrections become training pairs, training produces a candidate reranker, and a gate decides whether it ships. A candidate is promoted only if the 95% interval on its NDCG@10 or hit-rate gain excludes zero."
      />

      {error && <Problem>{error}</Problem>}

      <div className="grid max-w-4xl gap-4 md:grid-cols-2">
        <div>
          <label htmlFor="run-active" className="label">
            Evaluation run of the active model
          </label>
          <select
            id="run-active"
            className="field"
            value={runActive}
            onChange={(e) => setRunActive(e.target.value)}
          >
            <option value="">Choose a completed run</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="run-candidate" className="label">
            Evaluation run of the candidate
          </label>
          <select
            id="run-candidate"
            className="field"
            value={runCandidate}
            onChange={(e) => setRunCandidate(e.target.value)}
          >
            <option value="">Choose a completed run</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="mt-2 max-w-prose text-[0.9375rem] text-ink-2">
        The gate compares these two runs. Both must score the same held-out questions, never ones
        the candidate was trained on.
      </p>

      {result && (
        <section className="mt-12 grid gap-6 lg:grid-cols-12">
          <div className="self-start rounded-xl bg-panel p-6 text-white lg:col-span-4">
            <p className="text-[2.75rem] font-extrabold leading-none tracking-[-0.03em]">
              {result.promoted ? "Promoted" : "Not promoted"}
            </p>
            <p className="mt-3 text-lg font-bold">
              {result.promoted
                ? "The candidate is now the active model"
                : "The active model stays in place"}
            </p>
            <p className="mt-1 text-[0.9375rem] text-white/75">
              {result.reason ??
                (result.promoted
                  ? `Improved: ${result.improved_metrics.join(", ")}.`
                  : "The gate found no significant improvement.")}
            </p>
            {Object.keys(result.gate).length > 0 && (
              <dl className="mt-6 space-y-1 border-t border-white/20 pt-4 text-[0.9375rem]">
                {Object.entries(result.gate).map(([metric, g]) => (
                  <div key={metric} className="flex justify-between gap-4">
                    <dt className="text-white/75">{metric}</dt>
                    <dd className="text-right font-semibold">
                      {!g.significant
                        ? "interval includes zero"
                        : g.improved
                          ? "interval above zero"
                          : "interval below zero"}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          <div className="lg:col-span-8">
            <h2 className="mb-4 text-xl font-bold tracking-[-0.01em]">What the gate measured</h2>
              {Object.keys(result.gate).length > 0 && (
                <Scroll label="Gate metrics">
                  <table className="data stack max-w-4xl md:min-w-[48rem]">
                    <colgroup>
                      <col />
                      <col className="w-28" />
                      <col className="w-56" />
                      <col className="w-48" />
                      <col className="w-16" />
                    </colgroup>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th className="num">Change</th>
                        <th>Change and interval</th>
                        <th className="num">95% interval</th>
                        <th className="num">n</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.gate).map(([metric, g]) => (
                        <tr key={metric}>
                          <td className="font-semibold">{metric}</td>
                          <td className="num font-bold" data-label="Change">
                            {signed(g.delta, 4)}
                          </td>
                          <td className="wide-only">
                            <Forest delta={g.delta} low={g.ci_low} high={g.ci_high} tone={tone(g)} />
                          </td>
                          <td className="num text-ink-2" data-label="95% interval">
                            [{signed(g.ci_low, 4)}, {signed(g.ci_high, 4)}]
                          </td>
                          <td className="num text-ink-2" data-label="n">
                            {g.n}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Scroll>
              )}
          </div>
        </section>
      )}

      <Section title="Model registry">
        <Scroll label="Model registry">
          <table className="data stack md:min-w-[52rem]">
            <colgroup>
              <col />
              <col className="w-28" />
              <col className="w-36" />
              <col className="w-36" />
              <col className="w-52" />
            </colgroup>
            <thead>
              <tr>
                <th>Base model</th>
                <th>Kind</th>
                <th className="num">Trained on</th>
                <th>Status</th>
                <th>Gate</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td>
                    <span
                      className="block truncate font-mono text-sm"
                      title={m.artifact_path ?? m.base_model}
                    >
                      {m.base_model}
                    </span>
                  </td>
                  <td data-label="Kind">{m.kind}</td>
                  <td className="num text-ink-2" data-label="Trained on">
                    {typeof m.train_config.n_examples === "number"
                      ? `${m.train_config.n_examples} examples`
                      : "–"}
                  </td>
                  <td data-label="Status">
                    <ModelStatus status={m.status} />
                  </td>
                  <td data-label="Gate">
                    {m.status === "candidate" && (
                      <button
                        type="button"
                        onClick={() => promote(m.id)}
                        disabled={!ready || promoting === m.id}
                        className="btn btn-primary btn-sm"
                      >
                        {promoting === m.id ? "Testing" : "Run the gate"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Scroll>
        {models.some((m) => m.status === "candidate") && !ready && (
          <p className="mt-3 text-[0.9375rem] text-ink-2">
            Choose both evaluation runs above to run the gate on a candidate.
          </p>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-4">
          <button type="button" onClick={startFinetune} disabled={queued} className="btn btn-secondary">
            Train a new candidate
          </button>
          {queued && (
            <Mark tone="good">Queued. Training runs in the worker; reload in a few minutes.</Mark>
          )}
        </div>
      </Section>

      <Section title="Failure clusters">
        {clusters.length === 0 ? (
          <Empty title="No clusters yet">
            <p>
              Answers rated not useful are grouped by what went wrong: the right passage was not
              retrieved, the model misread it, the document was parsed badly, or the corpus does
              not cover the question.
            </p>
          </Empty>
        ) : (
          <Scroll label="Failure clusters">
            <table className="data max-w-4xl min-w-[36rem]">
              <colgroup>
                <col className="w-48" />
                <col className="w-24" />
                <col />
              </colgroup>
              <thead>
                <tr>
                  <th>What went wrong</th>
                  <th className="num">Answers</th>
                  <th>Suggested action</th>
                </tr>
              </thead>
              <tbody>
                {clusters.map((c) => (
                  <tr key={c.id}>
                    <td className="font-semibold">
                      {CLUSTER_NAMES[c.cluster_label] ?? c.cluster_label}
                    </td>
                    <td className="num">{c.size}</td>
                    <td className="text-ink-2">{c.suggested_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        )}
      </Section>

      <Section title={`Feedback received (${feedback.length})`}>
        {feedback.length === 0 ? (
          <Empty title="No feedback yet">
            <p>
              Rate an answer on the Query page. A rating with a correction becomes a training pair;
              a rating alone only feeds the failure clusters.
            </p>
          </Empty>
        ) : (
          <Scroll label="Feedback received">
            <table className="data max-w-4xl min-w-[36rem]">
              <colgroup>
                <col className="w-36" />
                <col />
                <col className="w-48" />
              </colgroup>
              <thead>
                <tr>
                  <th>Rating</th>
                  <th>Correction</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                {feedback.map((f) => (
                  <tr key={f.id}>
                    <td>
                      {f.rating > 0 ? (
                        <Mark tone="good">Useful</Mark>
                      ) : (
                        <Mark tone="bad">Not useful</Mark>
                      )}
                    </td>
                    <td className="text-ink-2">
                      {f.correction ? (
                        <span className="line-clamp-2" title={f.correction}>
                          {f.correction}
                        </span>
                      ) : (
                        "–"
                      )}
                    </td>
                    <td className="text-ink-2">{when(f.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        )}
      </Section>

      <div className="mt-12 max-w-xl">
        <Sign
          href="/trust-settings"
          title="Set how sure an answer must be"
          detail="The abstain threshold and the calibration curve behind it"
        />
      </div>
    </>
  );
}
