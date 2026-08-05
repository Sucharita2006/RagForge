import uuid

from fastapi import APIRouter, Depends
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.generation.generator import generate_answer
from app.generation.prompts import PROMPT_VERSION
from app.models.answers import Answer
from app.models.documents import Document
from app.models.queries import Query
from app.observability.cost import compute_cost_usd
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.ollama import OllamaProvider
from app.retrieval.assembly import assemble_context, expand_to_parents
from app.retrieval.cache import SemanticCache, get_corpus_version
from app.retrieval.fusion import FusedCandidate
from app.retrieval.pipeline import retrieve as run_retrieval_pipeline
from app.retrieval.query_transform import fetch_recent_history, rewrite_query
from app.schemas.query import ClaimOut, QueryRequest, QueryResponse, SourceOut
from app.trust.abstain import get_abstain_threshold, should_abstain
from app.trust.claims import verify_claims
from app.trust.confidence import compute_confidence
from app.trust.minicheck import get_minicheck_provider

router = APIRouter(tags=["query"])
settings = get_settings()
tracer = trace.get_tracer(__name__)


async def _sources_for(db: AsyncSession, candidates: list[FusedCandidate]) -> list[SourceOut]:
    """Top-level "which documents did we find" list (SPEC.md §3.3's
    abstention response carries this even with no answer) - distinct from
    each claim's own per-chunk citations."""
    document_ids = list({c.chunk.document_id for c in candidates})
    if not document_ids:
        return []
    result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
    docs_by_id = {d.id: d for d in result.scalars().all()}

    sources: list[SourceOut] = []
    seen_document_ids: set[uuid.UUID] = set()
    for candidate in candidates:
        doc = docs_by_id.get(candidate.chunk.document_id)
        if doc is None or doc.id in seen_document_ids:
            continue
        seen_document_ids.add(doc.id)
        sources.append(
            SourceOut(
                document_external_id=doc.external_id,
                title=doc.title,
                rerank_score=candidate.rerank_score,
            )
        )
    return sources


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, db: AsyncSession = Depends(get_db)) -> QueryResponse:
    with tracer.start_as_current_span(
        "query", attributes={"openinference.span.kind": "CHAIN"}
    ) as chain_span:
        trace_id = format(chain_span.get_span_context().trace_id, "032x")
        llm = OllamaProvider()
        embedder = get_embedding_provider()

        rewritten_text = req.question
        if req.session_id:
            history = await fetch_recent_history(db, req.session_id)
            if history:
                with tracer.start_as_current_span(
                    "rewrite_query", attributes={"openinference.span.kind": "LLM"}
                ):
                    rewritten_text = await rewrite_query(llm, history, req.question)

        query_row = Query(
            session_id=req.session_id,
            raw_text=req.question,
            rewritten_text=rewritten_text if rewritten_text != req.question else None,
            trace_id=trace_id,
        )
        db.add(query_row)
        await db.flush()

        with tracer.start_as_current_span(
            "embed_query", attributes={"openinference.span.kind": "EMBEDDING"}
        ):
            query_embedding = embedder.embed_query(rewritten_text)

        cache = SemanticCache()
        corpus_version = await get_corpus_version()
        cached = await cache.get(query_embedding, corpus_version)
        if cached is not None:
            query_row.cache_hit = True
            await db.commit()
            chain_span.set_attribute("query.cache_hit", True)
            chain_span.set_attribute("query.abstained", bool(cached["abstained"]))
            chain_span.set_attribute("query.confidence", float(cached["confidence"]))
            chain_span.set_attribute("query.cost_usd", 0.0)  # served from cache, no LLM call
            return QueryResponse(
                query_id=query_row.id,
                answer_id=uuid.UUID(cached["answer_id"]),
                claims=[ClaimOut(**c) for c in cached["claims"]],
                insufficient_context=cached["insufficient_context"],
                confidence=cached["confidence"],
                abstained=cached["abstained"],
                sources=[SourceOut(**s) for s in cached["sources"]],
                trace_id=trace_id,
                model=cached["model"],
                latency_ms=cached["latency_ms"],
                cache_hit=True,
                rewritten_question=rewritten_text if rewritten_text != req.question else None,
            )

        with tracer.start_as_current_span(
            "retrieve", attributes={"openinference.span.kind": "RETRIEVER"}
        ) as retriever_span:
            fused = await run_retrieval_pipeline(db, rewritten_text, query_embedding)
            retriever_span.set_attribute("retrieval.candidate_count", len(fused))

        top_candidates = fused[: settings.FINAL_TOP_K]
        top_chunks = [c.chunk for c in top_candidates]
        expanded_chunks = await expand_to_parents(db, top_chunks)
        context, used_chunks = assemble_context(expanded_chunks, settings.MAX_CONTEXT_TOKENS)
        valid_chunk_ids = {str(chunk.id) for chunk in used_chunks}

        with tracer.start_as_current_span(
            "generate",
            attributes={"openinference.span.kind": "LLM", "llm.model_name": llm.model_name},
        ) as llm_span:
            answer, raw = await generate_answer(llm, rewritten_text, context, valid_chunk_ids)
            llm_span.set_attribute("llm.token_count.prompt", raw["input_tokens"] or 0)
            llm_span.set_attribute("llm.token_count.completion", raw["output_tokens"] or 0)
            llm_span.set_attribute(
                "llm.cost_usd",
                compute_cost_usd(llm.model_name, raw["input_tokens"], raw["output_tokens"]),
            )

        with tracer.start_as_current_span(
            "verify_claims", attributes={"openinference.span.kind": "EVALUATOR"}
        ) as verify_span:
            minicheck = get_minicheck_provider()
            verified_claims = verify_claims(minicheck, answer.answer_sentences, used_chunks)
            confidence = compute_confidence(
                verified_claims, top_candidates, answer.insufficient_context
            )
            threshold = await get_abstain_threshold(db)
            abstained = should_abstain(confidence, threshold)
            verify_span.set_attribute("trust.confidence", confidence)
            verify_span.set_attribute("trust.abstained", abstained)
            verify_span.set_attribute("trust.claim_count", len(verified_claims))
            verify_span.set_attribute(
                "trust.unsupported_claim_count",
                sum(1 for c in verified_claims if c.verdict == "unsupported"),
            )

        # root-span attributes the Analytics page aggregates over (SPEC.md §3.8:
        # cache hit rate, abstention rate, cost/query) - set on CHAIN so one
        # query contributes exactly one row to each rate, regardless of how
        # many child spans it produced.
        chain_span.set_attribute("query.cache_hit", False)
        chain_span.set_attribute("query.abstained", abstained)
        chain_span.set_attribute("query.confidence", confidence)
        chain_span.set_attribute(
            "query.cost_usd",
            compute_cost_usd(llm.model_name, raw["input_tokens"], raw["output_tokens"]),
        )

        sources = await _sources_for(db, top_candidates)

        answer_row = Answer(
            query_id=query_row.id,
            claims=[c.model_dump() for c in verified_claims],
            insufficient_context=answer.insufficient_context,
            confidence=confidence,
            abstained=abstained,
            model=llm.model_name,
            prompt_version=PROMPT_VERSION,
            input_tokens=raw["input_tokens"],
            output_tokens=raw["output_tokens"],
            latency_ms=raw["latency_ms"],
            trace_id=trace_id,
        )
        db.add(answer_row)
        await db.commit()
        await db.refresh(answer_row)

        # an abstention response carries no partial answer (SPEC.md §3.3) -
        # the full verified claims still land in the DB row above for
        # observability/eval, just not in what the user sees.
        response_claims = [] if abstained else [ClaimOut(**c.model_dump()) for c in verified_claims]

        await cache.set(
            query_embedding,
            {
                "answer_id": str(answer_row.id),
                "claims": [c.model_dump() for c in response_claims],
                "insufficient_context": answer_row.insufficient_context,
                "confidence": confidence,
                "abstained": abstained,
                "sources": [s.model_dump() for s in sources],
                "model": answer_row.model,
                "latency_ms": answer_row.latency_ms,
            },
            corpus_version,
        )

        return QueryResponse(
            query_id=query_row.id,
            answer_id=answer_row.id,
            claims=response_claims,
            insufficient_context=answer_row.insufficient_context,
            confidence=confidence,
            abstained=abstained,
            sources=sources,
            trace_id=trace_id,
            model=answer_row.model,
            latency_ms=answer_row.latency_ms,
            cache_hit=False,
            rewritten_question=rewritten_text if rewritten_text != req.question else None,
        )
