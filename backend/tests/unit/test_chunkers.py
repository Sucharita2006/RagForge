from app.ingestion.chunkers import recursive_chunk
from app.providers.embeddings.base import EmbeddingProvider


class FakeEmbedder(EmbeddingProvider):
    """Word-count token proxy — fast and deterministic, no model load (SPEC.md
    §8.1 unit tests must be fast/mocked)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dim(self) -> int:
        return 1

    def count_tokens(self, text: str) -> int:
        return len(text.split())


def test_recursive_chunk_single_short_paragraph_stays_one_chunk() -> None:
    embedder = FakeEmbedder()
    text = "one two three four five"
    chunks = recursive_chunk(text, embedder, chunk_size=10, chunk_overlap=2)
    assert chunks == [text]


def test_recursive_chunk_splits_at_paragraph_boundaries_when_over_budget() -> None:
    embedder = FakeEmbedder()
    para_a = " ".join(f"a{i}" for i in range(5))  # 5 tokens
    para_b = " ".join(f"b{i}" for i in range(5))  # 5 tokens
    text = f"{para_a}\n\n{para_b}"
    chunks = recursive_chunk(text, embedder, chunk_size=5, chunk_overlap=0)
    assert len(chunks) == 2
    assert chunks[0] == para_a
    assert chunks[1] == para_b


def test_recursive_chunk_splits_a_single_long_paragraph_by_sentence() -> None:
    embedder = FakeEmbedder()
    sentences = [f"Sentence number {i} here." for i in range(6)]
    long_para = " ".join(sentences)
    chunks = recursive_chunk(long_para, embedder, chunk_size=8, chunk_overlap=0)
    assert len(chunks) > 1
    # every sentence's content must still be present somewhere in the output
    for s in sentences:
        assert any(s in c for c in chunks)


def test_recursive_chunk_applies_overlap_between_chunks() -> None:
    embedder = FakeEmbedder()
    # 4 paragraphs of 3 tokens each; chunk_size=6 fits exactly 2 per chunk.
    paras = [f"para{i}a para{i}b para{i}c" for i in range(4)]
    text = "\n\n".join(paras)
    chunks = recursive_chunk(text, embedder, chunk_size=6, chunk_overlap=3)
    assert len(chunks) == 3
    # the paragraph ending one chunk should reappear at the start of the next
    assert chunks[0].split("\n\n")[-1] == chunks[1].split("\n\n")[0]
    assert chunks[1].split("\n\n")[-1] == chunks[2].split("\n\n")[0]
