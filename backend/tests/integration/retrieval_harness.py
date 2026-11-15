"""Measure how well search finds the right passage (Phase 6, AI-1).

The dataset (tests/evaluation/retrieval_dataset.json) is a fictional
company, Atlantico Logistica: 17 documents in Portuguese and English, two
of them confidential, and 60 questions with the passage that answers them.
Questions are grouped by what they test: shared words, meaning only
(paraphrases), the other language, exact codes, and permissions (the
asker must NOT see the answer).

The harness runs the real pipeline inside one database transaction that
is rolled back: sync through the connector contract, passages, vectors
with the configured embedder, then search as a member through row-level
security. Nothing is kept.

Variants compared (VARIANTS): words, meaning, hybrid with the weighted
fusion (default), hybrid with the first plain fusion (hybrid-rrf), and
hybrid reordered by the reranker (hybrid+rerank).

Metrics, per variant and per group:
- Recall@1 and Recall@5: the right passage is first / in the first five;
- MRR@10: the average of 1 / position of the right passage (0 if absent
  from the first ten); 1.0 means always first;
- leaks: confidential passages shown to someone who may not read them
  (must be 0);
- latency: average milliseconds per search.
"""

import json
import time
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select, text

from app.connectors.base import CONNECTORS, ChangeSet, SourceItem
from app.core.errors import InvalidInputError
from app.models.background_job import BackgroundJob
from app.services.document_permission_service import SourcePermission
from app.services.embedding_service import EMBED_JOB, embed_version
from app.services.embeddings import EmbeddingUnavailableError, embeddings_enabled
from app.services.object_storage import LocalObjectStorage
from app.services.search_service import search
from app.services.sync_service import sync_connection
from tests.integration.test_document_permissions import _as_runtime, _as_worker


DATASET_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "retrieval_dataset.json"
VARIANTS = {
    "keyword": {"mode": "keyword"},
    "semantic": {"mode": "semantic"},
    "hybrid": {"mode": "hybrid"},
    "hybrid-rrf": {"mode": "hybrid", "fusion": "rrf"},
    "hybrid+rerank": {"mode": "hybrid", "rerank": True},
}
# The reranker settings compared in AI-2b: candidates read, characters of
# each (0 = whole passage).
RERANK_VARIANTS = {
    f"rerank-{n}{'-short' if chars else ''}": {
        "mode": "hybrid",
        "rerank": True,
        "rerank_candidates": n,
        "rerank_max_chars": chars,
    }
    for n, chars in ((20, 0), (10, 0), (20, 600), (10, 600))
}
VARIANTS.update(RERANK_VARIANTS)
MODES = ("keyword", "semantic", "hybrid")
TOP_K = 10


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="ascii"))


def _plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def ingest(db, world, dataset: dict, storage_dir: Path) -> int:
    """Sync the dataset as the worker and compute its vectors."""
    documents = dataset["documents"]
    ana = f"ana@{world.domain}"

    class Connector:
        def list_changes(self, cursor):
            return ChangeSet(
                changed=tuple(
                    SourceItem(
                        key,
                        doc["title"],
                        mime_type="text/plain",
                        revision="1",
                        permissions=(
                            (SourcePermission("user", ana),)
                            if doc["restricted"]
                            else (SourcePermission("domain", world.domain),)
                        ),
                    )
                    for key, doc in documents.items()
                ),
                cursor="eval",
            )

        def fetch_text(self, item):
            return documents[item.external_id]["text"]

    previous = CONNECTORS.get("google_drive")
    CONNECTORS["google_drive"] = lambda context: Connector()
    try:
        _as_worker(db, world.organization)
        summary = sync_connection(
            db,
            connection_id=world.connection,
            storage=LocalObjectStorage(storage_dir),
        )
        db.flush()
    finally:
        if previous is None:
            CONNECTORS.pop("google_drive", None)
        else:
            CONNECTORS["google_drive"] = previous

    embedded = 0
    if embeddings_enabled():
        jobs = db.scalars(
            select(BackgroundJob).where(
                BackgroundJob.organization_id == world.organization,
                BackgroundJob.kind == EMBED_JOB,
            )
        ).all()
        try:
            for job in jobs:
                embedded += embed_version(
                    db, version_id=uuid.UUID(job.payload["version_id"])
                )
        except EmbeddingUnavailableError:
            embedded = 0
        db.flush()
    assert summary["new_version"] == len(documents), summary
    return embedded


def _passages(db, chunk_ids):
    if not chunk_ids:
        return {}
    rows = db.execute(
        text(
            "SELECT c.id, d.external_id, c.content FROM document_chunks AS c "
            "JOIN documents AS d ON d.id = c.document_id WHERE c.id = ANY(:ids)"
        ),
        {"ids": list(chunk_ids)},
    ).all()
    return {row[0]: (row[1], _plain(row[2])) for row in rows}


def evaluate(db, world, dataset: dict, modes=MODES) -> dict:
    """Ask every question as Rui (a member who cannot read the confidential
    documents) and score each search mode."""
    _as_runtime(db, world.rui)
    results = {}
    for mode in modes:
        options = VARIANTS[mode]
        per_group = defaultdict(lambda: {"n": 0, "r1": 0.0, "r5": 0.0, "mrr": 0.0})
        leaks, misses, times, available = 0, [], [], True
        for question in dataset["questions"]:
            started = time.perf_counter()
            try:
                result = search(
                    db,
                    organization_id=world.organization,
                    query=question["query"],
                    limit=TOP_K,
                    **options,
                )
            except InvalidInputError:
                available = False
                break
            times.append(time.perf_counter() - started)
            if result.mode != options["mode"] or result.reranked != options.get("rerank", False):
                available = False
                break
            passages = _passages(db, [hit.chunk_id for hit in result.hits])
            found = [passages.get(hit.chunk_id, ("", "")) for hit in result.hits]

            if question["category"] == "permission":
                if any(doc in question["expect_absent"] for doc, _ in found):
                    leaks += 1
                continue

            phrase = _plain(question["expect_phrase"])
            rank = next(
                (
                    position
                    for position, (doc, content) in enumerate(found, start=1)
                    if doc == question["expect_doc"] and phrase in content
                ),
                None,
            )
            for group in (question["category"], "all"):
                stats = per_group[group]
                stats["n"] += 1
                stats["r1"] += 1.0 if rank == 1 else 0.0
                stats["r5"] += 1.0 if rank is not None and rank <= 5 else 0.0
                stats["mrr"] += 1.0 / rank if rank else 0.0
            if rank is None or rank > 5:
                misses.append(
                    {
                        "query": question["query"],
                        "rank": rank,
                        "first": [hit.title for hit in result.hits[:3]],
                    }
                )

        if not available:
            results[mode] = {"available": False}
            continue
        results[mode] = {
            "available": True,
            "leaks": leaks,
            "latency_ms": round(1000 * sum(times) / len(times), 1),
            "p95_ms": round(1000 * sorted(times)[int(0.95 * (len(times) - 1))], 1),
            "groups": {
                group: {
                    "n": s["n"],
                    "recall_at_1": round(s["r1"] / s["n"], 3),
                    "recall_at_5": round(s["r5"] / s["n"], 3),
                    "mrr_at_10": round(s["mrr"] / s["n"], 3),
                }
                for group, s in sorted(per_group.items())
            },
            "misses": misses,
        }
    return results


def format_report(results: dict) -> str:
    groups = sorted(
        {g for r in results.values() if r.get("available") for g in r["groups"]},
        key=lambda g: (g != "all", g),
    )
    lines = ["Recall@5 (MRR@10) by question group; leaks must be 0", ""]
    header = f"{'group':<12}" + "".join(f"{mode:>16}" for mode in results)
    lines += [header, "-" * len(header)]
    for group in groups:
        row = f"{group:<12}"
        for mode, r in results.items():
            if not r.get("available"):
                row += f"{'unavailable':>16}"
                continue
            g = r["groups"].get(group)
            row += f"{g['recall_at_5']:>9.2f} ({g['mrr_at_10']:.2f})" if g else f"{'-':>16}"
        lines.append(row)
    lines.append("-" * len(header))
    lines.append(f"{'leaks':<12}" + "".join(
        f"{(r['leaks'] if r.get('available') else '-'):>16}" for r in results.values()))
    lines.append(f"{'ms/search':<12}" + "".join(
        f"{(r['latency_ms'] if r.get('available') else '-'):>16}" for r in results.values()))
    lines.append(f"{'p95 ms':<12}" + "".join(
        f"{(r['p95_ms'] if r.get('available') else '-'):>16}" for r in results.values()))
    return "\n".join(lines)
