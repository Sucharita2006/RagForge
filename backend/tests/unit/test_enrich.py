from app.ingestion.enrich import build_enrichment_prompt


def test_build_enrichment_prompt_includes_title_and_chunk() -> None:
    prompt = build_enrichment_prompt("My Paper", "Parent section text.", "The chunk itself.")
    assert "My Paper" in prompt
    assert "Parent section text." in prompt
    assert "The chunk itself." in prompt


def test_build_enrichment_prompt_truncates_long_parent_content() -> None:
    long_parent = "x" * 5000
    prompt = build_enrichment_prompt("Title", long_parent, "chunk")
    # capped to 2000 chars so the enrichment call itself stays cheap
    assert prompt.count("x") == 2000
