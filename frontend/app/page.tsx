"use client";

import { use, useEffect, useState } from "react";

import { Arrow, Check, Dash } from "@/components/icons";
import { Lead, Mark, PageHead, Problem, Sign } from "@/components/ui";
import { api, message, send } from "@/lib/api";
import { clock, duration, percent } from "@/lib/format";

interface Claim {
  text: string;
  citations: string[];
  support_prob: number | null;
  verdict: string | null;
}

interface Source {
  document_external_id: string | null;
  title: string | null;
  rerank_score: number | null;
}

interface Passage {
  chunk_id: string;
  document_external_id: string | null;
  title: string | null;
  text: string;
}

interface QueryResponse {
  answer_id: string;
  claims: Claim[];
  insufficient_context: boolean;
  confidence: number;
  abstained: boolean;
  sources: Source[];
  passages?: Passage[];
  trace_id: string | null;
  model: string;
  latency_ms: number | null;
  cache_hit: boolean;
  rewritten_question: string | null;
}

interface Span {
  name: string;
  latency_ms: number;
}

type Focus = { claim: number } | { passage: string } | null;

// Verbatim from eval-datasets/v1/full.jsonl (si_072, mu_069, un_108).
const EXAMPLES = [
  {
    kind: "In the corpus",
    question: "Which specific TPU configuration was used for inference on PaLM 540B?",
  },
  {
    kind: "Needs two papers",
    question:
      "How does FAIR-RAG address the issue of reasoning misalignment in RAG systems, and in what way does its approach differ from standard iterative RAG methods in terms of handling evidence gaps and trust vulnerabilities?",
  },
  {
    kind: "Not in the corpus",
    question:
      "How does the integration of external knowledge graphs with retrieval-augmented generation affect the accuracy of factual responses in medical diagnosis scenarios?",
  },
];

// `typical` is the warm timing recorded in DECISIONS.md (2026-08-06) for the
// 8 GB CPU profile; it is replaced by this answer's own spans once they exist.
const STAGES = [
  { key: "embed", name: "Embed", typical: "< 1 s", what: "The question becomes a vector." },
  {
    key: "retrieve",
    name: "Retrieve",
    typical: "< 1 s",
    what: "Dense search and BM25 each propose passages; the two lists are fused.",
  },
  {
    key: "rerank",
    name: "Rerank",
    typical: "~8 s",
    what: "A cross-encoder rereads every candidate against the question.",
  },
  {
    key: "generate",
    name: "Generate",
    typical: "~2 min 40 s",
    what: "The model answers from the top passages, citing one for every sentence.",
  },
  {
    key: "verify",
    name: "Verify",
    typical: "~1 min 25 s",
    what: "Each sentence is tested against the passage it cites.",
  },
  {
    key: "decide",
    name: "Decide",
    typical: "instant",
    what: "Confidence under the threshold withholds the answer.",
  },
];

function stageTimes(spans: Span[]): Record<string, string> {
  const ms = (name: string) => spans.find((s) => s.name === name)?.latency_ms;
  const retrieve = ms("retrieve");
  const rerank = ms("rerank");
  const measured: Record<string, number | undefined> = {
    embed: ms("embed_query"),
    // the retrieve span nests the rerank span, so the two must not be added
    retrieve: retrieve === undefined ? undefined : Math.max(0, retrieve - (rerank ?? 0)),
    rerank,
    generate: ms("generate"),
    verify: ms("verify_claims"),
  };
  return Object.fromEntries(
    Object.entries(measured).flatMap(([key, value]) =>
      value === undefined ? [] : [[key, duration(value)]],
    ),
  );
}

/** Spans are exported in batches a few seconds after the response, root last. */
async function loadStageTimes(traceId: string): Promise<Record<string, string> | null> {
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const trace = await api<{ spans: Span[] }>(`/traces/${traceId}`);
      if (trace.spans.some((s) => s.name === "query")) return stageTimes(trace.spans);
    } catch {
      // not exported yet
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  return null;
}

function Verdict({ claim }: { claim: Claim }) {
  const prob = claim.support_prob === null ? "" : ` ${claim.support_prob.toFixed(2)}`;
  if (claim.verdict === "supported") return <Mark tone="good">Supported{prob}</Mark>;
  if (claim.verdict === "unsupported") return <Mark tone="bad">Not supported{prob}</Mark>;
  return <Mark tone="neutral">Not scored</Mark>;
}

function Figure({
  loading,
  elapsed,
  response,
  threshold,
}: {
  loading: boolean;
  elapsed: number;
  response: QueryResponse | null;
  threshold: number | null;
}) {
  return (
    <div className="rounded-xl bg-panel p-6 text-white">
      <p className="text-[5.5rem] font-extrabold leading-none tracking-[-0.03em] tabular-nums xl:text-[8rem]">
        {response ? (
          <>
            {Math.round(response.confidence * 100)}
            <span className="text-[0.5em]">%</span>
          </>
        ) : (
          clock(elapsed)
        )}
      </p>

      {loading && (
        <>
          <p className="mt-3 text-lg font-bold">Elapsed</p>
          <p className="mt-1 text-[0.9375rem] text-white/75">
            Nothing is streamed. The answer appears when verification finishes.
          </p>
        </>
      )}

      {response && (
        <>
          <p className="mt-3 text-lg font-bold">Confidence</p>
          <div className="relative mt-4 h-2 rounded-full bg-white/20">
            <div
              className="h-2 rounded-full bg-white"
              style={{ width: `${response.confidence * 100}%` }}
            />
            {threshold !== null && (
              <div
                className="absolute -top-1.5 h-5 w-0.5 bg-white"
                style={{ left: `${threshold * 100}%` }}
              />
            )}
          </div>
          <p className="mt-2 text-[0.9375rem] text-white/75">
            {threshold === null
              ? "Answers under the threshold are withheld."
              : `Answers under ${percent(threshold)} are withheld.`}
          </p>

          <p className="mt-6 flex items-center gap-2 text-lg font-bold">
            {/* Withholding is an outcome, not a failure: no red here. */}
            <span
              className={`inline-flex h-6 w-6 items-center justify-center rounded text-ink ${
                response.abstained ? "bg-white" : "bg-go-bright"
              }`}
            >
              {response.abstained ? <Dash className="h-4 w-4" /> : <Check className="h-4 w-4" />}
            </span>
            {response.abstained ? "Withheld" : "Answered"}
          </p>

          <dl className="mt-6 space-y-1 border-t border-white/20 pt-4 text-[0.9375rem]">
            <div className="flex justify-between gap-4">
              <dt className="text-white/75">Model</dt>
              <dd className="text-right font-semibold">{response.model}</dd>
            </div>
            {response.latency_ms !== null && (
              <div className="flex justify-between gap-4">
                <dt className="text-white/75">Generation</dt>
                <dd className="font-semibold tabular-nums">{duration(response.latency_ms)}</dd>
              </div>
            )}
            {response.cache_hit && (
              <div className="flex justify-between gap-4">
                <dt className="text-white/75">Source</dt>
                <dd className="font-semibold">Semantic cache</dd>
              </div>
            )}
          </dl>
        </>
      )}
    </div>
  );
}

export default function Query({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  // The Candidates page's sign arrives with ?q=...: the question is filled in, not run,
  // because an answer takes minutes on CPU.
  const { q } = use(searchParams);
  const [question, setQuestion] = useState(q ?? "");
  const [asked, setAsked] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [measured, setMeasured] = useState<Record<string, string> | null>(null);
  const [focus, setFocus] = useState<Focus>(null);
  const [opened, setOpened] = useState<string[]>([]);
  const [rated, setRated] = useState<number | null>(null);
  const [correction, setCorrection] = useState("");
  const [showCorrection, setShowCorrection] = useState(false);

  useEffect(() => {
    api<{ abstain_threshold: number }>("/settings")
      .then((settings) => setThreshold(settings.abstain_threshold))
      .catch(() => {}); // a failed ask reports the outage; the threshold line just stays generic
  }, []);

  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setQuestion(trimmed);
    setAsked(trimmed);
    setLoading(true);
    setElapsed(0);
    setError(null);
    setResponse(null);
    setMeasured(null);
    setFocus(null);
    setOpened([]);
    setRated(null);
    setCorrection("");
    setShowCorrection(false);
    try {
      const answer = await send<QueryResponse>("/query", { question: trimmed });
      setResponse(answer);
      if (answer.trace_id) loadStageTimes(answer.trace_id).then(setMeasured);
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }

  async function sendFeedback(rating: number, correctionText?: string) {
    if (!response) return;
    try {
      await send("/feedback", {
        answer_id: response.answer_id,
        rating,
        correction: correctionText || null,
      });
      setRated(rating);
      setShowCorrection(false);
    } catch (err) {
      setError(message(err));
    }
  }

  const passages = response?.passages ?? [];
  const letterOf = Object.fromEntries(
    passages.map((p, i) => [p.chunk_id, String.fromCharCode(65 + i)]),
  );
  const claims = response?.claims ?? [];
  const supported = claims.filter((c) => c.verdict === "supported").length;

  const claimLit = (i: number) =>
    focus !== null &&
    ("claim" in focus ? focus.claim === i : claims[i].citations.includes(focus.passage));
  const passageLit = (id: string) =>
    focus !== null &&
    ("passage" in focus ? focus.passage === id : claims[focus.claim].citations.includes(id));

  function goToPassage(letter: string) {
    const target = document.getElementById(`passage-${letter}`);
    target?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    target?.focus({ preventScroll: true });
  }

  return (
    <>
      <PageHead
        title="Query"
        purpose="Ask the corpus a question. Every sentence of the answer is tested against the passage it cites, and an answer that is not well enough supported is withheld."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="flex max-w-4xl flex-col gap-3 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <label htmlFor="question" className="label">
            Question
          </label>
          <input
            id="question"
            className="field h-14 text-lg"
            placeholder="What do the papers say about…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </div>
        <button type="submit" disabled={loading || !question.trim()} className="btn btn-primary h-14 pl-3.5 pr-6 text-base">
          <Lead />
          {loading ? "Working" : "Ask"}
        </button>
      </form>

      {!response && !loading && (
        <div className="mt-6 max-w-4xl">
          <p className="text-[0.9375rem] font-semibold">
            Or take one from the evaluation set, written for the seeded arXiv corpus
          </p>
          <ul className="mt-2 divide-y divide-rule border-y border-rule">
            {EXAMPLES.map((example) => (
              <li key={example.kind}>
                <button
                  type="button"
                  onClick={() => ask(example.question)}
                  className="grid w-full grid-cols-[9.5rem_1fr_auto] items-center gap-4 py-3 text-left transition-colors duration-150 hover:bg-concourse"
                >
                  <span className="pl-2 text-[0.9375rem] font-bold">{example.kind}</span>
                  <span className="line-clamp-2 text-[0.9375rem] text-ink-2">
                    {example.question}
                  </span>
                  <span className="sq sq-sm mr-2">
                    <Arrow />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6" aria-live="polite">
        {error && <Problem>{error}</Problem>}
        {response && (
          <p className="sr-only">
            {response.abstained ? "Answer withheld" : "Answer ready"}, confidence{" "}
            {percent(response.confidence)}.
          </p>
        )}
      </div>

      {(loading || response) && (
        <div className="mt-4 grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <Figure loading={loading} elapsed={elapsed} response={response} threshold={threshold} />
          </div>

          <div className="lg:col-span-8">
            {loading && (
              <div aria-hidden="true" className="space-y-6">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="grid grid-cols-[auto_1fr] gap-x-4">
                    <div className="skeleton h-9 w-9" />
                    <div className="space-y-2">
                      <div className="skeleton h-5" />
                      <div className="skeleton h-5 w-2/3" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {response && (
              <p className="mb-5 max-w-prose text-lg font-semibold leading-snug">{asked}</p>
            )}

            {response && response.abstained && (
              <>
                <h2 className="text-xl font-bold tracking-[-0.01em]">Answer withheld</h2>
                <p className="mt-2 max-w-prose text-[1.0625rem]">
                  Confidence {percent(response.confidence)} is under the
                  {threshold === null ? "" : ` ${percent(threshold)}`} threshold, so no sentence is
                  shown.
                  {response.insufficient_context &&
                    " The model itself reported that the retrieved passages do not answer the question."}
                </p>
                {response.sources.length > 0 && (
                  <>
                    <h3 className="mt-6 font-bold">What retrieval found</h3>
                    <ul className="mt-2 max-w-prose divide-y divide-rule border-y border-rule">
                      {response.sources.map((source, i) => (
                        <li key={i} className="flex items-baseline justify-between gap-4 py-2.5">
                          <span>
                            {source.title ?? source.document_external_id ?? "Untitled document"}
                          </span>
                          {source.rerank_score !== null && (
                            <span className="shrink-0 text-[0.9375rem] tabular-nums text-ink-2">
                              rerank {source.rerank_score.toFixed(2)}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}

            {response && !response.abstained && (
              <>
                <h2 className="text-xl font-bold tracking-[-0.01em]">Answer</h2>
                <p className="mt-1 text-[0.9375rem] text-ink-2">
                  {claims.length} {claims.length === 1 ? "sentence" : "sentences"}, {supported}{" "}
                  supported by the passage cited.
                  {response.rewritten_question &&
                    ` The question was rewritten as: ${response.rewritten_question}`}
                </p>
                <ol className="mt-5 space-y-6">
                  {claims.map((claim, i) => {
                    const letters = claim.citations.flatMap((id) => letterOf[id] ?? []);
                    return (
                      <li
                        key={i}
                        onMouseEnter={() => setFocus({ claim: i })}
                        onMouseLeave={() => setFocus(null)}
                        onFocus={() => setFocus({ claim: i })}
                        onBlur={() => setFocus(null)}
                        className={`grid grid-cols-[auto_1fr] gap-x-4 transition-opacity duration-200 ${
                          focus !== null && !claimLit(i) ? "opacity-40" : ""
                        }`}
                      >
                        <span className="sq sq-md">{i + 1}</span>
                        <div>
                          <p className="max-w-prose text-[1.0625rem] leading-relaxed">
                            {claim.text}
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.9375rem]">
                            <Verdict claim={claim} />
                            {letters.map((letter) => (
                              <button
                                key={letter}
                                type="button"
                                onClick={() => goToPassage(letter)}
                                className="locator"
                              >
                                <Arrow to="down" className="h-4 w-4" />
                                Passage {letter}
                              </button>
                            ))}
                            {letters.length === 0 && (
                              <span className="text-ink-3">No passage cited</span>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </>
            )}
          </div>
        </div>
      )}

      {passages.length > 0 && (
        <section className="mt-12">
          <h2 className="text-xl font-bold tracking-[-0.01em]">Passages cited</h2>
          <ul className="mt-4 grid gap-4 lg:grid-cols-2">
            {passages.map((passage) => {
              const letter = letterOf[passage.chunk_id];
              const open = opened.includes(passage.chunk_id);
              const lit = passageLit(passage.chunk_id);
              return (
                <li
                  key={passage.chunk_id}
                  id={`passage-${letter}`}
                  tabIndex={-1}
                  onMouseEnter={() => setFocus({ passage: passage.chunk_id })}
                  onMouseLeave={() => setFocus(null)}
                  className={`rounded-lg bg-card p-4 transition-[opacity,box-shadow] duration-200 ${
                    lit ? "ring-2 ring-ink" : ""
                  } ${focus !== null && !lit ? "opacity-40" : ""}`}
                >
                  <div className="flex items-start gap-3">
                    <span className="sq sq-md">{letter}</span>
                    <div className="min-w-0">
                      <p className="font-bold leading-snug">
                        {passage.title ?? passage.document_external_id ?? "Untitled document"}
                      </p>
                      {passage.title && passage.document_external_id && (
                        <p className="font-mono text-sm text-ink-3">
                          {passage.document_external_id}
                        </p>
                      )}
                    </div>
                  </div>
                  <p
                    className={`mt-3 whitespace-pre-line text-[0.9375rem] leading-relaxed text-ink-2 ${
                      open ? "" : "line-clamp-5"
                    }`}
                  >
                    {passage.text}
                  </p>
                  {passage.text.length > 420 && (
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() =>
                        setOpened(
                          open
                            ? opened.filter((id) => id !== passage.chunk_id)
                            : [...opened, passage.chunk_id],
                        )
                      }
                      className="mt-2 text-sm font-semibold underline"
                    >
                      {open ? "Show less" : "Show the whole passage"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {response && (
        <section className="mt-12 max-w-prose">
          <h2 className="text-xl font-bold tracking-[-0.01em]">Was this useful?</h2>
          {rated !== null ? (
            <p className="mt-3">
              <Mark tone="good">Recorded as {rated > 0 ? "useful" : "not useful"}</Mark>
            </p>
          ) : (
            <div className="mt-3 flex gap-3">
              <button type="button" onClick={() => sendFeedback(1)} className="btn btn-secondary">
                Useful
              </button>
              <button
                type="button"
                aria-expanded={showCorrection}
                onClick={() => setShowCorrection(true)}
                className="btn btn-secondary"
              >
                Not useful
              </button>
            </div>
          )}

          {showCorrection && rated === null && (
            <div className="mt-5">
              <label htmlFor="correction" className="label">
                What should it have said? (optional)
              </label>
              <p className="mb-2 text-[0.9375rem] text-ink-2">
                A correction becomes a training pair for the reranker. Without one, this only feeds
                failure clustering.
              </p>
              <textarea
                id="correction"
                rows={3}
                className="field"
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
              />
              <div className="mt-3 flex gap-3">
                <button
                  type="button"
                  onClick={() => sendFeedback(-1, correction)}
                  className="btn btn-primary"
                >
                  Send
                </button>
                <button
                  type="button"
                  onClick={() => sendFeedback(-1)}
                  className="btn btn-secondary"
                >
                  Send without a correction
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      <section className="mt-14">
        <h2 className="text-xl font-bold tracking-[-0.01em]">
          {response ? "How this answer was produced" : "What happens to a question"}
        </h2>
        <ol className="mt-5 grid gap-x-3 gap-y-3 lg:grid-cols-6 lg:gap-y-8">
          {STAGES.map((stage, i) => (
            <li key={stage.key}>
              <div className="flex items-center">
                <span className="sq sq-md">{i + 1}</span>
                {i < STAGES.length - 1 && (
                  <>
                    <span className="ml-2 hidden h-[3px] flex-1 bg-ink lg:block" />
                    <Arrow className="-ml-3 hidden h-5 w-5 lg:block" />
                  </>
                )}
              </div>
              <p className="mt-3 font-bold">{stage.name}</p>
              <p className="text-xl font-extrabold tabular-nums tracking-[-0.01em]">
                {measured ? (measured[stage.key] ?? (stage.key === "decide" ? "instant" : "–")) : stage.typical}
              </p>
              <p className="mt-1 text-sm text-ink-2">{stage.what}</p>
              {i < STAGES.length - 1 && <Arrow to="down" className="mt-3 h-5 w-5 lg:hidden" />}
            </li>
          ))}
        </ol>
        <p className="mt-5 max-w-prose text-[0.9375rem] text-ink-2">
          {measured
            ? response?.cache_hit
              ? "Measured for this answer. It came from the semantic cache, so the later stages did not run again."
              : "Measured for this answer, from its trace."
            : "Typical times, measured warm on the 8 GB CPU profile this was built on. Allow about four minutes for an answer."}
        </p>
      </section>
      {response && (
        <div className="mt-12 grid gap-4 md:grid-cols-2">
          <Sign
            href={`/candidates?q=${encodeURIComponent(asked)}`}
            title="Candidates for this question"
            detail="Every passage retrieval weighed, and the score each stage gave it"
          />
          {response.trace_id && (
            <Sign
              href={`/timeline?trace=${response.trace_id}`}
              title="Timeline of this answer"
              detail="Each step, how long it took and what it cost"
            />
          )}
        </div>
      )}
    </>
  );
}
