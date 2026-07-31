"use client";

import { useState } from "react";

interface Claim {
  text: string;
  citations: string[];
}

interface QueryResponse {
  query_id: string;
  answer_id: string;
  claims: Claim[];
  insufficient_context: boolean;
  trace_id: string | null;
  model: string;
  latency_ms: number | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Playground() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResponse(null);
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
          {response.insufficient_context && (
            <p className="rounded bg-amber-100 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              Insufficient grounded information to fully answer this question.
            </p>
          )}
          <div className="flex flex-col gap-2">
            {response.claims.map((claim, i) => (
              <p key={i} className="text-sm leading-relaxed">
                {claim.text}{" "}
                {claim.citations.length > 0 && (
                  <span className="text-xs text-neutral-400">[{claim.citations.join(", ")}]</span>
                )}
              </p>
            ))}
          </div>
          <div className="flex gap-3 text-xs text-neutral-400">
            <span>model: {response.model}</span>
            {response.latency_ms !== null && <span>{response.latency_ms} ms</span>}
          </div>
        </div>
      )}
    </main>
  );
}
