"""CI fixture corpus + golden set (SPEC.md §8.7 evals.yml).

The real golden set (eval-datasets/v1/) needs the real 40-document corpus
ingested, embedded, and indexed - not feasible to rebuild from scratch on
every PR in a free GitHub Actions runner. This generates a tiny, synthetic,
CLEARLY SEPARATE fixture corpus (a handful of one-topic-each PDFs, built by
hand-rolling minimal valid PDF bytes so no new dependency is needed just
for this) plus a matching mini golden set, so `evals.yml`'s per-PR fast
path has something real to ingest and query end-to-end (DECISIONS.md
2026-08-01 records why this isn't literally a subset of the v1 golden
set, unlike SPEC.md §8.3's original "30-item CI subset" wording).

Run on the host (no DB/LLM access needed): python scripts/generate_ci_fixtures.py
"""

import json
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "ci_corpus"
GOLDEN_PATH = REPO_ROOT / "eval-datasets" / "ci-fixture" / "golden.jsonl"


class FixtureDoc(NamedTuple):
    external_id: str
    title: str
    lines: list[str]


DOCUMENTS = [
    FixtureDoc(
        external_id="ci-fixture-llamas",
        title="Llama Husbandry Basics",
        lines=[
            "Llamas are domesticated South American camelids, related to alpacas.",
            "A typical adult llama weighs between 130 and 200 kilograms.",
            "Llamas are commonly used as pack animals due to their strength and endurance.",
        ],
    ),
    FixtureDoc(
        external_id="ci-fixture-sourdough",
        title="Sourdough Bread Fundamentals",
        lines=[
            "Sourdough bread relies on a natural fermentation starter of flour and water.",
            "The starter culture contains wild yeast and lactic acid bacteria.",
            "A mature sourdough starter typically takes five to seven days to develop.",
        ],
    ),
    FixtureDoc(
        external_id="ci-fixture-lighthouses",
        title="Coastal Lighthouse Design",
        lines=[
            "Lighthouses use a rotating Fresnel lens to project light over long distances.",
            "The Fresnel lens was invented in 1822 by Augustin-Jean Fresnel.",
            "Modern lighthouses are largely automated and require minimal staffing.",
        ],
    ),
    FixtureDoc(
        external_id="ci-fixture-volcanoes",
        title="Volcanic Eruption Classification",
        lines=[
            "The Volcanic Explosivity Index rates eruptions on a scale from 0 to 8.",
            "Effusive eruptions produce slow-moving lava flows rather than explosions.",
            "Stratovolcanoes are steep-sided, built from alternating lava and ash layers.",
        ],
    ),
]

GOLDEN_ITEMS = [
    {
        "id": "ci_001",
        "type": "single_hop",
        "question": "How much does a typical adult llama weigh?",
        "expected_arxiv_ids": ["ci-fixture-llamas"],
        "reference_answer": "Between 130 and 200 kilograms.",
        "unanswerable": False,
    },
    {
        "id": "ci_002",
        "type": "single_hop",
        "question": "What two microorganisms does a sourdough starter culture contain?",
        "expected_arxiv_ids": ["ci-fixture-sourdough"],
        "reference_answer": "Wild yeast and lactic acid bacteria.",
        "unanswerable": False,
    },
    {
        "id": "ci_003",
        "type": "single_hop",
        "question": "Who invented the Fresnel lens used in lighthouses, and when?",
        "expected_arxiv_ids": ["ci-fixture-lighthouses"],
        "reference_answer": "Augustin-Jean Fresnel, in 1822.",
        "unanswerable": False,
    },
    {
        "id": "ci_004",
        "type": "single_hop",
        "question": "What scale is used to rate the explosivity of volcanic eruptions?",
        "expected_arxiv_ids": ["ci-fixture-volcanoes"],
        "reference_answer": "The Volcanic Explosivity Index, rated 0 to 8.",
        "unanswerable": False,
    },
    {
        "id": "ci_005",
        "type": "unanswerable",
        "question": "What is the average lifespan of a bottlenose dolphin in captivity?",
        "expected_arxiv_ids": [],
        "reference_answer": None,
        "unanswerable": True,
    },
]


def make_pdf(lines: list[str]) -> bytes:
    """Hand-rolled minimal single-page PDF - no PDF-writing dependency
    needed just to produce a handful of tiny CI fixture files."""
    content_lines = []
    y = 750
    for line in lines:
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"BT /F1 12 Tf 50 {y} Td ({esc}) Tj ET")
        y -= 16
    content = "\n".join(content_lines).encode()

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]

    out = bytearray()
    out += b"%PDF-1.4\n"
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(out)


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for doc in DOCUMENTS:
        pdf_bytes = make_pdf([doc.title + "."] + doc.lines)
        (FIXTURE_DIR / f"{doc.external_id}.pdf").write_bytes(pdf_bytes)
    (FIXTURE_DIR / "manifest.json").write_text(
        json.dumps([doc._asdict() for doc in DOCUMENTS], indent=2)
    )
    print(f"Wrote {len(DOCUMENTS)} fixture PDFs to {FIXTURE_DIR}")

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN_PATH.open("w") as f:
        for item in GOLDEN_ITEMS:
            f.write(json.dumps(item) + "\n")
    print(f"Wrote {len(GOLDEN_ITEMS)} golden items to {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
