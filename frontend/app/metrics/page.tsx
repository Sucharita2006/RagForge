"use client";

import { useState } from "react";

import { Empty, PageHead, Problem, Rows, Scroll, Section, Sign } from "@/components/ui";
import { useApi } from "@/lib/api";
import { duration, money, percent, when } from "@/lib/format";

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
}

interface AnalyticsSummary {
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

const WINDOWS = [
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 24 * 7 },
  { label: "30 days", hours: 24 * 30 },
];

const STAGE_NAMES: Record<string, string> = {
  CHAIN: "Whole request",
  EMBEDDING: "Embedding",
  RETRIEVER: "Retrieval (includes reranking)",
  RERANKER: "Reranking",
  LLM: "Generation",
  EVALUATOR: "Verification",
  GUARDRAIL: "Guardrail",
};

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-sm font-semibold text-ink-2">{label}</dt>
      <dd className="mt-0.5 text-[1.75rem] font-extrabold leading-tight tracking-[-0.01em] tabular-nums">
        {value}
      </dd>
      {note && <dd className="text-sm text-ink-2">{note}</dd>}
    </div>
  );
}

/** Drawn with plain elements: a handful of buckets does not earn a chart library. */
function BucketBars({ buckets }: { buckets: AnalyticsBucket[] }) {
  const peak = Math.max(...buckets.map((b) => b.p95_ms), 1);
  return (
    <figure className="max-w-4xl">
      <div className="flex items-end gap-3">
        <span className="w-20 shrink-0 self-start text-right text-sm tabular-nums text-ink-2">
          {duration(peak)}
        </span>
        <div
          role="img"
          aria-label={`95th percentile latency in ${buckets.length} time buckets, highest ${duration(peak)}`}
          className="flex h-40 flex-1 items-end gap-1 border-b-2 border-ink"
        >
          {buckets.map((b) => (
            <div
              key={b.bucket_start}
              className="flex-1 rounded-t-sm bg-ink transition-colors duration-150 hover:bg-ink-2"
              style={{ height: `${Math.max(2, (b.p95_ms / peak) * 100)}%` }}
              title={`${when(b.bucket_start)}: ${b.query_count} questions, p50 ${duration(b.p50_ms)}, p95 ${duration(b.p95_ms)}`}
            />
          ))}
        </div>
      </div>
      <figcaption className="ml-[5.75rem] mt-2 flex justify-between text-sm text-ink-2">
        <span>{when(buckets[0].bucket_start)}</span>
        <span>{when(buckets[buckets.length - 1].bucket_start)}</span>
      </figcaption>
    </figure>
  );
}

export default function Metrics() {
  const [windowHours, setWindowHours] = useState(24);
  const { data, error, loading } = useApi<AnalyticsSummary>(
    `/analytics/summary?window_hours=${windowHours}`,
  );

  return (
    <>
      <PageHead
        title="Metrics"
        purpose="How long questions take, how often the cache answers, how often an answer is withheld, and what it all costs."
      >
        <div role="group" aria-label="Time window" className="flex">
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              type="button"
              aria-pressed={windowHours === w.hours}
              onClick={() => setWindowHours(w.hours)}
              className="btn btn-sm -ml-0.5 rounded-none border-2 border-ink first:ml-0 first:rounded-l-md last:rounded-r-md hover:bg-concourse aria-pressed:bg-ink aria-pressed:text-white"
            >
              {w.label}
            </button>
          ))}
        </div>
      </PageHead>

      {error && <Problem>{error}</Problem>}
      {loading && <Rows />}

      {data && data.query_count === 0 && !loading && (
        <Empty title="No questions in this window">
          <p>
            These figures are built from traces. Ask a question on the Query page, or choose a
            longer window.
          </p>
        </Empty>
      )}

      {data && data.query_count > 0 && (
        <>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-6 border-y-2 border-ink py-6 md:grid-cols-3 xl:grid-cols-5">
            <Stat label="Questions" value={String(data.query_count)} />
            <Stat
              label="Median duration"
              value={duration(data.latency.p50_ms)}
              note={`p95 ${duration(data.latency.p95_ms)}, p99 ${duration(data.latency.p99_ms)}`}
            />
            <Stat label="Answered from cache" value={percent(data.cache_hit_rate)} />
            <Stat
              label="Withheld"
              value={percent(data.abstention_rate)}
              note={
                data.mean_confidence === null
                  ? undefined
                  : `mean confidence ${data.mean_confidence.toFixed(2)}`
              }
            />
            <Stat
              label="Cost"
              value={money(data.total_cost_usd)}
              note={
                data.total_cost_usd === 0
                  ? "every model ran locally"
                  : `${money(data.cost_per_query_usd)} per question`
              }
            />
          </dl>

          {data.query_count < 20 && (
            <p className="mt-4 max-w-prose text-[0.9375rem] text-ink-2">
              With {data.query_count} {data.query_count === 1 ? "question" : "questions"} in the
              window, the percentiles are close to single observations. Read them as examples, not
              as a distribution.
            </p>
          )}

          {data.buckets.length > 0 && (
            <Section
              title="Slowest questions over time"
              note="Each bar is one time bucket's 95th percentile. Hover a bar for its counts."
            >
              <BucketBars buckets={data.buckets} />
            </Section>
          )}

          {Object.keys(data.by_span_kind).length > 0 && (
            <Section title="Where the time goes">
              <Scroll label="Duration by pipeline stage">
                <table className="data max-w-3xl min-w-[36rem]">
                  <colgroup>
                    <col />
                    <col className="w-32" />
                    <col className="w-32" />
                    <col className="w-32" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Stage</th>
                      <th className="num">Median</th>
                      <th className="num">p95</th>
                      <th className="num">p99</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.by_span_kind).map(([kind, p]) => (
                      <tr key={kind}>
                        <td className="font-semibold">{STAGE_NAMES[kind] ?? kind}</td>
                        <td className="num">{duration(p.p50_ms)}</td>
                        <td className="num">{duration(p.p95_ms)}</td>
                        <td className="num">{duration(p.p99_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Scroll>
            </Section>
          )}

          <div className="mt-12 max-w-xl">
            <Sign
              href="/timeline"
              title="Every question, step by step"
              detail="Open any request to see where its time went"
            />
          </div>
        </>
      )}
    </>
  );
}
