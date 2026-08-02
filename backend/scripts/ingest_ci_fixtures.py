"""Ingests the CI fixture corpus (scripts/generate_ci_fixtures.py) against a
running API instance and waits for every document to reach `ready`. Used by
.github/workflows/evals.yml's fast per-PR retrieval smoke test.
"""

import sys
import time
from pathlib import Path

import httpx

API_BASE = "http://localhost:8000/api"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ci_corpus"


def wait_for_ready(client: httpx.Client, document_id: str, timeout_s: int = 60) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = client.get(f"/documents/{document_id}", timeout=10.0)
        resp.raise_for_status()
        status = resp.json()["status"]
        if status in ("ready", "failed"):
            return status
        time.sleep(1)
    return "timeout"


def main() -> None:
    pdf_paths = sorted(FIXTURE_DIR.glob("*.pdf"))
    if not pdf_paths:
        print("No fixture PDFs found - run scripts/generate_ci_fixtures.py first", file=sys.stderr)
        sys.exit(1)

    failures = []
    with httpx.Client(base_url=API_BASE) as client:
        for path in pdf_paths:
            external_id = path.stem
            with path.open("rb") as f:
                resp = client.post(
                    "/ingest",
                    files={"file": (path.name, f, "application/pdf")},
                    data={"title": external_id, "external_id": external_id},
                    timeout=30.0,
                )
            resp.raise_for_status()
            document_id = resp.json()["document_id"]
            status = wait_for_ready(client, document_id)
            print(f"{external_id}: {status}")
            if status != "ready":
                failures.append(external_id)

    if failures:
        print(f"Failed to ingest: {failures}", file=sys.stderr)
        sys.exit(1)
    print(f"Ingested {len(pdf_paths)}/{len(pdf_paths)} CI fixture documents.")


if __name__ == "__main__":
    main()
