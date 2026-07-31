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
from app.retrieval.assembly import assemble_context
from app.retrieval.dense import dense_search
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

        query_row = Query(raw_text=req.question, trace_id=trace_id)
        db.add(query_row)
        await db.flush()

        embedder = get_embedding_provider()
        with tracer.start_as_current_span(
            "embed_query", attributes={"openinference.span.kind": "EMBEDDING"}
        ):
            query_embedding = embedder.embed_query(req.question)

        with tracer.start_as_current_span(
            "dense_retrieve", attributes={"openinference.span.kind": "RETRIEVER"}
        ) as retriever_span:
            results = await dense_search(
                db, query_embedding, settings.DENSE_TOP_K, settings.HNSW_EF_SEARCH
            )
            retriever_span.set_attribute("retrieval.candidate_count", len(results))

        chunks = [chunk for chunk, _score in results]
        context, used_chunks = assemble_context(chunks, settings.MAX_CONTEXT_TOKENS)
        valid_chunk_ids = {str(chunk.id) for chunk in used_chunks}

        llm = OllamaProvider()
        with tracer.start_as_current_span(
            "generate",
            attributes={"openinference.span.kind": "LLM", "llm.model_name": llm.model_name},
        ) as llm_span:
            answer, raw = await generate_answer(llm, req.question, context, valid_chunk_ids)
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

        return QueryResponse(
            query_id=query_row.id,
            answer_id=answer_row.id,
            claims=[ClaimOut(**c) for c in answer_row.claims],
            insufficient_context=answer_row.insufficient_context,
            trace_id=trace_id,
            model=answer_row.model,
            latency_ms=answer_row.latency_ms,
        )
