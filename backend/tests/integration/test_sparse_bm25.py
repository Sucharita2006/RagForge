"""BM25 lives in SQL, so only a real Postgres can check it. Needs a migrated
database at DATABASE_URL (evals.yml provides one). Everything happens in one
transaction that is rolled back, so no rows are left behind."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.ingestion.hashing import content_hash
from app.models.chunks import Chunk
from app.models.documents import Document
from app.retrieval.sparse import sparse_search


async def test_bm25_matches_any_term_and_ranks_by_rarity_and_frequency() -> None:
    texts = {
        "twice": "The quokka met another quokka near the harbour wall.",
        "once": "A quokka sat near the harbour wall in the afternoon.",
        "common_only": "Boats leave the harbour wall each morning at dawn.",
        "unrelated": "Sourdough needs a long, slow rise.",
    }
    # Its own engine, not app.db.session's: that pool may hold connections
    # opened on an earlier test's event loop, which asyncpg refuses to reuse.
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    async with AsyncSession(engine) as db:
        document = Document(filename="bm25-test", mime="text/plain", status="ready")
        db.add(document)
        await db.flush()
        chunks = {
            name: Chunk(
                document_id=document.id,
                content=body,
                token_count=len(body.split()),
                content_hash=content_hash(body),
            )
            for name, body in texts.items()
        }
        db.add_all(chunks.values())
        await db.flush()
        names = {chunk.id: name for name, chunk in chunks.items()}

        # No chunk says "live": the old all-terms-required query returned nothing here.
        results = await sparse_search(
            db, "Where does the quokka live near the harbour?", 10, document.id
        )

        assert [names[chunk.id] for chunk, _ in results] == ["twice", "once", "common_only"]
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True) and scores[-1] > 0
        await db.rollback()
    await engine.dispose()
