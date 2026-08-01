import uuid

from fastapi import APIRouter, Depends
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.generation.generator import generate_answer
from app.generation.prompts import PROMPT_VERSION
from app.models.answers import Answer
from app.models.queries import Query
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.ollama import OllamaProvider
from app.retrieval.assembly import assemble_context, expand_to_parents
from app.retrieval.cache import SemanticCache, get_corpus_version
from app.retrieval.pipeline import retrieve as run_retrieval_pipeline
from app.retrieval.query_transform import fetch_recent_history, rewrite_query
from app.schemas.query import ClaimOut, QueryRequest, QueryResponse

router = APIRouter(tags=["query"])
settings = get_settings()
tracer = trace.get_tracer(__name__)


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
            return QueryResponse(
                query_id=query_row.id,
                answer_id=uuid.UUID(cached["answer_id"]),
                claims=[ClaimOut(**c) for c in cached["claims"]],
                insufficient_context=cached["insufficient_context"],
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

        top_chunks = [f.chunk for f in fused[: settings.FINAL_TOP_K]]
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

        answer_row = Answer(
            query_id=query_row.id,
            claims=[c.model_dump() for c in answer.answer_sentences],
            insufficient_context=answer.insufficient_context,
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

        claims_dump = [c.model_dump() for c in answer.answer_sentences]
        await cache.set(
            query_embedding,
            {
                "answer_id": str(answer_row.id),
                "claims": claims_dump,
                "insufficient_context": answer_row.insufficient_context,
                "model": answer_row.model,
                "latency_ms": answer_row.latency_ms,
            },
            corpus_version,
        )

        return QueryResponse(
            query_id=query_row.id,
            answer_id=answer_row.id,
            claims=[ClaimOut(**c) for c in claims_dump],
            insufficient_context=answer_row.insufficient_context,
            trace_id=trace_id,
            model=answer_row.model,
            latency_ms=answer_row.latency_ms,
            cache_hit=False,
            rewritten_question=rewritten_text if rewritten_text != req.question else None,
        )
