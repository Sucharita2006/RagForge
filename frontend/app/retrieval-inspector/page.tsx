"use client";

import { useState } from "react";

interface Candidate {
  chunk_id: string;
  document_id: string;
  document_external_id: string | null;
  document_title: string | null;
  content_preview: string;
  dense_score: number | null;
  dense_rank: number | null;
  sparse_score: number | null;
  sparse_rank: number | null;
  rrf_score: number | null;
  rerank_score: number | null;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function fmt(n: number | null): string {
  return n === null ? "—" : n.toFixed(4);
}

export default function RetrievalInspector() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(10);
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setCandidates(null);
    try {
      const res = await fetch(`${API_URL}/api/retrieve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: topK }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const data = (await res.json()) as { candidates: Candidate[] };
      setCandidates(data.candidates);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Retrieval Inspector</h1>
        <p className="text-sm text-neutral-500">
          See every candidate&apos;s dense score, sparse rank, RRF score, and rerank score
          (SPEC.md §3.2).
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          className="flex-1 rounded border border-neutral-300 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          placeholder="Ask a question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <input
          type="number"
          min={1}
          max={50}
          className="w-20 rounded border border-neutral-300 px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-neutral-900 px-4 py-2 text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {candidates && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-neutral-300 text-left dark:border-neutral-700">
                <th className="p-2">#</th>
                <th className="p-2">Document</th>
                <th className="p-2">Preview</th>
                <th className="p-2 text-right">Dense</th>
                <th className="p-2 text-right">Sparse</th>
                <th className="p-2 text-right">RRF</th>
                <th className="p-2 text-right">Rerank</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, i) => (
                <tr key={c.chunk_id} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="p-2 text-neutral-400">{i + 1}</td>
                  <td className="max-w-[200px] truncate p-2" title={c.document_title ?? undefined}>
                    {c.document_title ?? c.document_external_id ?? c.document_id.slice(0, 8)}
                  </td>
                  <td className="max-w-[320px] truncate p-2 text-neutral-500" title={c.content_preview}>
                    {c.content_preview}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {fmt(c.dense_score)}
                    {c.dense_rank && <span className="text-neutral-400"> (#{c.dense_rank})</span>}
                  </td>
                  <td className="p-2 text-right tabular-nums">
                    {fmt(c.sparse_score)}
                    {c.sparse_rank && <span className="text-neutral-400"> (#{c.sparse_rank})</span>}
                  </td>
                  <td className="p-2 text-right tabular-nums">{fmt(c.rrf_score)}</td>
                  <td className="p-2 text-right font-medium tabular-nums">{fmt(c.rerank_score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
