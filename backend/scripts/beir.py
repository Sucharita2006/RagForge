"""Public BEIR collections, scored by the project's own evaluation runner.

The golden set in eval-datasets/v1 was written and judged by this project's
own 4B model and already scores hit_rate 0.988, so it cannot show a
retrieval change. Two BEIR collections, SciDocs (scientific papers) and
ArguAna (counter-arguments), have 1,000+ judged test questions each and
published baselines.

Each collection lives in its own database, ragforge_beir_<name>, so public
data never mixes with the demo corpus; the script refuses any other.

    URL=postgresql+asyncpg://ragforge:ragforge@postgres:5432/ragforge_beir_scidocs
    docker compose run --rm -e DATABASE_URL=$URL api python -m scripts.beir load scidocs
    docker compose run --rm -e DATABASE_URL=$URL api python -m scripts.beir run scidocs "bm25"
    docker compose run --rm -e DATABASE_URL=$URL api python -m scripts.beir compare scidocs A B

`load` downloads the collection from the BEIR distribution (cached in
eval-datasets/downloads/), creates and migrates the database, stores one
document and one embedded chunk per BEIR document (external_id = BEIR id),
and writes the test questions with graded judgments as the golden set
eval-datasets/beir-<name>/full.jsonl.

`run` is a retrieval-only run of app.evals.runner.execute_eval_run, the code
behind POST /api/eval/run, so its rows show on the Golden set page when the
API points at the same database. `compare` stores an A/B comparison the same
way POST /api/experiments does. `run golden` and `compare golden` do both for
the project's own golden set on the main database, so a retrieval change is
checked on its real use case too.

`analyze` replays stored candidate pools under other ordering policies, and
`probe` scores dense retrieval alone with and without pseudo-relevance
feedback; both report a fixed 30% dev split (for choosing) and the 70% rest.
"""

import argparse
import asyncio
import csv
import hashlib
import io
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.db.session import async_session_maker
from app.evals.experiments import compare_runs, numeric_metrics_by_question
from app.evals.retrieval_metrics import graded_ndcg_at_k
from app.evals.runner import execute_eval_run
from app.ingestion.hashing import content_hash
from app.models.chunks import Chunk
from app.models.documents import Document
from app.models.evals import EvalResult, EvalRun
from app.models.spans import Experiment
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.ollama import OllamaProvider
from app.retrieval.dense import dense_search, embedding_of, feedback_query

settings = get_settings()

COLLECTIONS = ("scidocs", "arguana")
# "golden" is the project's own golden set on its main database, so a
# retrieval change is A/B-tested on its real use case with the same commands.
GOLDEN = "golden"
SOURCE = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/{name}.zip"
BACKEND = Path(__file__).resolve().parent.parent
# eval-datasets/ is backend/'s sibling in the repo and /app/eval-datasets in
# the container; the one holding the project's own golden set is the real one.
DATA = next(
    p for p in (BACKEND / "eval-datasets", BACKEND.parent / "eval-datasets") if (p / "v1").is_dir()
)
BATCH = 256


def database_for(name: str) -> str:
    return "ragforge" if name == GOLDEN else f"ragforge_beir_{name}"


def dataset_for(name: str) -> Path:
    return DATA / ("v1" if name == GOLDEN else f"beir-{name}") / "full.jsonl"


def require_database(name: str) -> None:
    url = make_url(settings.DATABASE_URL)
    if url.database != database_for(name):
        target = url.set(database=database_for(name)).render_as_string(hide_password=False)
        raise SystemExit(
            f"DATABASE_URL points at {url.database!r}. Run with -e DATABASE_URL={target}"
        )


# --- Data ---


def read_collection(name: str) -> tuple[dict[str, dict], dict[str, str], dict[str, dict[str, int]]]:
    """corpus, test queries and test judgments, read straight out of the
    cached zip (nothing is extracted to disk)."""
    archive = DATA / "downloads" / f"{name}.zip"
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {SOURCE.format(name=name)}", flush=True)
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(SOURCE.format(name=name), timeout=120) as response:
            with partial.open("wb") as out:
                shutil.copyfileobj(response, out)
        partial.rename(archive)

    with zipfile.ZipFile(archive) as zf:

        def lines(member: str) -> list[str]:
            return (
                io.TextIOWrapper(zf.open(f"{name}/{member}"), encoding="utf-8").read().splitlines()
            )

        corpus = {d["_id"]: d for d in map(json.loads, lines("corpus.jsonl"))}
        queries = {q["_id"]: q["text"] for q in map(json.loads, lines("queries.jsonl"))}
        judgments: dict[str, dict[str, int]] = {}
        for row in lines("qrels/test.tsv")[1:]:  # header: query-id, corpus-id, score
            query_id, doc_id, grade = row.split("\t")
            judgments.setdefault(query_id, {})[doc_id] = int(grade)
    return corpus, queries, judgments


def golden_items(queries: dict[str, str], judgments: dict[str, dict[str, int]]) -> list[dict]:
    """Test questions with at least one relevant document, in the project's
    golden-set format."""
    items = []
    for query_id in sorted(judgments):
        relevance = {doc: grade for doc, grade in judgments[query_id].items() if grade > 0}
        if relevance and query_id in queries:
            items.append(
                {
                    "id": query_id,
                    "type": "beir",
                    "question": queries[query_id],
                    "expected_arxiv_ids": sorted(relevance),
                    "relevance": relevance,
                }
            )
    return items


# --- Database ---


async def create_and_migrate(name: str) -> None:
    url = make_url(settings.DATABASE_URL)
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_for(name)}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{database_for(name)}"'))
    await admin.dispose()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)


async def store_corpus(name: str, corpus: dict[str, dict]) -> None:
    embedder = get_embedding_provider()
    async with async_session_maker() as db:
        stored = await db.scalar(select(func.count(Document.id)))
        if stored == len(corpus):
            print(f"{stored} documents already stored", flush=True)
            return
        if stored:
            raise SystemExit(
                f"{stored} of {len(corpus)} documents stored; drop the database and reload"
            )

        rows = list(corpus.values())
        for start in range(0, len(rows), BATCH):
            batch = rows[start : start + BATCH]
            documents = [
                Document(
                    filename=f"beir-{name}/{row['_id']}",
                    title=row.get("title") or None,
                    external_id=row["_id"],
                    mime="text/plain",
                    parser="beir",
                    status="ready",
                )
                for row in batch
            ]
            db.add_all(documents)
            await db.flush()
            bodies = [f"{row.get('title') or ''}\n{row['text']}".strip() for row in batch]
            vectors = await asyncio.to_thread(embedder.embed_documents, bodies)
            db.add_all(
                Chunk(
                    document_id=document.id,
                    content=body,
                    token_count=embedder.count_tokens(body),
                    content_hash=content_hash(body),
                    embedding=vector,
                    embedding_model=embedder.model_name,
                )
                for document, body, vector in zip(documents, bodies, vectors, strict=True)
            )
            await db.commit()
            print(f"stored {min(start + BATCH, len(rows))}/{len(rows)}", flush=True)


# --- Commands ---


async def load(name: str) -> None:
    corpus, queries, judgments = read_collection(name)
    await create_and_migrate(name)
    await store_corpus(name, corpus)
    items = golden_items(queries, judgments)
    path = DATA / f"beir-{name}" / "full.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
    print(f"{len(corpus)} documents, {len(items)} test questions -> {path}")


async def run(name: str, run_name: str, note: str) -> None:
    async with async_session_maker() as db:
        eval_run = EvalRun(
            name=run_name,
            dataset_version="v1" if name == GOLDEN else f"beir-{name}",
            config={
                "full_pipeline": False,
                "benchmark": "golden set v1" if name == GOLDEN else f"BEIR {name}, test split",
                "note": note,
                "rerank_candidates": settings.RERANK_CANDIDATES,
                "reranker": settings.RERANKER_MODEL,
            },
            status="running",
        )
        db.add(eval_run)
        await db.commit()
        await db.refresh(eval_run)
        await execute_eval_run(
            db,
            eval_run.id,
            dataset_for(name),
            get_embedding_provider(),
            OllamaProvider(),  # never called: retrieval-only
            full_pipeline_ids=set(),
        )
        await db.refresh(eval_run)
        print(f"{run_name}: {eval_run.status} {eval_run.error or ''}")
        for metric in ("ndcg@10_graded", "recall@10", "reciprocal_rank", "latency_ms"):
            m = (eval_run.metrics or {}).get(metric)
            if m:
                print(
                    f"  {metric}: {m['mean']:.4f} "
                    f"[{m['ci_low']:.4f}, {m['ci_high']:.4f}] n={m['n']}"
                )


async def run_by_name(db: AsyncSession, run_name: str) -> EvalRun:
    found = (
        (
            await db.execute(
                select(EvalRun).where(EvalRun.name == run_name).order_by(EvalRun.started_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if found is None:
        raise SystemExit(f"no run named {run_name!r}")
    return found


async def results_of(db: AsyncSession, run: EvalRun) -> list[EvalResult]:
    rows = await db.execute(select(EvalResult).where(EvalResult.run_id == run.id))
    return list(rows.scalars().all())


async def compare(name_a: str, name_b: str) -> None:
    async with async_session_maker() as db:
        run_a, run_b = await run_by_name(db, name_a), await run_by_name(db, name_b)
        deltas = compare_runs(
            numeric_metrics_by_question(await results_of(db, run_a)),
            numeric_metrics_by_question(await results_of(db, run_b)),
        )
        db.add(
            Experiment(
                name=f"{name_a} vs {name_b}",
                config_a=run_a.config or {},
                config_b=run_b.config or {},
                run_a_id=run_a.id,
                run_b_id=run_b.id,
                deltas=deltas,
            )
        )
        await db.commit()
    print("| metric | A | B | B - A | 95% interval | significant |\n|---|---|---|---|---|---|")
    for metric, d in deltas.items():
        print(
            f"| {metric} | {d['mean_a']:.4f} | {d['mean_b']:.4f} | {d['delta']:+.4f} "
            f"| [{d['ci_low']:+.4f}, {d['ci_high']:+.4f}] | {'yes' if d['significant'] else 'no'} |"
        )


def split_of(question_id: str) -> str:
    """A stable 30/70 dev/test split by question id, independent of file
    order: policies are chosen on dev and reported on test."""
    digest = hashlib.sha256(question_id.encode()).digest()
    return "dev" if int.from_bytes(digest[:8], "big") % 10 < 3 else "test"


# A pool row as the runner stores it: id, dense rank, sparse rank, RRF, rerank.
Row = list


def orderings(pool: list[Row], thresholds: list[float]) -> dict[str, list[str]]:
    """Top-10 document ids under each ordering policy.

    `lift(base, t)`: candidates the cross-encoder scores at or above t go
    first, in its order; everything else keeps the base order.
    `gate(base, t)`: the whole reranked order when the best rerank score
    reaches t, otherwise the base order."""
    by_rerank = sorted(pool, key=lambda r: -math.inf if r[4] is None else r[4], reverse=True)
    best = by_rerank[0][4] if by_rerank and by_rerank[0][4] is not None else -math.inf
    bases = {
        "dense": sorted((r for r in pool if r[1] is not None), key=lambda r: r[1]),
        "fused": sorted(pool, key=lambda r: r[3], reverse=True),
    }
    # "returned" is the order the pipeline itself produced (pools are stored in it)
    out: dict[str, list[Row]] = {"returned": pool, "reranked": by_rerank, **bases}
    for name, base in bases.items():
        for t in thresholds:
            lifted = [r for r in by_rerank if r[4] is not None and r[4] >= t]
            ids = {r[0] for r in lifted}
            out[f"lift({name},{t:+.1f})"] = lifted + [r for r in base if r[0] not in ids]
            out[f"gate({name},{t:+.1f})"] = by_rerank if best >= t else base
    return {policy: [r[0] for r in rows[:10]] for policy, rows in out.items()}


async def analyze(name: str, run_name: str) -> None:
    # The golden set has no graded judgments: its expected papers count as relevant.
    items = {
        item["id"]: item.get("relevance") or dict.fromkeys(item["expected_arxiv_ids"], 1)
        for item in map(json.loads, dataset_for(name).open(encoding="utf-8"))
        if item.get("relevance") or item.get("expected_arxiv_ids")
    }
    async with async_session_maker() as db:
        results = await results_of(db, await run_by_name(db, run_name))
    thresholds = [t / 2 for t in range(-8, 17)]  # -4.0 .. +8.0 in rerank logits
    scores: dict[str, dict[str, list[float]]] = {}
    for result in results:
        if result.question_id not in items:
            continue
        pool = result.retrieved.get("pool")
        if pool is None:
            raise SystemExit(f"{run_name!r} has no stored pools; re-run it with this runner")
        split = split_of(result.question_id)
        for policy, top in orderings(pool, thresholds).items():
            ndcg = graded_ndcg_at_k(top, items[result.question_id], 10)
            scores.setdefault(policy, {"dev": [], "test": []})[split].append(ndcg)

    rows = sorted(
        ((p, statistics.fmean(s["dev"]), statistics.fmean(s["test"])) for p, s in scores.items()),
        key=lambda r: r[1],
        reverse=True,
    )
    slug = re.sub(r"[^a-z0-9]+", "-", run_name.lower()).strip("-")
    out = DATA / "benchmarks" / f"{name}-{slug}-policies.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:  # policy names contain commas
        writer = csv.writer(f)
        writer.writerow(["policy", "dev", "test"])
        writer.writerows((p, f"{d:.4f}", f"{t:.4f}") for p, d, t in rows)
    n_dev, n_test = len(scores["reranked"]["dev"]), len(scores["reranked"]["test"])
    print(f"{name} / {run_name}: {n_dev} dev and {n_test} test questions -> {out}")
    print("| policy | dev nDCG@10 | test nDCG@10 |\n|---|---|---|")
    shown = rows[:12] + [r for r in rows[12:] if r[0] in ("returned", "reranked", "dense", "fused")]
    for p, d, t in shown:
        print(f"| {p} | {d:.4f} | {t:.4f} |")


async def probe(name: str) -> None:
    """Dense retrieval alone, with and without pseudo-relevance feedback, over
    a grid of (feedback documents, weight). Only the vector index is used, so
    a whole collection takes minutes; the result picks settings to try in a
    full run, chosen on dev."""
    items = [json.loads(line) for line in dataset_for(name).open(encoding="utf-8") if line.strip()]
    grid = [(0, 0.0)] + [(k, w) for k in (1, 3, 5, 10) for w in (0.25, 0.5, 1.0, 2.0)]
    scores: dict[tuple[int, float], dict[str, list[float]]] = {
        g: {"dev": [], "test": []} for g in grid
    }
    embedder = get_embedding_provider()
    async with async_session_maker() as db:
        rows = await db.execute(select(Chunk.id, Document.external_id).join(Document))
        external_id = {chunk_id: doc_id for chunk_id, doc_id in rows.all()}

        async def top(query: list[float], question_id: str, k: int) -> list[Chunk]:
            hits = await dense_search(db, query, k + 1, settings.HNSW_EF_SEARCH)
            return [c for c, _ in hits if external_id[c.id] != question_id][:k]

        for n, item in enumerate(items, 1):
            query = embedder.embed_query(item["question"])
            first = await top(query, item["id"], 10)
            for k, weight in grid:
                ranked = first
                if k:
                    feedback = [embedding_of(c) for c in first[:k]]
                    ranked = await top(feedback_query(query, feedback, weight), item["id"], 10)
                ndcg = graded_ndcg_at_k([external_id[c.id] for c in ranked], item["relevance"], 10)
                scores[(k, weight)][split_of(item["id"])].append(ndcg)
            await db.rollback()  # end the read transaction; SET LOCAL is per transaction
            if n % 200 == 0:
                print(f"probed {n}/{len(items)}", flush=True)

    rows_out = sorted(
        (
            (k, w, statistics.fmean(s["dev"]), statistics.fmean(s["test"]))
            for (k, w), s in scores.items()
        ),
        key=lambda r: r[2],
        reverse=True,
    )
    out = DATA / "benchmarks" / f"{name}-feedback.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "feedback_docs,weight,dev,test\n"
        + "".join(f"{k},{w},{d:.4f},{t:.4f}\n" for k, w, d, t in rows_out),
        encoding="utf-8",
    )
    print(f"{name}: dense alone and with feedback -> {out}")
    print("| feedback docs | weight | dev nDCG@10 | test nDCG@10 |\n|---|---|---|---|")
    for k, w, d, t in rows_out:
        print(f"| {k} | {w} | {d:.4f} | {t:.4f} |")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("load", "run", "compare", "analyze", "probe"):
        p = sub.add_parser(command)
        targets = (
            (*COLLECTIONS, GOLDEN) if command in ("run", "compare", "analyze") else COLLECTIONS
        )
        p.add_argument("collection", choices=targets)
    sub.choices["run"].add_argument("name", help="run name, shown on the Golden set page")
    sub.choices["run"].add_argument("--note", default="", help="what differs in this run")
    sub.choices["compare"].add_argument("run_a")
    sub.choices["compare"].add_argument("run_b")
    sub.choices["analyze"].add_argument("run", help="a run whose results store candidate pools")
    args = parser.parse_args()

    require_database(args.collection)
    if args.command == "load":
        asyncio.run(load(args.collection))
    elif args.command == "run":
        asyncio.run(run(args.collection, args.name, args.note))
    elif args.command == "compare":
        asyncio.run(compare(args.run_a, args.run_b))
    elif args.command == "analyze":
        asyncio.run(analyze(args.collection, args.run))
    else:
        asyncio.run(probe(args.collection))


if __name__ == "__main__":
    main()
