"use client";

import { use, useState } from "react";

import { Arrow } from "@/components/icons";
import { Empty, Mark, PageHead, Problem, Rows, Scroll, Section, Sign } from "@/components/ui";
import { useApi } from "@/lib/api";
import { duration, money, when } from "@/lib/format";

interface TraceSummary {
  trace_id: string;
  started_at: string;
  latency_ms: number;
  span_count: number;
  question: string | null;
  cache_hit: boolean | null;
  abstained: boolean | null;
  cost_usd: number | null;
}

interface Span {
  id: string;
  kind: string;
  name: string;
  started_at: string;
  ended_at: string;
  latency_ms: number;
  attributes: Record<string, unknown>;
}

interface TraceDetail {
  trace_id: string;
  spans: Span[];
  question: string | null;
  total_latency_ms: number;
  total_cost_usd: number;
}

// The whole request in ink, every step inside it in grey: the row's own
// label names the stage, so colour is not asked to.
const KINDS: Record<string, { bar: string; label: string }> = {
  CHAIN: { bar: "bg-ink", label: "Whole request" },
  EMBEDDING: { bar: "bg-ink-3", label: "Embedding" },
  RETRIEVER: { bar: "bg-ink-3", label: "Retrieval" },
  RERANKER: { bar: "bg-ink-3", label: "Reranking" },
  LLM: { bar: "bg-ink-3", label: "Generation" },
  EVALUATOR: { bar: "bg-ink-3", label: "Verification" },
  GUARDRAIL: { bar: "bg-ink-3", label: "Guardrail" },
};
const OTHER = { bar: "bg-ink-3", label: "Other" };

function Waterfall({ spans }: { spans: Span[] }) {
  // Offsets are measured from the trace's own first span, not from epoch.
  const t0 = Math.min(...spans.map((s) => new Date(s.started_at).getTime()));
  const t1 = Math.max(...spans.map((s) => new Date(s.ended_at).getTime()));
  const total = Math.max(1, t1 - t0);

  return (
    <ol aria-label="Span waterfall" className="divide-y divide-rule border-y border-rule">
        {spans.map((span) => {
          const kind = KINDS[span.kind] ?? OTHER;
          const offset = ((new Date(span.started_at).getTime() - t0) / total) * 100;
          const width = Math.max(0.6, (span.latency_ms / total) * 100);
          return (
            <li
              key={span.id}
              className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5 py-2 md:grid-cols-[11rem_8.5rem_1fr_6.5rem]"
            >
              <span className="truncate font-mono text-sm" title={span.name}>
                {span.name}
              </span>
              <span className="hidden text-sm text-ink-2 md:block">
                {kind.label}
              </span>
              <span className="relative order-last col-span-2 h-4 rounded-sm bg-concourse md:order-none md:col-span-1">
                <span
                  className={`absolute h-4 rounded-sm ${kind.bar}`}
                  style={{ left: `${Math.min(offset, 99.4)}%`, width: `${width}%` }}
                />
              </span>
              <span className="text-right text-[0.9375rem] font-semibold tabular-nums">
                {duration(span.latency_ms)}
              </span>
            </li>
          );
        })}
      </ol>
  );
}

export default function Timeline({
  searchParams,
}: {
  searchParams: Promise<{ trace?: string }>;
}) {
  // The Query page's sign arrives with ?trace=...: that trace opens straight away.
  const { trace } = use(searchParams);
  const list = useApi<TraceSummary[]>("/traces?limit=50");
  const traces = list.data ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(trace ?? null);
  const detail = useApi<TraceDetail>(selectedId === null ? null : `/traces/${selectedId}`);
  const selected = detail.data;
  const { loading } = list;
  const error = list.error;

  return (
    <>
      <PageHead
        title="Timeline"
        purpose="Every question, step by step: what ran, in what order, for how long, and what it cost."
      />

      {error && <Problem>{error}</Problem>}
      {detail.error && (
        <Problem>
          {detail.error} Spans are written a few seconds after an answer, so a trace opened
          immediately may not exist yet.{" "}
          <button type="button" onClick={detail.reload} className="font-semibold underline">
            Load it again
          </button>
        </Problem>
      )}
      {loading && <Rows />}

      {!loading && !error && traces.length === 0 && (
        <Empty title="No traces yet">
          <p>
            A trace is recorded for every question. Ask one on the Query page and it appears here a
            few seconds after the answer.
          </p>
        </Empty>
      )}

      {traces.length > 0 && (
        <Scroll label="Recent traces">
          <table className="data stack md:min-w-[56rem]">
            <colgroup>
              <col />
              <col className="w-20" />
              <col className="w-32" />
              <col className="w-28" />
              <col className="w-40" />
              <col className="w-48" />
            </colgroup>
            <thead>
              <tr>
                <th>Question</th>
                <th className="num">Spans</th>
                <th className="num">Duration</th>
                <th className="num">Cost</th>
                <th>Outcome</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => {
                const current = selectedId === t.trace_id;
                return (
                  <tr key={t.trace_id} className={current ? "bg-concourse" : undefined}>
                    <td>
                      <button
                        type="button"
                        onClick={() => setSelectedId(t.trace_id)}
                        aria-current={current ? "true" : undefined}
                        className="flex w-full items-center gap-2 text-left font-semibold underline decoration-rule decoration-2 hover:decoration-ink"
                      >
                        {current && (
                          <span className="sq sq-sm">
                            <Arrow to="down" />
                          </span>
                        )}
                        <span className={`truncate ${t.question ? "" : "font-mono text-sm"}`}>
                          {t.question ?? t.trace_id}
                        </span>
                      </button>
                    </td>
                    <td className="num text-ink-2" data-label="Spans">
                      {t.span_count}
                    </td>
                    <td className="num" data-label="Duration">
                      {duration(t.latency_ms)}
                    </td>
                    <td className="num text-ink-2" data-label="Cost">
                      {t.cost_usd === null ? "–" : money(t.cost_usd)}
                    </td>
                    <td data-label="Outcome">
                      <div>
                      {t.abstained ? (
                        <Mark tone="neutral">Withheld</Mark>
                      ) : t.abstained === false ? (
                        <Mark tone="good">Answered</Mark>
                      ) : (
                        <span className="text-ink-3">–</span>
                      )}
                      {t.cache_hit && <span className="block text-sm text-ink-2">from cache</span>}
                      </div>
                    </td>
                    <td className="text-ink-2" data-label="Started">
                      {when(t.started_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Scroll>
      )}

      {selected && (
        <>
          <Section
            title={selected.question ?? "Trace"}
            note={`${selected.spans.length} spans, ${duration(selected.total_latency_ms)} in all, ${money(selected.total_cost_usd)}. A cost of $0 means every model ran locally.`}
          >
            <p className="mb-4 break-all font-mono text-sm text-ink-3">{selected.trace_id}</p>
            {selected.spans.length > 0 && <Waterfall spans={selected.spans} />}
          </Section>

          <Section title="What each span recorded">
            <div className="max-w-4xl divide-y divide-rule border-y border-rule">
              {selected.spans.map((span) => {
                const entries = Object.entries(span.attributes);
                if (entries.length === 0) return null;
                return (
                  <details key={span.id} className="group py-1">
                    <summary className="flex cursor-pointer items-center justify-between gap-4 py-2">
                      <span className="font-mono text-sm font-semibold">{span.name}</span>
                      <span className="text-sm text-ink-2">
                        {entries.length} {entries.length === 1 ? "attribute" : "attributes"}
                      </span>
                    </summary>
                    <dl className="grid grid-cols-1 gap-x-6 gap-y-1 pb-3 text-sm sm:grid-cols-[minmax(0,20rem)_1fr]">
                      {entries.map(([key, value]) => (
                        <div key={key} className="contents">
                          <dt className="break-all font-mono text-ink-2">{key}</dt>
                          <dd className="mb-2 break-all font-mono sm:mb-0">{String(value)}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                );
              })}
            </div>
          </Section>

          {selected.question && (
            <div className="mt-12 max-w-xl">
              <Sign
                href={`/candidates?q=${encodeURIComponent(selected.question)}`}
                title="Candidates for this question"
                detail="Every passage retrieval weighed, and the score each stage gave it"
              />
            </div>
          )}
        </>
      )}
    </>
  );
}
