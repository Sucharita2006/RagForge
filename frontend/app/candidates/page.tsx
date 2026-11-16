"use client";

import { use, useEffect, useState } from "react";

import { Empty, Lead, PageHead, Problem, Rows, Scroll, Sign } from "@/components/ui";
import { message, send } from "@/lib/api";
import { fixed } from "@/lib/format";

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

function Scored({ score, rank, digits }: { score: number | null; rank: number | null; digits: number }) {
  if (score === null) return <span className="text-ink-3">–</span>;
  return (
    <span>
      {score.toFixed(digits)}
      {rank !== null && <span className="block text-sm text-ink-3">rank {rank}</span>}
    </span>
  );
}

function retrieve(question: string, top_k: number): Promise<Candidate[]> {
  return send<{ candidates: Candidate[] }>("/retrieve", { question, top_k }).then(
    (data) => data.candidates,
  );
}

export default function Candidates({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  // The Query page's sign arrives with ?q=...: that question runs once, on arrival.
  const { q } = use(searchParams);
  const [question, setQuestion] = useState(q ?? "");
  const [topK, setTopK] = useState(10);
  const [loading, setLoading] = useState(Boolean(q));
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!q) return;
    let live = true;
    retrieve(q, 10)
      .then((found) => {
        if (live) setCandidates(found);
      })
      .catch((err) => {
        if (live) setError(message(err));
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [q]);

  async function search(text: string, k: number) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setCandidates(null);
    try {
      setCandidates(await retrieve(trimmed, k));
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }

  const reranks = (candidates ?? []).flatMap((c) => c.rerank_score ?? []);
  const low = Math.min(...reranks);
  const span = Math.max(...reranks) - low || 1;

  return (
    <>
      <PageHead
        title="Candidates"
        purpose="One question, every candidate, and the score each stage gave it. Nothing is generated here, so it answers in seconds."
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          search(question, topK);
        }}
        className="flex max-w-4xl flex-col gap-3 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <label htmlFor="question" className="label">
            Question
          </label>
          <input
            id="question"
            className="field"
            placeholder="What do the papers say about…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </div>
        <div className="sm:w-28">
          <label htmlFor="top-k" className="label">
            Candidates
          </label>
          <input
            id="top-k"
            type="number"
            min={1}
            max={50}
            className="field tabular-nums"
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
          />
        </div>
        <button type="submit" disabled={loading || !question.trim()} className="btn btn-primary pl-2">
          <Lead />
          {loading ? "Searching" : "Search"}
        </button>
      </form>

      <div className="mt-8">
        {error && <Problem>{error}</Problem>}
        {loading && <Rows count={6} />}

        {!loading && !candidates && !error && (
          <Empty title="Four scores for every candidate">
            <dl className="space-y-2">
              <div>
                <dt className="inline font-bold text-ink">Dense. </dt>
                <dd className="inline">
                  Cosine similarity between the question&apos;s embedding and the passage&apos;s.
                </dd>
              </div>
              <div>
                <dt className="inline font-bold text-ink">BM25. </dt>
                <dd className="inline">
                  Keyword score over the passage&apos;s lexemes. A dash means no word of the
                  question put it in the keyword list.
                </dd>
              </div>
              <div>
                <dt className="inline font-bold text-ink">Fused. </dt>
                <dd className="inline">Reciprocal rank fusion of the two rankings.</dd>
              </div>
              <div>
                <dt className="inline font-bold text-ink">Rerank. </dt>
                <dd className="inline">
                  The cross-encoder&apos;s score for question and passage read together. It sets
                  the final order.
                </dd>
              </div>
            </dl>
          </Empty>
        )}

        {candidates && candidates.length === 0 && (
          <Empty title="Nothing retrieved">
            <p>
              The corpus has no passages yet. Seed it with{" "}
              <code className="font-mono text-[0.875em] text-ink">
                python scripts/seed_demo_corpus.py
              </code>{" "}
              and search again.
            </p>
          </Empty>
        )}

        {candidates && candidates.length > 0 && (
          <Scroll label="Retrieved candidates">
            <table className="data stack md:min-w-[58rem]">
              <colgroup>
                <col className="w-16" />
                <col />
                <col className="w-28" />
                <col className="w-28" />
                <col className="w-24" />
                <col className="w-52" />
              </colgroup>
              <thead>
                <tr>
                  <th>Final</th>
                  <th>Passage</th>
                  <th className="num">Dense</th>
                  <th className="num">BM25</th>
                  <th className="num">Fused</th>
                  <th>Rerank</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c, i) => (
                  <tr key={c.chunk_id}>
                    <td className="wide-only">
                      <span className="sq sq-sm">{i + 1}</span>
                    </td>
                    <td>
                      <span className="flex items-center gap-2 font-semibold">
                        <span className="sq sq-sm md:hidden">{i + 1}</span>
                        <span className="truncate">
                          {c.document_title ?? c.document_external_id ?? c.document_id.slice(0, 8)}
                        </span>
                      </span>
                      <span className="mt-0.5 line-clamp-2 text-sm text-ink-2">
                        {c.content_preview}
                      </span>
                    </td>
                    <td className="num" data-label="Dense">
                      <Scored score={c.dense_score} rank={c.dense_rank} digits={3} />
                    </td>
                    <td className="num" data-label="BM25">
                      <Scored score={c.sparse_score} rank={c.sparse_rank} digits={2} />
                    </td>
                    <td className="num" data-label="Fused">
                      {fixed(c.rrf_score, 4)}
                    </td>
                    <td data-label="Rerank">
                      {c.rerank_score === null ? (
                        <span className="text-ink-3">–</span>
                      ) : (
                        <span className="flex items-center gap-3 max-md:w-1/2">
                          <span className="w-14 text-right font-semibold">
                            {c.rerank_score.toFixed(2)}
                          </span>
                          <span className="h-2.5 flex-1 rounded-full bg-concourse">
                            <span
                              className="block h-2.5 rounded-full bg-ink"
                              style={{
                                width: `${Math.max(4, ((c.rerank_score - low) / span) * 100)}%`,
                              }}
                            />
                          </span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Scroll>
        )}
      </div>

      {candidates && candidates.length > 0 && question.trim() && (
        <div className="mt-12 max-w-xl">
          <Sign
            href={`/?q=${encodeURIComponent(question.trim())}`}
            title="Answer this question"
            detail="Generate an answer and check every sentence against these passages"
          />
        </div>
      )}
    </>
  );
}
