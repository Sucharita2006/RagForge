from app.ingestion import parsers


def test_parse_document_removes_nul_characters(monkeypatch) -> None:
    # Postgres rejects NUL in text; one such character used to fail a whole document.
    monkeypatch.setattr(parsers, "_extract", lambda path: ("Table\x00 1\x00", "pypdf"))
    assert parsers.parse_document("paper.pdf") == ("Table 1", "pypdf")
