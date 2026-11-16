"use client";

import { Fragment, useState } from "react";

import { Arrow } from "@/components/icons";
import { Interval } from "@/components/plots";
import { Empty, Mark, PageHead, Problem, Rows, Scroll, Section, Sign } from "@/components/ui";
import { API_URL, useApi } from "@/lib/api";
import { fixed, when } from "@/lib/format";

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
  answer: { text?: string; insufficient_context?: boolean };
  judge_notes: string | null;
}

interface EvalRunDetail extends EvalRun {
  results: EvalResult[];
}

const METRICS: [key: string, label: string][] = [
  ["hit_rate", "Hit rate"],
  ["reciprocal_rank", "Reciprocal rank"],
  ["ndcg@10", "NDCG@10"],
  ["faithfulness", "Faithfulness"],
  ["answer_correctness", "Answer correctness"],
  ["context_precision", "Context precision"],
  ["context_recall", "Context recall"],
  ["abstention_recall_unanswerable", "Withheld when unanswerable"],
  ["answered_precision", "Correct when answered"],
];

function RunStatus({ status }: { status: string }) {
  if (status === "completed") return <Mark tone="good">Completed</Mark>;
  if (status === "failed") return <Mark tone="bad">Failed</Mark>;
  return <Mark tone="neutral">{status === "running" ? "Running" : status}</Mark>;
}

export default function GoldenSet() {
  const list = useApi<EvalRun[]>("/eval/runs");
  const runs = list.data ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const detail = useApi<EvalRunDetail>(selectedId === null ? null : `/eval/runs/${selectedId}`);
  const selected = detail.data;
  const { loading } = list;
  const error = detail.error ?? list.error;

  const measured = METRICS.filter(([key]) => selected?.metrics?.[key]);

  return (
    <>
      <PageHead
        title="Golden set"
        purpose="Runs against the golden set. Every metric is a mean over the questions with a bootstrap 95% interval, so a difference smaller than the interval is not a difference."
      />

      {error && <Problem>{error}</Problem>}
      {loading && <Rows />}

      {!loading && !error && runs.length === 0 && (
        <Empty title="No evaluation runs yet">
          <p>Start one from a terminal. It appears here when it finishes.</p>
          <pre className="overflow-x-auto rounded-md bg-ground p-3 font-mono text-sm text-ink">
            {`curl -X POST ${API_URL}/api/eval/run \\
  -H "Content-Type: application/json" \\
  -d '{"name": "baseline", "full_pipeline": false}'`}
          </pre>
          <p>
            With <code className="font-mono text-[0.875em] text-ink">full_pipeline</code> off, only
            retrieval is scored and the run takes minutes. Turned on, every answer is generated and
            judged, which takes hours on a CPU.
          </p>
        </Empty>
      )}

      {runs.length > 0 && (
        <Scroll label="Evaluation runs">
          <table className="data stack md:min-w-[52rem]">
            <colgroup>
              <col />
              <col className="w-28" />
              <col className="w-36" />
              <col className="w-28" />
              <col className="w-32" />
              <col className="w-48" />
            </colgroup>
            <thead>
              <tr>
                <th>Run</th>
                <th>Dataset</th>
                <th>Status</th>
                <th className="num">NDCG@10</th>
                <th className="num">Faithfulness</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const current = selectedId === run.id;
                return (
                  <tr key={run.id} className={current ? "bg-concourse" : undefined}>
                    <td>
                      <button
                        type="button"
                        onClick={() => setSelectedId(run.id)}
                        aria-current={current ? "true" : undefined}
                        className="flex w-full items-center gap-2 text-left font-semibold underline decoration-rule decoration-2 hover:decoration-ink"
                      >
                        {current && (
                          <span className="sq sq-sm">
                            <Arrow to="down" />
                          </span>
                        )}
                        <span className="truncate">{run.name}</span>
                      </button>
                    </td>
                    <td className="text-ink-2" data-label="Dataset">
                      {run.dataset_version}
                    </td>
                    <td data-label="Status">
                      <RunStatus status={run.status} />
                    </td>
                    <td className="num" data-label="NDCG@10">
                      {fixed(run.metrics?.["ndcg@10"]?.mean)}
                    </td>
                    <td className="num" data-label="Faithfulness">
                      {fixed(run.metrics?.["faithfulness"]?.mean)}
                    </td>
                    <td className="text-ink-2" data-label="Started">
                      {when(run.started_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Scroll>
      )}

      {runs.length > 0 && !selected && (
        <p className="mt-4 text-[0.9375rem] text-ink-2">
          Choose a run to see its metrics and every question it scored.
        </p>
      )}

      {selected && (
        <>
          <Section
            title={selected.name}
            note="Each line runs from 0 to 1. The dot is the mean; the thick bar is its 95% interval."
          >
            {selected.error && (
              <p className="mb-4 max-w-prose rounded-lg bg-card p-4 text-[0.9375rem]">
                {selected.error}
              </p>
            )}
            {measured.length === 0 ? (
              <p className="text-ink-2">This run recorded no aggregate metrics.</p>
            ) : (
              <div className="grid max-w-4xl grid-cols-1 items-center gap-x-6 gap-y-1 sm:grid-cols-[minmax(11rem,15rem)_minmax(8rem,1fr)_auto] sm:gap-y-3">
                {measured.map(([key, label]) => {
                  const m = selected.metrics![key];
                  return (
                    <Fragment key={key}>
                      <span className="mt-3 font-semibold sm:mt-0">{label}</span>
                      <Interval mean={m.mean} low={m.ci_low} high={m.ci_high} />
                      <span className="tabular-nums">
                        <span className="font-bold">{m.mean.toFixed(3)}</span>{" "}
                        <span className="text-[0.9375rem] text-ink-2">
                          [{m.ci_low.toFixed(3)}, {m.ci_high.toFixed(3)}] n={m.n}
                        </span>
                      </span>
                    </Fragment>
                  );
                })}
              </div>
            )}
          </Section>

          <Section title="Question by question">
            <Scroll label="Per-question results">
              <table className="data min-w-[52rem]">
                <colgroup>
                  <col className="w-28" />
                  <col className="w-32" />
                  <col />
                  <col />
                </colgroup>
                <thead>
                  <tr>
                    <th>Question</th>
                    <th>Type</th>
                    <th>Answer</th>
                    <th>Judge notes</th>
                  </tr>
                </thead>
                <tbody>
                  {selected.results.map((r) => (
                    <tr key={r.id}>
                      <td className="font-mono text-sm">{r.question_id}</td>
                      <td>{r.question_type.replace("_", " ")}</td>
                      <td>
                        {r.answer.insufficient_context ? (
                          <Mark tone="neutral">Withheld</Mark>
                        ) : r.answer.text ? (
                          <span className="line-clamp-3" title={r.answer.text}>
                            {r.answer.text}
                          </span>
                        ) : (
                          <span className="text-ink-3">Retrieval only</span>
                        )}
                      </td>
                      <td className="text-ink-2">
                        {r.judge_notes ? (
                          <span className="line-clamp-3" title={r.judge_notes}>
                            {r.judge_notes}
                          </span>
                        ) : (
                          "–"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Scroll>
          </Section>

          <div className="mt-12 max-w-xl">
            <Sign
              href={`/ab?a=${selected.id}`}
              title="Compare this run with another"
              detail="Question by question, with a 95% interval on every difference"
            />
          </div>
        </>
      )}
    </>
  );
}
