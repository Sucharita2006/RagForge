"""Seed the demo corpus (SPEC.md scripts/seed_demo_corpus.py).

Discovers real, current arXiv LLM/RAG paper ids via the arXiv API rather
than a hardcoded id list (a hand-typed list risks silently including a
misremembered id — DECISIONS.md), downloads the PDFs, POSTs each to
/api/ingest, and polls document status until ready/failed.

Run with the stack up (`docker compose up -d`) from the repo root:
    pip install -r scripts/requirements.txt
    python scripts/seed_demo_corpus.py                    # today's top matches
    python scripts/seed_demo_corpus.py --from-golden-set  # the golden set's papers
"""

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

API_BASE = os.environ.get("RAGFORGE_API", "http://localhost:8000/api")
GOLDEN_SET = Path(__file__).resolve().parent.parent / "eval-datasets" / "v1" / "full.jsonl"
ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Topic queries, not specific paper ids — lets arXiv's own index surface the
# actual current top matches instead of trusting a memorized id list.
SEARCH_QUERIES: list[tuple[str, int]] = [
    ('all:"retrieval augmented generation"', 8),
    ('all:"dense passage retrieval"', 4),
    ('all:"large language models" AND cat:cs.CL', 8),
    ('all:"chain of thought prompting"', 4),
    ('all:"in-context learning"', 4),
    ('all:"instruction tuning" AND cat:cs.CL', 4),
    ('all:"transformer language model"', 4),
    ('all:"open domain question answering"', 4),
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "seed_corpus"


def discover_papers() -> list[dict]:
    seen: set[str] = set()
    papers: list[dict] = []
    for query, n in SEARCH_QUERIES:
        try:
            resp = httpx.get(
                ARXIV_API,
                params={
                    "search_query": query,
                    "start": 0,
                    "max_results": n,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                },
                timeout=30.0,
                follow_redirects=True,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception as e:
            print(f"[warn] arXiv search failed for {query!r}: {e}")
            continue

        papers += _papers_in(root, seen)
        time.sleep(3)  # arXiv API etiquette: >=3s between requests
    return papers


def _papers_in(root: ET.Element, seen: set[str]) -> list[dict]:
    papers = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        arxiv_id = entry.find(f"{ATOM_NS}id").text.rsplit("/", 1)[-1]
        if arxiv_id in seen:
            continue
        pdf_url = next(
            (
                link.get("href")
                for link in entry.findall(f"{ATOM_NS}link")
                if link.get("title") == "pdf"
            ),
            None,
        )
        if not pdf_url:
            continue
        title = entry.find(f"{ATOM_NS}title").text.strip().replace("\n", " ")
        seen.add(arxiv_id)
        papers.append({"arxiv_id": arxiv_id, "title": title, "pdf_url": pdf_url})
    return papers


def golden_set_papers() -> list[dict]:
    """The exact paper versions the golden set was written against.

    discover_papers() asks arXiv for today's best matches, which drift as
    new papers appear, so a corpus seeded months later no longer contains
    the papers the golden set's expected ids point at. Pinning them by
    version reproduces the corpus its numbers came from."""
    ids = sorted(
        {
            arxiv_id
            for line in GOLDEN_SET.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for arxiv_id in json.loads(line).get("expected_arxiv_ids", [])
        }
    )
    resp = httpx.get(
        ARXIV_API,
        params={"id_list": ",".join(ids), "max_results": len(ids)},
        timeout=60.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    papers = _papers_in(ET.fromstring(resp.text), set())
    missing = set(ids) - {p["arxiv_id"] for p in papers}
    if missing:
        print(f"[warn] arXiv returned no entry for {sorted(missing)}")
    return papers


def download_pdf(pdf_url: str, dest: Path) -> None:
    with httpx.stream("GET", pdf_url, timeout=60.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)


def ingest_pdf(client: httpx.Client, path: Path, title: str, arxiv_id: str) -> str:
    with path.open("rb") as f:
        resp = client.post(
            "/ingest",
            files={"file": (path.name, f, "application/pdf")},
            data={"title": title, "external_id": arxiv_id},
            timeout=60.0,
        )
    resp.raise_for_status()
    return resp.json()["document_id"]


def wait_for_ready(client: httpx.Client, document_id: str, timeout_s: int = 600) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/documents/{document_id}", timeout=30.0)
        resp.raise_for_status()
        status = resp.json()["status"]
        if status in ("ready", "failed"):
            return status
        time.sleep(3)
    return "timeout"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-golden-set",
        action="store_true",
        help="seed exactly the paper versions eval-datasets/v1 references (reproducible)",
    )
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    papers = golden_set_papers() if args.from_golden_set else discover_papers()
    print(f"{len(papers)} papers to ingest")

    downloaded: list[dict] = []
    for paper in papers:
        dest = DATA_DIR / f"{paper['arxiv_id']}.pdf"
        if not dest.exists():
            try:
                download_pdf(paper["pdf_url"], dest)
            except Exception as e:
                print(f"  [warn] download failed {paper['arxiv_id']}: {e}")
                continue
        paper["local_path"] = str(dest)
        downloaded.append(paper)
    print(f"Downloaded {len(downloaded)} PDFs to {DATA_DIR}")
    (DATA_DIR / "manifest.json").write_text(json.dumps(downloaded, indent=2))

    results = []
    with httpx.Client(base_url=API_BASE) as client:
        for paper in downloaded:
            try:
                document_id = ingest_pdf(
                    client, Path(paper["local_path"]), paper["title"], paper["arxiv_id"]
                )
            except Exception as e:
                print(f"  [warn] ingest request failed {paper['arxiv_id']}: {e}")
                continue
            status = wait_for_ready(client, document_id)
            print(f"  {paper['arxiv_id']}: {status} ({paper['title'][:60]})")
            results.append({**paper, "document_id": document_id, "status": status})

    ready = sum(1 for r in results if r["status"] == "ready")
    print(f"\nIngested {ready}/{len(results)} documents successfully.")
    (DATA_DIR / "ingest_results.json").write_text(json.dumps(results, indent=2))
    if ready == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
