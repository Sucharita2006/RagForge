"use client";

import { useState } from "react";

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

interface QueryResponse {
  query_id: string;
  answer_id: string;
  claims: Claim[];
  insufficient_context: boolean;
  confidence: number;
  abstained: boolean;
  sources: Source[];
  trace_id: string | null;
  model: string;
  latency_ms: number | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const VERDICT_STYLES: Record<string, string> = {
  supported: "bg-green-100 dark:bg-green-950/60",
  unsupported: "bg-amber-100 dark:bg-amber-950/60",
  unscored: "bg-neutral-100 dark:bg-neutral-900",
};

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.7
      ? "bg-green-100 text-green-900 dark:bg-green-950 dark:text-green-200"
      : confidence >= 0.4
        ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        : "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${color}`}>
      confidence: {pct}%
    </span>
  );
}

export default function Playground() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rated, setRated] = useState<number | null>(null);
  const [correction, setCorrection] = useState("");
  const [showCorrection, setShowCorrection] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    setRated(null);
    setCorrection("");
    setShowCorrection(false);
    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setResponse((await res.json()) as QueryResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function sendFeedback(rating: number, correctionText?: string) {
    if (!response) return;
    try {
      const res = await fetch(`${API_URL}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answer_id: response.answer_id,
          rating,
          correction: correctionText || null,
        }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      setRated(rating);
      setShowCorrection(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">ragforge</h1>
        <p className="text-sm text-neutral-500">
          Playground — ask a question about the ingested corpus.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          className="flex-1 rounded border border-neutral-300 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="Ask a question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-neutral-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {response && (
        <div className="flex flex-col gap-3 rounded border border-neutral-200 p-4 dark:border-neutral-800">
          <div className="flex items-center gap-2">
            <ConfidenceBadge confidence={response.confidence} />
            {response.abstained && (
              <span className="rounded bg-neutral-200 px-2 py-0.5 text-xs font-medium text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
                abstained
              </span>
            )}
          </div>

          {response.abstained ? (
            <div className="flex flex-col gap-2">
              <p className="rounded bg-amber-100 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                I don&apos;t have enough grounded information to confidently answer this question.
              </p>
              {response.sources.length > 0 && (
                <div className="text-xs text-neutral-500">
                  <p className="mb-1">Sources found, in case they help:</p>
                  <ul className="flex flex-col gap-0.5">
                    {response.sources.map((s, i) => (
                      <li key={i}>{s.title ?? s.document_external_id ?? "unknown source"}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {response.claims.map((claim, i) => (
                <p
                  key={i}
                  className={`rounded px-2 py-1 text-sm leading-relaxed ${VERDICT_STYLES[claim.verdict ?? "unscored"]}`}
                  title={
                    claim.support_prob !== null
                      ? `${claim.verdict} (support ${claim.support_prob.toFixed(2)})`
                      : "unscored"
                  }
                >
                  {claim.text}{" "}
                  {claim.citations.length > 0 && (
                    <span className="text-xs text-neutral-400">
                      [{claim.citations.join(", ")}]
                    </span>
                  )}
                </p>
              ))}
            </div>
          )}

          <div className="flex items-center gap-3 border-t border-neutral-100 pt-3 text-xs dark:border-neutral-900">
            {rated === null ? (
              <>
                <span className="text-neutral-500">Was this answer useful?</span>
                <button
                  onClick={() => sendFeedback(1)}
                  className="rounded border border-neutral-300 px-2 py-1 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
                  aria-label="Rate answer as useful"
                >
                  👍
                </button>
                <button
                  onClick={() => setShowCorrection(true)}
                  className="rounded border border-neutral-300 px-2 py-1 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-900"
                  aria-label="Rate answer as not useful"
                >
                  👎
                </button>
              </>
            ) : (
              <span className="text-neutral-500">
                Thanks — feedback recorded {rated > 0 ? "👍" : "👎"}
              </span>
            )}
          </div>

          {showCorrection && rated === null && (
            <div className="flex flex-col gap-2">
              <label htmlFor="correction" className="text-xs text-neutral-500">
                What should it have said? (optional — a correction lets this become a training
                pair; a bare 👎 only feeds failure clustering)
              </label>
              <textarea
                id="correction"
                className="rounded border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                rows={3}
                value={correction}
                onChange={(e) => setCorrection(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  onClick={() => sendFeedback(-1, correction)}
                  className="rounded bg-neutral-900 px-3 py-1 text-xs text-white dark:bg-neutral-100 dark:text-neutral-900"
                >
                  Submit
                </button>
                <button
                  onClick={() => sendFeedback(-1)}
                  className="rounded border border-neutral-300 px-3 py-1 text-xs dark:border-neutral-700"
                >
                  Skip correction
                </button>
              </div>
            </div>
          )}

          <div className="flex gap-3 text-xs text-neutral-400">
            <span>model: {response.model}</span>
            {response.latency_ms !== null && <span>{response.latency_ms} ms</span>}
          </div>
        </div>
      )}
    </main>
  );
}
