import uuid

from app.models.chunks import Chunk
from app.retrieval.assembly import assemble_context, reorder_lost_in_the_middle


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


def test_reorder_lost_in_the_middle_puts_best_at_edges_worst_in_middle() -> None:
    """Best-ranked chunks should end up at the start *and* end of the
    sequence; the lowest-ranked chunk should land in the middle, where LLM
    attention over long contexts tends to be weakest (SPEC.md §3.2 step 7)."""
    chunks = [make_chunk(name, 10) for name in ["1st", "2nd", "3rd", "4th", "5th"]]
    reordered = reorder_lost_in_the_middle(chunks)
    contents = [c.content for c in reordered]
    assert contents[0] == "1st"
    assert contents[-1] == "2nd"
    assert contents[len(contents) // 2] == "5th"  # worst-ranked buried in the middle


def test_reorder_lost_in_the_middle_preserves_all_chunks() -> None:
    chunks = [make_chunk(str(i), 10) for i in range(6)]
    reordered = reorder_lost_in_the_middle(chunks)
    assert {c.content for c in reordered} == {c.content for c in chunks}
    assert len(reordered) == len(chunks)


def test_reorder_lost_in_the_middle_empty_and_single() -> None:
    assert reorder_lost_in_the_middle([]) == []
    single = [make_chunk("only", 10)]
    assert reorder_lost_in_the_middle(single) == single
