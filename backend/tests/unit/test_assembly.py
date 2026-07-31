import uuid

from app.models.chunks import Chunk
from app.retrieval.assembly import assemble_context


def make_chunk(content: str, token_count: int) -> Chunk:
    return Chunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        token_count=token_count,
        content_hash="x" * 64,
        embedding=[0.0] * 384,
        embedding_model="fake",
    )


def test_assemble_context_includes_all_chunks_within_budget() -> None:
    chunks = [make_chunk("first", 100), make_chunk("second", 100)]
    context, used = assemble_context(chunks, max_context_tokens=1000)
    assert len(used) == 2
    assert "first" in context
    assert "second" in context


def test_assemble_context_stops_at_token_budget_in_rank_order() -> None:
    """Chunks arrive pre-sorted by descending similarity; once the budget is
    exhausted we stop rather than skip ahead to a smaller lower-ranked chunk
    (predictable rank-respecting behavior over squeezing in extra content)."""
    chunks = [make_chunk("best", 400), make_chunk("second_best", 400), make_chunk("small", 50)]
    context, used = assemble_context(chunks, max_context_tokens=500)
    assert len(used) == 1
    assert used[0].content == "best"
    assert "second_best" not in context
    assert "small" not in context


def test_assemble_context_labels_each_chunk_with_its_id() -> None:
    chunk = make_chunk("hello world", 10)
    context, _used = assemble_context([chunk], max_context_tokens=100)
    assert f"[chunk_id={chunk.id}]" in context


def test_assemble_context_empty_input() -> None:
    context, used = assemble_context([], max_context_tokens=100)
    assert context == ""
    assert used == []
