"""The passages an answer returns are the chunks its claims cite, in
first-cited order, each once. Needs a migrated database at DATABASE_URL; the
transaction is rolled back."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.query import _passages_for
from app.config import get_settings
from app.ingestion.hashing import content_hash
from app.models.chunks import Chunk
from app.models.documents import Document
from app.schemas.query import ClaimOut


async def test_passages_follow_first_citation_order_once_each() -> None:
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    async with AsyncSession(engine) as db:
        document = Document(filename="p.pdf", title="A paper", external_id="2401.00001")
        db.add(document)
        await db.flush()
        first, second = (
            Chunk(
                document_id=document.id,
                content=body,
                token_count=3,
                content_hash=content_hash(body),
            )
            for body in ("First passage.", "Second passage.")
        )
        db.add_all([first, second])
        await db.flush()

        claims = [
            ClaimOut(text="One.", citations=[str(second.id)]),
            # cites a chunk that was not in the context, then repeats one
            ClaimOut(text="Two.", citations=["not-a-chunk", str(first.id), str(second.id)]),
        ]
        passages = await _passages_for(db, claims, [first, second])

        assert [p.text for p in passages] == ["Second passage.", "First passage."]
        assert {p.title for p in passages} == {"A paper"}
        assert await _passages_for(db, [], [first, second]) == []
        await db.rollback()
    await engine.dispose()
