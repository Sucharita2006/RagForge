import logging
import uuid

from app.config import get_settings
from app.db.session import async_session_maker
from app.ingestion.chunkers import recursive_chunk
from app.ingestion.hashing import content_hash
from app.ingestion.parsers import parse_document
from app.models.chunks import Chunk
from app.models.documents import Document
from app.providers.embeddings.bge_small import get_embedding_provider

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


async def ingest_document(document_id: uuid.UUID, file_path: str) -> None:
    """Parse -> chunk -> embed -> store (SPEC.md §3.1, Phase 1 subset: no
    contextual enrichment, incremental re-ingest, or security scan yet —
    those land in Phase 2/7)."""
    embedder = get_embedding_provider()
    await _set_status(document_id, "processing")

    try:
        text, parser_used = parse_document(file_path)
        chunk_texts = recursive_chunk(text, embedder, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        if not chunk_texts:
            raise ValueError(f"no extractable text in {file_path}")

        embeddings = embedder.embed_documents(chunk_texts)

        async with async_session_maker() as session:
            for chunk_text, embedding in zip(chunk_texts, embeddings, strict=True):
                session.add(
                    Chunk(
                        document_id=document_id,
                        content=chunk_text,
                        token_count=embedder.count_tokens(chunk_text),
                        content_hash=content_hash(chunk_text),
                        embedding=embedding,
                        embedding_model=embedder.model_name,
                    )
                )
            await session.commit()

        await _set_status(document_id, "ready", parser=parser_used)
        logger.info("Ingested %s: %d chunks via %s", file_path, len(chunk_texts), parser_used)
    except Exception:
        logger.exception("Ingestion failed for %s", file_path)
        await _set_status(document_id, "failed")
        raise
