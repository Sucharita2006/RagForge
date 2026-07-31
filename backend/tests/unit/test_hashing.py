from app.ingestion.hashing import content_hash, normalize_content


def test_normalize_content_collapses_whitespace() -> None:
    assert normalize_content("Hello   world\n\n  foo") == "Hello world foo"


def test_content_hash_stable_across_trivial_reformatting() -> None:
    a = content_hash("Hello   world")
    b = content_hash("Hello world")
    c = content_hash("Hello\nworld")
    assert a == b == c


def test_content_hash_differs_for_different_content() -> None:
    assert content_hash("Hello world") != content_hash("Goodbye world")


def test_content_hash_is_sha256_hex() -> None:
    h = content_hash("anything")
    assert len(h) == 64
    int(h, 16)  # raises ValueError if not valid hex
