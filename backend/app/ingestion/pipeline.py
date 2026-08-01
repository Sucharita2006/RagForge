import logging
import uuid

from sqlalchemy import delete, select

from app.config import get_settings
from app.db.session import async_session_maker
from app.ingestion.chunkers import recursive_chunk
from app.ingestion.enrich import enrichment_enabled, generate_context_prefix
from app.ingestion.hashing import content_hash
from app.ingestion.parsers import parse_document
from app.models.chunks import Chunk
from app.models.documents import Document
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.gemini import GeminiProvider
from app.retrieval.cache import bump_corpus_version

logger = logging.getLogger(__name__)
settings = get_settings()


async def _set_status(document_id: uuid.UUID, status: str, parser: str | None = None) -> None:
    async with async_session_maker() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = status
        if parser is not None:
            document.parser = parser
        await session.commit()


def _build_parent_child_texts(
    text: str, embedder: EmbeddingProvider
) -> tuple[list[str], list[list[str]]]:
    """SPEC.md §3.2 step 7: split into PARENT_CHUNK_SIZE parents, each split
    again into CHUNK_SIZE children."""
    parent_texts = recursive_chunk(text, embedder, settings.PARENT_CHUNK_SIZE, 0)
    child_texts_per_parent = [
        recursive_chunk(p, embedder, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        for p in parent_texts
    ]
    return parent_texts, child_texts_per_parent


async def _store_chunks(
    document_id: uuid.UUID,
    document_title: str,
    embedder: EmbeddingProvider,
    parent_texts: list[str],
    child_texts_per_parent: list[list[str]],
    reusable_embeddings: dict[str, list[float]],
) -> tuple[int, int, int]:
    """Insert parent + child Chunk rows.

    `reusable_embeddings` maps a child's content_hash to a previously-computed
    embedding (incremental re-ingest, SPEC.md §3.1: "re-embeds only chunks
    whose hash changed"); anything not in that map gets embedded fresh.

    Contextual enrichment (SPEC.md §3.1, feature-flagged + requires a Gemini
    key — see enrichment_enabled()): for freshly-embedded children only (a
    reused embedding's prefix, if any, is already baked in from before), a
    situating prefix is generated and prepended to the text actually sent to
    the embedder, while `content`/`context_prefix` are stored separately so
    the generation-time context stays exactly the chunk's own text.

    Returns (n_parents, n_children, n_reused).
    """
    all_child_texts = [c for group in child_texts_per_parent for c in group]
    hashes = [content_hash(t) for t in all_child_texts]
    parent_for_child = [
        parent_text
        for parent_text, child_texts in zip(parent_texts, child_texts_per_parent, strict=True)
        for _ in child_texts
    ]

    context_prefixes: list[str | None] = [None] * len(all_child_texts)
    enrichment_llm = GeminiProvider() if enrichment_enabled() else None

    texts_to_embed: list[str] = []
    indices_to_embed: list[int] = []
    for i, (child_text, h) in enumerate(zip(all_child_texts, hashes, strict=True)):
        if h in reusable_embeddings:
            continue
        indices_to_embed.append(i)
        if enrichment_llm is not None:
            prefix = await generate_context_prefix(
                enrichment_llm, document_title, parent_for_child[i], child_text
            )
            context_prefixes[i] = prefix
            texts_to_embed.append(f"{prefix}\n{child_text}")
        else:
            texts_to_embed.append(child_text)

    fresh_embeddings = iter(embedder.embed_documents(texts_to_embed) if texts_to_embed else [])
    embeddings_by_index: list[list[float] | None] = [None] * len(all_child_texts)
    n_reused = 0
    for i, h in enumerate(hashes):
        if h in reusable_embeddings:
            embeddings_by_index[i] = reusable_embeddings[h]
            n_reused += 1
    for i in indices_to_embed:
        embeddings_by_index[i] = next(fresh_embeddings)

    idx = 0
    async with async_session_maker() as session:
        for parent_text, child_texts in zip(parent_texts, child_texts_per_parent, strict=True):
            parent_chunk = Chunk(
                document_id=document_id,
                content=parent_text,
                token_count=embedder.count_tokens(parent_text),
                content_hash=content_hash(parent_text),
                is_parent=True,
            )
            session.add(parent_chunk)
            await session.flush()  # need parent_chunk.id for children's FK

            for child_text in child_texts:
                session.add(
                    Chunk(
                        document_id=document_id,
                        parent_id=parent_chunk.id,
                        content=child_text,
                        context_prefix=context_prefixes[idx],
                        token_count=embedder.count_tokens(child_text),
                        content_hash=hashes[idx],
                        embedding=embeddings_by_index[idx],
                        embedding_model=embedder.model_name,
                    )
                )
                idx += 1
        await session.commit()

    return len(parent_texts), len(all_child_texts), n_reused


async def _get_document_title(document_id: uuid.UUID) -> str:
    async with async_session_maker() as session:
        document = await session.get(Document, document_id)
        return (document.title or document.filename) if document else ""


async def ingest_document(document_id: uuid.UUID, file_path: str) -> None:
    """Parse -> parent/child chunk -> embed children -> store (SPEC.md §3.1)."""
    embedder = get_embedding_provider()
    await _set_status(document_id, "processing")

    try:
        document_title = await _get_document_title(document_id)
        text, parser_used = parse_document(file_path)
        parent_texts, child_texts_per_parent = _build_parent_child_texts(text, embedder)
        if not parent_texts or not any(child_texts_per_parent):
            raise ValueError(f"no extractable text in {file_path}")

        n_parents, n_children, _ = await _store_chunks(
            document_id,
            document_title,
            embedder,
            parent_texts,
            child_texts_per_parent,
            reusable_embeddings={},
        )

        await bump_corpus_version()
        await _set_status(document_id, "ready", parser=parser_used)
        logger.info(
            "Ingested %s: %d parent / %d child chunks via %s",
            file_path,
            n_parents,
            n_children,
            parser_used,
        )
    except Exception:
        logger.exception("Ingestion failed for %s", file_path)
        await _set_status(document_id, "failed")
        raise


async def reingest_document(document_id: uuid.UUID, file_path: str) -> None:
    """Incremental re-ingestion (SPEC.md §3.1): re-embeds only chunks whose
    content changed; unchanged chunks reuse their existing embedding. Old
    chunks are replaced (matched by content_hash, not by position — content
    earlier in the doc shifting doesn't spuriously invalidate later chunks
    whose text didn't change)."""
    embedder = get_embedding_provider()
    await _set_status(document_id, "processing")

    try:
        document_title = await _get_document_title(document_id)
        async with async_session_maker() as session:
            result = await session.execute(
                select(Chunk).where(Chunk.document_id == document_id, Chunk.is_parent.is_(False))
            )
            existing_children = result.scalars().all()
            reusable_embeddings = {
                c.content_hash: c.embedding for c in existing_children if c.embedding is not None
            }

        text, parser_used = parse_document(file_path)
        parent_texts, child_texts_per_parent = _build_parent_child_texts(text, embedder)
        if not parent_texts or not any(child_texts_per_parent):
            raise ValueError(f"no extractable text in {file_path}")

        async with async_session_maker() as session:
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            await session.commit()

        n_parents, n_children, n_reused = await _store_chunks(
            document_id,
            document_title,
            embedder,
            parent_texts,
            child_texts_per_parent,
            reusable_embeddings,
        )

        await bump_corpus_version()
        await _set_status(document_id, "ready", parser=parser_used)
        logger.info(
            "Re-ingested %s: %d parent / %d child chunks via %s (%d/%d embeddings reused)",
            file_path,
            n_parents,
            n_children,
            parser_used,
            n_reused,
            n_children,
        )
    except Exception:
        logger.exception("Re-ingestion failed for %s", file_path)
        await _set_status(document_id, "failed")
        raise
