#!/usr/bin/env python3
"""Run one frozen five-way full-corpus BM25/Dense/RRF ablation."""

from __future__ import annotations

import os

# Keep local latency comparisons on one numerical thread in every child process.
for _thread_variable in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_variable] = "1"

import argparse
import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
import gc
import hashlib
import heapq
import json
import logging
import math
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse

import bm25s
import numpy as np
import Stemmer

from deeptutor.services.rag.pipelines.llamaindex.bm25_tokenization import (
    CJK_BIGRAM_TOKEN_PATTERN,
    cjk_bigram_tokenizer_manifest,
    prepare_cjk_bigram_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVISION = "ff68e85c3a75b54db4eb603cf7dd4dd54ea1cdb3"
PUBLIC_EVAL_ROOT = PROJECT_ROOT / "data" / "evaluations" / "rag_public_holdout_final"
SOURCE_ROOT = PUBLIC_EVAL_ROOT / "source" / REVISION
SOURCE_FILES = {
    "corpus": SOURCE_ROOT / "corpus-dev.parquet",
    "qrels": SOURCE_ROOT / "qrels-dev.parquet",
    "queries": SOURCE_ROOT / "queries-dev.parquet",
    "dataset_card": SOURCE_ROOT / "README.md",
}
PRIOR_RUN_ROOT = PUBLIC_EVAL_ROOT / "runs" / "mmarco_zh_dev_200_seed20260911"
PRIOR_SNAPSHOT = PRIOR_RUN_ROOT / "selected_snapshot.json"
PRIOR_MANIFEST = PRIOR_RUN_ROOT / "manifest.json"
PRIOR_VECTOR_CACHE = PRIOR_RUN_ROOT / "embeddings.jsonl"
FULL_BM25_ROOT = (
    PROJECT_ROOT
    / "data"
    / "evaluations"
    / "rag_full_corpus_bm25_validation"
    / "runs"
    / "mmarco_zh_dev_200_full_106813"
)
FULL_BM25_MANIFEST = FULL_BM25_ROOT / "manifest.json"
EVAL_ROOT = PROJECT_ROOT / "data" / "evaluations" / "rag_full_corpus_hybrid_ablation"
RUN_ID = "mmarco_zh_dev_200_full_106813_top50"
RUN_ROOT = EVAL_ROOT / "runs" / RUN_ID
SCRIPT_PATH = Path(__file__).resolve()

QUERY_COUNT = 200
CORPUS_COUNT = 106_813
LOGICAL_ITEM_COUNT = QUERY_COUNT + CORPUS_COUNT
EXPECTED_UNIQUE_TEXTS = 106_986
EXPECTED_REUSED_UNIQUE = 3_200
AUTHORIZED_MISSING_UNIQUE = 103_786
AUTHORIZED_MISSING_CHARACTERS = 11_869_974
EMBEDDING_DIMENSION = 1_024
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_BATCH_SIZE = 10
EMBEDDING_CONCURRENCY = 4
TOP_K = 50
RRF_K = 60
WARMUP_QUERIES = 3
BOOTSTRAP_SAMPLES = 5_000
BOOTSTRAP_SEED = 20260911
SCHEMES = (
    "bm25_legacy",
    "bm25_cjk_bigram_v1",
    "dense",
    "rrf_dense_legacy",
    "rrf_dense_cjk_bigram_v1",
)

LOGICAL_ITEMS_PATH = RUN_ROOT / "logical_items.jsonl"
UNIQUE_TEXTS_PATH = RUN_ROOT / "unique_texts.jsonl"
MISSING_TEXTS_PATH = RUN_ROOT / "missing_texts.jsonl"
MANIFEST_PATH = RUN_ROOT / "manifest.json"
MANIFEST_CHECKSUM_PATH = RUN_ROOT / "manifest.sha256"
PASSAGE_VECTORS_PATH = RUN_ROOT / "passage_vectors.f32"
QUERY_VECTORS_PATH = RUN_ROOT / "query_vectors.f32"
PASSAGE_STATUS_PATH = RUN_ROOT / "passage_status.u8"
QUERY_STATUS_PATH = RUN_ROOT / "query_status.u8"
VECTOR_STORE_META_PATH = RUN_ROOT / "vector_store_meta.json"
EMBEDDING_BATCH_LOG_PATH = RUN_ROOT / "embedding_batches.jsonl"
EMBEDDING_AUDIT_PATH = RUN_ROOT / "embedding_audit.json"
NORMALIZATION_PATH = RUN_ROOT / "normalization.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id_key(value: str) -> tuple[int, int | str, str]:
    text = str(value)
    return (0, int(text), text) if text.isdecimal() else (1, text, text)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)


def write_frozen_bytes(path: Path, payload: bytes) -> str:
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"refusing to replace frozen artifact: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return sha256_bytes(payload)


def write_frozen_json(path: Path, value: Any) -> str:
    return write_frozen_bytes(path, canonical_json_bytes(value))


def verify_frozen_file(path: Path, checksum_path: Path) -> str:
    expected = checksum_path.read_text(encoding="utf-8").strip().split()[0]
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"frozen checksum mismatch: {path}")
    return actual


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(dict(row)) for row in rows)


def append_jsonl_durable(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                dict(row),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def load_parquet_rows(
    path: Path, *, columns: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    selected = list(columns) if columns is not None else None
    return pq.read_table(path, columns=selected).to_pylist()


def stable_top_scores(
    passage_ids: Sequence[str], scores: Sequence[float], *, limit: int
) -> list[tuple[str, float]]:
    if len(passage_ids) != len(scores):
        raise ValueError("passage_ids and scores must have equal lengths")
    return heapq.nsmallest(
        max(0, int(limit)),
        ((str(passage_id), float(score)) for passage_id, score in zip(passage_ids, scores)),
        key=lambda item: (-item[1], stable_id_key(item[0])),
    )


def stable_top_positive(
    passage_ids: Sequence[str], scores: Sequence[float], *, limit: int
) -> list[tuple[str, float]]:
    if len(passage_ids) != len(scores):
        raise ValueError("passage_ids and scores must have equal lengths")
    return heapq.nsmallest(
        max(0, int(limit)),
        (
            (str(passage_id), float(score))
            for passage_id, score in zip(passage_ids, scores)
            if float(score) > 0.0
        ),
        key=lambda item: (-item[1], stable_id_key(item[0])),
    )


def rrf_rank(
    dense: Sequence[tuple[str, float]],
    bm25: Sequence[tuple[str, float]],
    *,
    limit: int,
    rrf_k: int,
) -> tuple[list[tuple[str, float]], dict[str, Any]]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in (dense, bm25):
        for rank, (passage_id, _) in enumerate(ranking, 1):
            scores[str(passage_id)] += 1.0 / (rrf_k + rank)
    ordered = heapq.nsmallest(
        max(0, int(limit)),
        scores.items(),
        key=lambda item: (-item[1], stable_id_key(item[0])),
    )
    union_ids = sorted(scores, key=stable_id_key)
    return ordered, {"union_size": len(union_ids), "union_passage_ids": union_ids}


def score_ranking(
    ranking: Sequence[str], relevant_passage_ids: Iterable[str]
) -> dict[str, float | int | None]:
    relevant = {str(value) for value in relevant_passage_ids}
    if not relevant:
        raise ValueError("at least one relevant passage is required")
    first_rank = next(
        (
            rank
            for rank, passage_id in enumerate(ranking[:10], 1)
            if passage_id in relevant
        ),
        None,
    )
    found_at_5 = relevant.intersection(ranking[:5])
    found_at_20 = relevant.intersection(ranking[:20])
    found_at_50 = relevant.intersection(ranking[:50])
    return {
        "reciprocal_rank_at_10": (
            0.0 if first_rank is None else 1.0 / first_rank
        ),
        "hit_at_5": float(bool(found_at_5)),
        "hit_at_20": float(bool(found_at_20)),
        "recall_at_20": len(found_at_20) / len(relevant),
        "hit_at_50": float(bool(found_at_50)),
        "recall_at_50": len(found_at_50) / len(relevant),
        "first_relevant_rank": first_rank,
    }


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def safe_embedding_config(config: Any) -> dict[str, Any]:
    parsed = urlparse(config.effective_url or config.base_url or "")
    return {
        "binding": config.binding,
        "provider_name": config.provider_name,
        "provider_mode": config.provider_mode,
        "model": config.model,
        "configured_dimension": config.dim,
        "send_dimensions": config.send_dimensions,
        "endpoint_host": parsed.netloc,
        "endpoint_path": parsed.path,
        "request_timeout_seconds": config.request_timeout,
        "configured_batch_size": config.batch_size,
        "api_key_present": bool(config.api_key),
    }


def repo_state() -> dict[str, Any]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
        )
    except Exception:
        head, dirty = "unknown", None
    return {
        "git_head": head,
        "git_worktree_dirty": dirty,
        "script_sha256": sha256_file(SCRIPT_PATH),
    }


def runtime_versions() -> dict[str, str]:
    from importlib import metadata

    result = {
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    for name in ("bm25s", "PyStemmer", "pyarrow"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = "unknown"
    return result


def load_inputs() -> tuple[list[dict[str, Any]], list[str], list[str]]:
    snapshot = load_json(PRIOR_SNAPSHOT)
    queries = list(snapshot.get("queries") or [])
    if len(queries) != QUERY_COUNT or len({str(row["query_id"]) for row in queries}) != QUERY_COUNT:
        raise RuntimeError("prior snapshot query set changed")
    rows = load_parquet_rows(SOURCE_FILES["corpus"], columns=("_id", "text"))
    corpus = [
        (str(row["_id"]), "" if row["text"] is None else str(row["text"]))
        for row in rows
    ]
    if len(corpus) != CORPUS_COUNT or len({row[0] for row in corpus}) != CORPUS_COUNT:
        raise RuntimeError("pinned corpus count or ID uniqueness changed")
    corpus.sort(key=lambda item: stable_id_key(item[0]))
    passage_ids = [row[0] for row in corpus]
    passage_texts = [row[1] for row in corpus]
    if any(not text.strip() for text in passage_texts):
        raise RuntimeError("pinned corpus unexpectedly contains empty passage text")
    return queries, passage_ids, passage_texts


def build_text_inventory(
    queries: Sequence[Mapping[str, Any]],
    passage_ids: Sequence[str],
    passage_texts: Sequence[str],
) -> dict[str, Any]:
    logical_rows: list[dict[str, Any]] = []
    unique: dict[str, dict[str, Any]] = {}
    for row_index, query in enumerate(queries):
        text = str(query["text"])
        text_hash = sha256_text(text)
        logical_rows.append(
            {
                "kind": "query",
                "item_id": str(query["query_id"]),
                "row": row_index,
                "text_sha256": text_hash,
                "characters": len(text),
                "utf8_bytes": len(text.encode("utf-8")),
            }
        )
        unique.setdefault(
            text_hash,
            {
                "text_sha256": text_hash,
                "representative_kind": "query",
                "representative_id": str(query["query_id"]),
                "characters": len(text),
                "utf8_bytes": len(text.encode("utf-8")),
                "logical_references": 0,
            },
        )["logical_references"] += 1
    for row_index, (passage_id, text) in enumerate(zip(passage_ids, passage_texts)):
        text_hash = sha256_text(text)
        logical_rows.append(
            {
                "kind": "passage",
                "item_id": passage_id,
                "row": row_index,
                "text_sha256": text_hash,
                "characters": len(text),
                "utf8_bytes": len(text.encode("utf-8")),
            }
        )
        unique.setdefault(
            text_hash,
            {
                "text_sha256": text_hash,
                "representative_kind": "passage",
                "representative_id": passage_id,
                "characters": len(text),
                "utf8_bytes": len(text.encode("utf-8")),
                "logical_references": 0,
            },
        )["logical_references"] += 1
    return {
        "logical_rows": logical_rows,
        "unique_rows": [unique[key] for key in sorted(unique)],
        "unique": unique,
    }


def audit_prior_cache(required_hashes: set[str]) -> dict[str, Any]:
    seen: set[str] = set()
    models: set[str] = set()
    dimensions: set[int] = set()
    invalid = 0
    with PRIOR_VECTOR_CACHE.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = str(row["text_sha256"])
            vector = row["embedding"]
            dimension = int(row["dimension"])
            if key in seen or len(vector) != dimension or not all(
                math.isfinite(float(value)) for value in vector
            ):
                invalid += 1
            seen.add(key)
            models.add(str(row["model"]))
            dimensions.add(dimension)
    reusable = seen.intersection(required_hashes)
    return {
        "path": str(PRIOR_VECTOR_CACHE.relative_to(PROJECT_ROOT)),
        "sha256": sha256_file(PRIOR_VECTOR_CACHE),
        "cache_rows": len(seen),
        "required_hashes_reused": len(reusable),
        "irrelevant_cached_hashes": len(seen - required_hashes),
        "models": sorted(models),
        "dimensions": sorted(dimensions),
        "invalid_rows": invalid,
        "reusable_hashes": reusable,
    }


def validate_original_qrels(
    queries: Sequence[Mapping[str, Any]], passage_ids: set[str]
) -> dict[str, Any]:
    qrel_rows = load_parquet_rows(
        SOURCE_FILES["qrels"], columns=("query-id", "corpus-id", "score")
    )
    source_qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for row in qrel_rows:
        score = int(row["score"])
        if score > 0:
            source_qrels[str(row["query-id"])][str(row["corpus-id"])] = score
    distribution: Counter[int] = Counter()
    for query in queries:
        query_id = str(query["query_id"])
        expected = {
            str(item["passage_id"]): int(item["score"])
            for item in query["positive_qrels"]
        }
        if expected != source_qrels.get(query_id):
            raise RuntimeError(f"qrels changed for {query_id}")
        if not set(expected) <= passage_ids:
            raise RuntimeError(f"qrel positive absent from full corpus: {query_id}")
        distribution[len(expected)] += 1
    return {
        "positive_qrels": sum(
            len(query["positive_qrels"]) for query in queries
        ),
        "distribution": {
            str(key): value for key, value in sorted(distribution.items())
        },
        "provenance": "pinned mteb/MMarcoRetrieval default config dev qrels, score > 0",
    }


def write_inventory_and_manifest() -> dict[str, Any]:
    from deeptutor.services.embedding import get_embedding_config

    required_paths = [
        *SOURCE_FILES.values(),
        PRIOR_SNAPSHOT,
        PRIOR_MANIFEST,
        PRIOR_VECTOR_CACHE,
        FULL_BM25_MANIFEST,
    ]
    missing_paths = [str(path) for path in required_paths if not path.is_file()]
    if missing_paths:
        raise FileNotFoundError(f"missing frozen prerequisites: {missing_paths}")
    if MANIFEST_PATH.exists():
        verify_frozen_file(MANIFEST_PATH, MANIFEST_CHECKSUM_PATH)
        manifest = load_json(MANIFEST_PATH)
        if manifest["code"]["script_sha256"] != sha256_file(SCRIPT_PATH):
            raise RuntimeError("runner changed after manifest freeze")
        return manifest

    queries, passage_ids, passage_texts = load_inputs()
    inventory = build_text_inventory(queries, passage_ids, passage_texts)
    unique_rows = inventory["unique_rows"]
    required_hashes = set(inventory["unique"])
    prior_cache = audit_prior_cache(required_hashes)
    if prior_cache["invalid_rows"] or prior_cache["models"] != [EMBEDDING_MODEL] or prior_cache["dimensions"] != [EMBEDDING_DIMENSION]:
        raise RuntimeError("prior vector cache model/dimension/content validation failed")
    reusable_hashes = prior_cache.pop("reusable_hashes")
    missing_rows = [row for row in unique_rows if row["text_sha256"] not in reusable_hashes]
    for index, row in enumerate(missing_rows):
        row["batch_index"] = index // EMBEDDING_BATCH_SIZE + 1
    missing_characters = sum(int(row["characters"]) for row in missing_rows)
    if (
        len(inventory["logical_rows"]) != LOGICAL_ITEM_COUNT
        or len(unique_rows) != EXPECTED_UNIQUE_TEXTS
        or prior_cache["required_hashes_reused"] != EXPECTED_REUSED_UNIQUE
        or len(missing_rows) != AUTHORIZED_MISSING_UNIQUE
        or missing_characters != AUTHORIZED_MISSING_CHARACTERS
    ):
        raise RuntimeError(
            "frozen unique/reuse/missing counts differ from the authorized boundary"
        )
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    logical_sha = write_frozen_bytes(
        LOGICAL_ITEMS_PATH, jsonl_bytes(inventory["logical_rows"])
    )
    unique_sha = write_frozen_bytes(UNIQUE_TEXTS_PATH, jsonl_bytes(unique_rows))
    missing_sha = write_frozen_bytes(MISSING_TEXTS_PATH, jsonl_bytes(missing_rows))
    embedding_config = get_embedding_config()
    validated_embedding_config = validate_runtime_embedding_config()
    if embedding_config.model != EMBEDDING_MODEL:
        raise RuntimeError(
            f"configured embedding model changed: {embedding_config.model!r}"
        )
    prior_public_manifest = load_json(PRIOR_MANIFEST)
    full_bm25_manifest = load_json(FULL_BM25_MANIFEST)
    frozen_utc = utc_now()
    manifest = {
        "schema_version": 1,
        "task": "RAG-FULL-CORPUS-HYBRID-ABLATION",
        "run_id": RUN_ID,
        "frozen_utc": frozen_utc,
        "experiment_role": "same-query full-corpus five-way ablation after observing prior small-pool and full-corpus BM25 results; no query/strategy tuning after this freeze",
        "source": {
            "dataset_id": "mteb/MMarcoRetrieval",
            "description": "MTEB-packaged mMARCO Chinese dev retrieval corpus, not the original multi-million-passage corpus",
            "revision": REVISION,
            "split": "dev",
            "files": {
                name: {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for name, path in SOURCE_FILES.items()
            },
            "passage_count": CORPUS_COUNT,
            "query_count": QUERY_COUNT,
            "qrels": validate_original_qrels(queries, set(passage_ids)),
        },
        "lineage": {
            "prior_snapshot_path": str(PRIOR_SNAPSHOT.relative_to(PROJECT_ROOT)),
            "prior_snapshot_sha256": sha256_file(PRIOR_SNAPSHOT),
            "prior_public_manifest_path": str(PRIOR_MANIFEST.relative_to(PROJECT_ROOT)),
            "prior_public_manifest_sha256": sha256_file(PRIOR_MANIFEST),
            "full_corpus_bm25_manifest_path": str(FULL_BM25_MANIFEST.relative_to(PROJECT_ROOT)),
            "full_corpus_bm25_manifest_sha256": sha256_file(FULL_BM25_MANIFEST),
            "query_ids_sha256": full_bm25_manifest["query_lineage"]["query_ids_sha256"],
            "queries_and_qrels_unchanged": True,
        },
        "input_inventory": {
            "logical_items": LOGICAL_ITEM_COUNT,
            "unique_texts": len(unique_rows),
            "duplicate_logical_items": LOGICAL_ITEM_COUNT - len(unique_rows),
            "logical_items_path": str(LOGICAL_ITEMS_PATH.relative_to(PROJECT_ROOT)),
            "logical_items_sha256": logical_sha,
            "unique_texts_path": str(UNIQUE_TEXTS_PATH.relative_to(PROJECT_ROOT)),
            "unique_texts_sha256": unique_sha,
            "missing_texts_path": str(MISSING_TEXTS_PATH.relative_to(PROJECT_ROOT)),
            "missing_texts_sha256": missing_sha,
            "missing_unique_texts": len(missing_rows),
            "missing_characters": missing_characters,
            "missing_utf8_bytes": sum(int(row["utf8_bytes"]) for row in missing_rows),
            "authorization_match": True,
        },
        "embedding": {
            "configuration": validated_embedding_config,
            "required_model": EMBEDDING_MODEL,
            "required_actual_dimension": EMBEDDING_DIMENSION,
            "prior_cache": prior_cache,
            "batch_size": EMBEDDING_BATCH_SIZE,
            "max_concurrency": EMBEDDING_CONCURRENCY,
            "input": "exact query or passage text only; no title, ID, metadata, chunking, or runner-side truncation",
            "storage": "float32 passage/query memmap plus durable status bytes; exact-text SHA-256 deduplication",
            "successful_cache_policy": "committed vectors with durable status are never resent",
            "secret_output": False,
        },
        "retrieval": {
            "schemes": list(SCHEMES),
            "top_k_per_branch_and_final": TOP_K,
            "top_k_change_from_prior": "20 -> 50, frozen before ranking solely to report Hit/Recall@20 and @50 plus branch-union coverage; not selected from results",
            "dense": "cosine similarity over one shared text-embedding-v4 1024-dimensional vector set",
            "bm25_legacy": {
                "library": "bm25s",
                "parameters": "bm25s.BM25() defaults",
                "token_pattern": r"(?u)\b\w\w+\b",
                "stopwords": "en",
                "stemmer": "english",
            },
            "bm25_cjk_bigram_v1": cjk_bigram_tokenizer_manifest(),
            "bm25_nonpositive_policy": "score <= 0 excluded",
            "tie_break": "descending score then stable numeric-or-lexical passage ID",
            "hybrid": "equal unweighted reciprocal rank fusion",
            "rrf_k": RRF_K,
            "candidate_union": "union of dense top50 and positive-score BM25 top50, at most 100 before overlap; reported separately from fused top50",
            "reranker": False,
            "metadata_filter": False,
            "query_rewrite": False,
            "parameter_tuning": False,
        },
        "metrics": {
            "unit": "passage",
            "per_scheme": [
                "MRR@10",
                "query Hit@5",
                "query Hit@20",
                "Recall@20",
                "query Hit@50",
                "Recall@50",
            ],
            "hybrid_candidate_union": [
                "query union hit",
                "macro union recall",
                "union size",
            ],
            "unjudged_policy": "treated as nonrelevant for metrics; qrels are not asserted exhaustive negatives",
            "bootstrap": {
                "samples": BOOTSTRAP_SAMPLES,
                "seed": BOOTSTRAP_SEED,
                "method": "paired query bootstrap percentile 95% CI for MRR@10 differences",
            },
        },
        "latency": {
            "warmup_queries": WARMUP_QUERIES,
            "summary": ["P50", "P95"],
            "threads": {name: os.environ[name] for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )},
            "hybrid_measurement": "sum of same-run sequential dense retrieval, BM25 retrieval, and measured RRF fusion per query",
            "excluded": "index build/load and query embedding",
            "online_query_embedding_latency_measured": False,
            "online_end_to_end_latency_measured": False,
        },
        "external_calls": {
            "authorized_embedding_missing_unique_texts": AUTHORIZED_MISSING_UNIQUE,
            "ocr": 0,
            "generation_llm": 0,
            "download": 0,
        },
        "runtime": runtime_versions(),
        "code": repo_state(),
        "prior_small_pool_metrics_reference": prior_public_manifest["run_id"],
    }
    manifest_sha = write_frozen_json(MANIFEST_PATH, manifest)
    MANIFEST_CHECKSUM_PATH.write_text(
        f"{manifest_sha}  manifest.json\n", encoding="utf-8"
    )
    return manifest


def load_and_verify_manifest() -> dict[str, Any]:
    verify_frozen_file(MANIFEST_PATH, MANIFEST_CHECKSUM_PATH)
    manifest = load_json(MANIFEST_PATH)
    if manifest["code"]["script_sha256"] != sha256_file(SCRIPT_PATH):
        raise RuntimeError("runner changed after manifest freeze")
    for name, info in manifest["source"]["files"].items():
        if sha256_file(PROJECT_ROOT / info["path"]) != info["sha256"]:
            raise RuntimeError(f"source hash changed: {name}")
    for path_key, hash_key in (
        ("logical_items_path", "logical_items_sha256"),
        ("unique_texts_path", "unique_texts_sha256"),
        ("missing_texts_path", "missing_texts_sha256"),
    ):
        if sha256_file(PROJECT_ROOT / manifest["input_inventory"][path_key]) != manifest["input_inventory"][hash_key]:
            raise RuntimeError(f"frozen inventory changed: {path_key}")
    return manifest


def build_runtime_text_maps() -> dict[str, Any]:
    queries, passage_ids, passage_texts = load_inputs()
    text_by_hash: dict[str, str] = {}
    locations: dict[str, dict[str, list[int]]] = {}
    query_hashes: list[str] = []
    passage_hashes: list[str] = []
    for row_index, query in enumerate(queries):
        text = str(query["text"])
        key = sha256_text(text)
        text_by_hash.setdefault(key, text)
        locations.setdefault(key, {"query": [], "passage": []})["query"].append(
            row_index
        )
        query_hashes.append(key)
    for row_index, text in enumerate(passage_texts):
        key = sha256_text(text)
        text_by_hash.setdefault(key, text)
        locations.setdefault(key, {"query": [], "passage": []})[
            "passage"
        ].append(row_index)
        passage_hashes.append(key)
    return {
        "queries": queries,
        "passage_ids": passage_ids,
        "passage_texts": passage_texts,
        "text_by_hash": text_by_hash,
        "locations": locations,
        "query_hashes": query_hashes,
        "passage_hashes": passage_hashes,
    }


def expected_memmap_bytes(rows: int, *, dtype: np.dtype[Any]) -> int:
    return rows * int(np.dtype(dtype).itemsize)


def initialize_vector_store(manifest: Mapping[str, Any]) -> None:
    vector_specs = (
        (PASSAGE_VECTORS_PATH, (CORPUS_COUNT, EMBEDDING_DIMENSION), np.float32),
        (QUERY_VECTORS_PATH, (QUERY_COUNT, EMBEDDING_DIMENSION), np.float32),
        (PASSAGE_STATUS_PATH, (CORPUS_COUNT,), np.uint8),
        (QUERY_STATUS_PATH, (QUERY_COUNT,), np.uint8),
    )
    if VECTOR_STORE_META_PATH.exists():
        meta = load_json(VECTOR_STORE_META_PATH)
        if (
            meta["manifest_sha256"] != sha256_file(MANIFEST_PATH)
            or meta["model"] != EMBEDDING_MODEL
            or int(meta["dimension"]) != EMBEDDING_DIMENSION
        ):
            raise RuntimeError("existing vector store metadata does not match manifest")
        for path, shape, dtype in vector_specs:
            expected = int(np.prod(shape)) * int(np.dtype(dtype).itemsize)
            if not path.is_file() or path.stat().st_size != expected:
                raise RuntimeError(f"vector store file size mismatch: {path}")
        return
    unexpected = [str(path) for path, _, _ in vector_specs if path.exists()]
    if unexpected:
        raise RuntimeError(
            f"vector store files exist without metadata; refusing reuse: {unexpected}"
        )
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    for path, shape, dtype in vector_specs:
        mapped = np.memmap(path, dtype=dtype, mode="w+", shape=shape)
        mapped[:] = 0
        mapped.flush()
        del mapped
    write_json_atomic(
        VECTOR_STORE_META_PATH,
        {
            "manifest_sha256": sha256_file(MANIFEST_PATH),
            "model": EMBEDDING_MODEL,
            "dimension": EMBEDDING_DIMENSION,
            "dtype": "float32",
            "passage_shape": [CORPUS_COUNT, EMBEDDING_DIMENSION],
            "query_shape": [QUERY_COUNT, EMBEDDING_DIMENSION],
            "passage_status_shape": [CORPUS_COUNT],
            "query_status_shape": [QUERY_COUNT],
            "created_utc": utc_now(),
            "normalization": "raw provider vectors until normalization.json is written",
            "successful_commit": "vector flush followed by durable status byte; status=1 is the resend guard",
        },
    )


def open_vector_store(mode: str = "r+") -> dict[str, np.memmap]:
    return {
        "passage_vectors": np.memmap(
            PASSAGE_VECTORS_PATH,
            dtype=np.float32,
            mode=mode,
            shape=(CORPUS_COUNT, EMBEDDING_DIMENSION),
        ),
        "query_vectors": np.memmap(
            QUERY_VECTORS_PATH,
            dtype=np.float32,
            mode=mode,
            shape=(QUERY_COUNT, EMBEDDING_DIMENSION),
        ),
        "passage_status": np.memmap(
            PASSAGE_STATUS_PATH,
            dtype=np.uint8,
            mode=mode,
            shape=(CORPUS_COUNT,),
        ),
        "query_status": np.memmap(
            QUERY_STATUS_PATH,
            dtype=np.uint8,
            mode=mode,
            shape=(QUERY_COUNT,),
        ),
    }


def validate_vector(vector: Sequence[float]) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    if array.shape != (EMBEDDING_DIMENSION,):
        raise ValueError(
            f"embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {array.shape}"
        )
    if not np.isfinite(array).all() or float(np.linalg.norm(array)) <= 0.0:
        raise ValueError("embedding contains invalid values or has zero norm")
    return array


def commit_vector(
    store: Mapping[str, np.memmap],
    locations: Mapping[str, Mapping[str, Sequence[int]]],
    text_hash: str,
    vector: Sequence[float],
) -> None:
    array = validate_vector(vector)
    refs = locations[text_hash]
    for row in refs["passage"]:
        store["passage_vectors"][int(row)] = array
    for row in refs["query"]:
        store["query_vectors"][int(row)] = array
    for row in refs["passage"]:
        store["passage_status"][int(row)] = 1
    for row in refs["query"]:
        store["query_status"][int(row)] = 1


def flush_vector_store(store: Mapping[str, np.memmap]) -> None:
    """Durably publish vectors before their status bytes become resend guards."""
    store["passage_vectors"].flush()
    store["query_vectors"].flush()
    store["passage_status"].flush()
    store["query_status"].flush()


def commit_vector_batch(
    store: Mapping[str, np.memmap],
    locations: Mapping[str, Mapping[str, Sequence[int]]],
    vectors: Sequence[tuple[str, Sequence[float]]],
) -> None:
    validated = [(text_hash, validate_vector(vector)) for text_hash, vector in vectors]
    for text_hash, array in validated:
        refs = locations[text_hash]
        for row in refs["passage"]:
            store["passage_vectors"][int(row)] = array
        for row in refs["query"]:
            store["query_vectors"][int(row)] = array
    store["passage_vectors"].flush()
    store["query_vectors"].flush()
    for text_hash, _ in validated:
        refs = locations[text_hash]
        for row in refs["passage"]:
            store["passage_status"][int(row)] = 1
        for row in refs["query"]:
            store["query_status"][int(row)] = 1
    store["passage_status"].flush()
    store["query_status"].flush()


def existing_vector_for_hash(
    store: Mapping[str, np.memmap],
    locations: Mapping[str, Mapping[str, Sequence[int]]],
    text_hash: str,
) -> np.ndarray | None:
    refs = locations[text_hash]
    for row in refs["passage"]:
        if int(store["passage_status"][int(row)]) == 1:
            return validate_vector(store["passage_vectors"][int(row)])
    for row in refs["query"]:
        if int(store["query_status"][int(row)]) == 1:
            return validate_vector(store["query_vectors"][int(row)])
    return None


def propagate_existing_vectors(
    store: Mapping[str, np.memmap], locations: Mapping[str, Mapping[str, Sequence[int]]]
) -> int:
    propagated = 0
    for text_hash in locations:
        vector = existing_vector_for_hash(store, locations, text_hash)
        if vector is None:
            continue
        refs = locations[text_hash]
        incomplete = any(
            int(store["passage_status"][int(row)]) != 1
            for row in refs["passage"]
        ) or any(
            int(store["query_status"][int(row)]) != 1 for row in refs["query"]
        )
        if incomplete:
            commit_vector(store, locations, text_hash, vector)
            propagated += 1
    if propagated:
        flush_vector_store(store)
    return propagated


def seed_prior_cache(
    store: Mapping[str, np.memmap],
    locations: Mapping[str, Mapping[str, Sequence[int]]],
) -> dict[str, int]:
    seeded = 0
    already_present = 0
    pending: list[tuple[str, Sequence[float]]] = []
    with PRIOR_VECTOR_CACHE.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            text_hash = str(row["text_sha256"])
            if text_hash not in locations:
                continue
            existing = existing_vector_for_hash(store, locations, text_hash)
            if existing is not None:
                already_present += 1
                continue
            if str(row["model"]) != EMBEDDING_MODEL or int(row["dimension"]) != EMBEDDING_DIMENSION:
                raise RuntimeError("prior cache model/dimension changed during seeding")
            pending.append((text_hash, row["embedding"]))
            seeded += 1
    if pending:
        commit_vector_batch(store, locations, pending)
    propagated = propagate_existing_vectors(store, locations)
    return {
        "seeded_unique": seeded,
        "already_present_unique": already_present,
        "duplicate_hashes_propagated": propagated,
    }


def hash_is_committed(
    store: Mapping[str, np.memmap],
    locations: Mapping[str, Mapping[str, Sequence[int]]],
    text_hash: str,
) -> bool:
    refs = locations[text_hash]
    return all(
        int(store["passage_status"][int(row)]) == 1 for row in refs["passage"]
    ) and all(
        int(store["query_status"][int(row)]) == 1 for row in refs["query"]
    )


class RetryWarningCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "retrying in" in message.lower():
            self.count += 1


async def request_embedding_batch(
    client: Any,
    config: Any,
    batch_id: int,
    hashes: Sequence[str],
    text_by_hash: Mapping[str, str],
) -> tuple[list[tuple[str, np.ndarray]], dict[str, Any]]:
    from deeptutor.services.embedding import EmbeddingRequest, validate_embedding_batch

    texts = [text_by_hash[text_hash] for text_hash in hashes]
    started = time.perf_counter()
    response = await client.adapter.embed(
        EmbeddingRequest(
            texts=texts,
            model=config.model,
            dimensions=config.dim or None,
        )
    )
    vectors = validate_embedding_batch(
        response.embeddings,
        expected_count=len(texts),
        binding=config.binding,
        model=config.model,
        batch_index=batch_id,
        total_batches=math.ceil(AUTHORIZED_MISSING_UNIQUE / EMBEDDING_BATCH_SIZE),
        start_index=(batch_id - 1) * EMBEDDING_BATCH_SIZE,
    )
    if str(response.model or config.model) != EMBEDDING_MODEL:
        raise RuntimeError("embedding response model changed")
    prepared = [
        (text_hash, validate_vector(vector))
        for text_hash, vector in zip(hashes, vectors)
    ]
    return prepared, {
        "batch_id": batch_id,
        "status": "success",
        "completed_utc": utc_now(),
        "item_count": len(hashes),
        "input_sha256": list(hashes),
        "input_characters": sum(len(text) for text in texts),
        "input_utf8_bytes": sum(len(text.encode("utf-8")) for text in texts),
        "provider_reported_usage": dict(response.usage or {}),
        "response_model": str(response.model or config.model),
        "actual_dimension": len(vectors[0]),
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        "adapter_retry_attempts": "not exposed by response; aggregate retry warnings counted separately",
    }


def embedding_log_audit() -> dict[str, Any]:
    rows = load_jsonl(EMBEDDING_BATCH_LOG_PATH) if EMBEDDING_BATCH_LOG_PATH.exists() else []
    successes = [row for row in rows if row.get("status") == "success"]
    failures = [row for row in rows if row.get("status") == "failed"]
    successful_hashes: list[str] = [
        str(value) for row in successes for value in row.get("input_sha256", [])
    ]
    usage_keys = sorted(
        {
            key
            for row in successes
            for key in (row.get("provider_reported_usage") or {})
        }
    )
    return {
        "success_log_rows": len(successes),
        "failed_log_rows": len(failures),
        "successful_unique_hashes": len(set(successful_hashes)),
        "duplicate_success_hash_records": len(successful_hashes)
        - len(set(successful_hashes)),
        "successful_characters": sum(int(row.get("input_characters") or 0) for row in successes),
        "successful_utf8_bytes": sum(int(row.get("input_utf8_bytes") or 0) for row in successes),
        "provider_reported_usage_totals": {
            key: sum(
                int((row.get("provider_reported_usage") or {}).get(key) or 0)
                for row in successes
            )
            for key in usage_keys
        },
    }


async def acquire_embeddings() -> dict[str, Any]:
    from deeptutor.services.embedding import EmbeddingClient, get_embedding_config

    manifest = load_and_verify_manifest()
    current_safe_config = validate_runtime_embedding_config()
    if current_safe_config != manifest["embedding"]["configuration"]:
        raise RuntimeError("embedding configuration changed after manifest freeze")
    initialize_vector_store(manifest)
    runtime = build_runtime_text_maps()
    locations = runtime["locations"]
    text_by_hash = runtime["text_by_hash"]
    store = open_vector_store("r+")
    seed_audit = seed_prior_cache(store, locations)
    missing_records = load_jsonl(MISSING_TEXTS_PATH)
    frozen_missing_hashes = [str(row["text_sha256"]) for row in missing_records]
    if len(frozen_missing_hashes) != AUTHORIZED_MISSING_UNIQUE:
        raise RuntimeError("missing-text manifest count changed")
    if NORMALIZATION_PATH.exists() and any(
        not hash_is_committed(store, locations, text_hash)
        for text_hash in frozen_missing_hashes
    ):
        raise RuntimeError("normalized vector store unexpectedly has missing rows")

    batches: list[tuple[int, list[str]]] = []
    for batch_index in range(
        1, math.ceil(len(frozen_missing_hashes) / EMBEDDING_BATCH_SIZE) + 1
    ):
        start = (batch_index - 1) * EMBEDDING_BATCH_SIZE
        frozen_batch = frozen_missing_hashes[start : start + EMBEDDING_BATCH_SIZE]
        pending = [
            text_hash
            for text_hash in frozen_batch
            if not hash_is_committed(store, locations, text_hash)
        ]
        if pending:
            batches.append((batch_index, pending))

    config = get_embedding_config()
    if config.model != EMBEDDING_MODEL:
        raise RuntimeError("configured embedding model changed")
    evaluation_config = replace(config, batch_size=EMBEDDING_BATCH_SIZE)
    client = EmbeddingClient(evaluation_config)
    retry_counter = RetryWarningCounter()
    adapter_logger = logging.getLogger(
        "deeptutor.services.embedding.adapters.openai_compatible"
    )
    adapter_logger.addHandler(retry_counter)
    queue: asyncio.Queue[tuple[int, list[str]] | None] = asyncio.Queue()
    for batch in batches:
        queue.put_nowait(batch)
    for _ in range(EMBEDDING_CONCURRENCY):
        queue.put_nowait(None)
    completed_this_invocation = 0
    committed_hashes_this_invocation = 0
    progress_lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal completed_this_invocation, committed_hashes_this_invocation
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                return
            batch_index, hashes = item
            try:
                vectors, log_row = await request_embedding_batch(
                    client,
                    evaluation_config,
                    batch_index,
                    hashes,
                    text_by_hash,
                )
                commit_vector_batch(store, locations, vectors)
                append_jsonl_durable(EMBEDDING_BATCH_LOG_PATH, log_row)
                async with progress_lock:
                    completed_this_invocation += 1
                    committed_hashes_this_invocation += len(hashes)
                    if completed_this_invocation % 100 == 0 or completed_this_invocation == len(batches):
                        print(
                            json.dumps(
                                {
                                    "embedding_progress": {
                                        "completed_batches_this_invocation": completed_this_invocation,
                                        "pending_batches_at_start": len(batches),
                                        "committed_hashes_this_invocation": committed_hashes_this_invocation,
                                    }
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
            except Exception as exc:
                append_jsonl_durable(
                    EMBEDDING_BATCH_LOG_PATH,
                    {
                        "batch_id": batch_index,
                        "status": "failed",
                        "completed_utc": utc_now(),
                        "item_count": len(hashes),
                        "input_sha256": list(hashes),
                        "input_characters": sum(
                            len(text_by_hash[text_hash]) for text_hash in hashes
                        ),
                        "error_type": type(exc).__name__,
                        "http_status": getattr(exc, "status", None),
                        "adapter_retry_attempts": "not exposed",
                    },
                )
                raise
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(EMBEDDING_CONCURRENCY)]
    try:
        await asyncio.gather(*workers)
    except Exception:
        for task in workers:
            if not task.done():
                task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise
    finally:
        adapter_logger.removeHandler(retry_counter)

    propagated = propagate_existing_vectors(store, locations)
    passage_complete = int(np.count_nonzero(store["passage_status"]))
    query_complete = int(np.count_nonzero(store["query_status"]))
    if passage_complete != CORPUS_COUNT or query_complete != QUERY_COUNT:
        raise RuntimeError(
            f"vector store incomplete: passages={passage_complete}, queries={query_complete}"
        )
    del store
    log_audit = embedding_log_audit()
    audit = {
        "completed_utc": utc_now(),
        "model": EMBEDDING_MODEL,
        "actual_dimension": EMBEDDING_DIMENSION,
        "logical_items": LOGICAL_ITEM_COUNT,
        "unique_texts": EXPECTED_UNIQUE_TEXTS,
        "prior_reused_unique": EXPECTED_REUSED_UNIQUE,
        "authorized_missing_unique": AUTHORIZED_MISSING_UNIQUE,
        "authorized_missing_characters": AUTHORIZED_MISSING_CHARACTERS,
        "pending_batches_at_invocation_start": len(batches),
        "successful_batches_this_invocation": completed_this_invocation,
        "committed_hashes_this_invocation": committed_hashes_this_invocation,
        "seed_audit": seed_audit,
        "post_commit_duplicate_hashes_propagated": propagated,
        "passage_rows_complete": passage_complete,
        "query_rows_complete": query_complete,
        "adapter_retry_warnings_this_invocation": retry_counter.count,
        "adapter_http_attempts": "not exposed; logical batch count is not HTTP attempt count",
        "log": log_audit,
        "batch_log_path": str(EMBEDDING_BATCH_LOG_PATH.relative_to(PROJECT_ROOT)),
        "batch_log_sha256": sha256_file(EMBEDDING_BATCH_LOG_PATH),
        "external_ocr_calls": 0,
        "external_generation_llm_calls": 0,
    }
    write_json_atomic(EMBEDDING_AUDIT_PATH, audit)
    return audit


def normalize_vector_store() -> dict[str, Any]:
    load_and_verify_manifest()
    if not EMBEDDING_AUDIT_PATH.is_file():
        raise RuntimeError("embedding audit required before normalization")
    if NORMALIZATION_PATH.is_file():
        existing = load_json(NORMALIZATION_PATH)
        for path, key in (
            (PASSAGE_VECTORS_PATH, "passage_vectors_sha256"),
            (QUERY_VECTORS_PATH, "query_vectors_sha256"),
            (PASSAGE_STATUS_PATH, "passage_status_sha256"),
            (QUERY_STATUS_PATH, "query_status_sha256"),
        ):
            if sha256_file(path) != existing[key]:
                raise RuntimeError(f"normalized vector store hash changed: {path}")
        return existing
    store = open_vector_store("r+")
    if int(np.count_nonzero(store["passage_status"])) != CORPUS_COUNT or int(
        np.count_nonzero(store["query_status"])
    ) != QUERY_COUNT:
        raise RuntimeError("cannot normalize incomplete vector store")
    started = time.perf_counter()
    for key, rows in (
        ("passage_vectors", CORPUS_COUNT),
        ("query_vectors", QUERY_COUNT),
    ):
        matrix = store[key]
        for start in range(0, rows, 512):
            end = min(rows, start + 512)
            block = np.asarray(matrix[start:end], dtype=np.float32)
            norms = np.linalg.norm(block, axis=1)
            if not np.isfinite(norms).all() or np.any(norms <= 0.0):
                raise RuntimeError(f"invalid vector norm in {key} rows {start}:{end}")
            matrix[start:end] = block / norms[:, None]
        matrix.flush()
    del store
    result = {
        "completed_utc": utc_now(),
        "method": "in-place float32 L2 normalization in 512-row blocks; idempotent if interrupted",
        "elapsed_seconds": time.perf_counter() - started,
        "passage_vectors_sha256": sha256_file(PASSAGE_VECTORS_PATH),
        "query_vectors_sha256": sha256_file(QUERY_VECTORS_PATH),
        "passage_status_sha256": sha256_file(PASSAGE_STATUS_PATH),
        "query_status_sha256": sha256_file(QUERY_STATUS_PATH),
    }
    write_json_atomic(NORMALIZATION_PATH, result)
    return result


def verify_normalized_store() -> dict[str, Any]:
    if not NORMALIZATION_PATH.is_file():
        raise RuntimeError("normalization audit is required before ranking")
    audit = load_json(NORMALIZATION_PATH)
    for path, key in (
        (PASSAGE_VECTORS_PATH, "passage_vectors_sha256"),
        (QUERY_VECTORS_PATH, "query_vectors_sha256"),
        (PASSAGE_STATUS_PATH, "passage_status_sha256"),
        (QUERY_STATUS_PATH, "query_status_sha256"),
    ):
        if sha256_file(path) != audit[key]:
            raise RuntimeError(f"normalized vector store hash mismatch: {path}")
    return audit


def query_relevance(query: Mapping[str, Any]) -> tuple[list[str], dict[str, int]]:
    scores = {
        str(item["passage_id"]): int(item["score"])
        for item in query["positive_qrels"]
    }
    return list(scores), scores


def ranking_row(
    query: Mapping[str, Any],
    scheme: str,
    ranking: Sequence[tuple[str, float]],
    *,
    latency_ms: float,
) -> dict[str, Any]:
    relevant, qrel_scores = query_relevance(query)
    passage_ranking = [passage_id for passage_id, _ in ranking]
    return {
        "query_id": str(query["query_id"]),
        "scheme": scheme,
        "relevant_passage_ids": relevant,
        "positive_qrel_scores": qrel_scores,
        "ranking": [
            {"rank": rank, "passage_id": passage_id, "score": score}
            for rank, (passage_id, score) in enumerate(ranking, 1)
        ],
        "latency_ms": latency_ms,
        **score_ranking(passage_ranking, relevant),
    }


def scheme_path(scheme: str) -> Path:
    if scheme not in SCHEMES:
        raise ValueError(f"unknown scheme: {scheme}")
    return RUN_ROOT / f"{scheme}.jsonl"


def scheme_audit_path(scheme: str) -> Path:
    return RUN_ROOT / f"{scheme}_audit.json"


def write_scheme_output(
    scheme: str, rows: Sequence[Mapping[str, Any]], audit: Mapping[str, Any]
) -> Path:
    if len(rows) != QUERY_COUNT:
        raise RuntimeError(f"{scheme} did not produce {QUERY_COUNT} rows")
    path = scheme_path(scheme)
    write_frozen_bytes(path, jsonl_bytes(rows))
    complete_audit = dict(audit)
    complete_audit["raw_results_sha256"] = sha256_file(path)
    write_frozen_json(scheme_audit_path(scheme), complete_audit)
    return path


def load_scheme_rows(scheme: str) -> list[dict[str, Any]]:
    rows = load_jsonl(scheme_path(scheme))
    if len(rows) != QUERY_COUNT or any(row.get("scheme") != scheme for row in rows):
        raise RuntimeError(f"invalid {scheme} output")
    return rows


def verify_existing_scheme_output(scheme: str) -> Path:
    path = scheme_path(scheme)
    load_scheme_rows(scheme)
    audit_path = scheme_audit_path(scheme)
    if not audit_path.is_file():
        raise RuntimeError(f"scheme output exists without audit: {scheme}")
    audit = load_json(audit_path)
    if audit.get("raw_results_sha256") != sha256_file(path):
        raise RuntimeError(f"scheme output hash mismatch: {scheme}")
    return path


def tokenize_corpus(texts: Sequence[str], *, cjk: bool) -> Any:
    prepared = (
        [prepare_cjk_bigram_text(text) for text in texts] if cjk else list(texts)
    )
    tokenized = bm25s.tokenize(
        prepared,
        stopwords="en",
        stemmer=Stemmer.Stemmer("english"),
        token_pattern=CJK_BIGRAM_TOKEN_PATTERN if cjk else r"(?u)\b\w\w+\b",
        show_progress=False,
    )
    del prepared
    gc.collect()
    return tokenized


def tokenize_query(text: str, *, cjk: bool) -> list[str]:
    prepared = prepare_cjk_bigram_text(text) if cjk else text
    tokenized = bm25s.tokenize(
        prepared,
        stopwords="en",
        stemmer=Stemmer.Stemmer("english"),
        token_pattern=CJK_BIGRAM_TOKEN_PATTERN if cjk else r"(?u)\b\w\w+\b",
        return_ids=False,
        show_progress=False,
    )
    return list(tokenized[0]) if tokenized else []


def latency_summary(values: Sequence[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 50),
        "p95_ms": percentile(values, 95),
        "mean_ms": float(np.mean(np.asarray(values, dtype=np.float64))),
    }


def run_dense_scheme() -> Path:
    load_and_verify_manifest()
    verify_normalized_store()
    output_path = scheme_path("dense")
    if output_path.exists():
        return verify_existing_scheme_output("dense")
    runtime = build_runtime_text_maps()
    queries = runtime["queries"]
    passage_ids = runtime["passage_ids"]
    load_started = time.perf_counter()
    passage_vectors = np.memmap(
        PASSAGE_VECTORS_PATH,
        dtype=np.float32,
        mode="r",
        shape=(CORPUS_COUNT, EMBEDDING_DIMENSION),
    )
    query_vectors = np.memmap(
        QUERY_VECTORS_PATH,
        dtype=np.float32,
        mode="r",
        shape=(QUERY_COUNT, EMBEDDING_DIMENSION),
    )
    load_seconds = time.perf_counter() - load_started
    for index in range(WARMUP_QUERIES):
        warm_scores = passage_vectors @ query_vectors[index]
        stable_top_scores(passage_ids, warm_scores, limit=TOP_K)
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    for index, query in enumerate(queries):
        started = time.perf_counter()
        scores = passage_vectors @ query_vectors[index]
        top = stable_top_scores(passage_ids, scores, limit=TOP_K)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed_ms)
        row = ranking_row(query, "dense", top, latency_ms=elapsed_ms)
        row["score_semantics"] = "cosine similarity from L2-normalized float32 vectors"
        rows.append(row)
    del passage_vectors, query_vectors
    audit = {
        "scheme": "dense",
        "completed_utc": utc_now(),
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "normalization_sha256": sha256_file(NORMALIZATION_PATH),
        "rows": len(rows),
        "corpus_count": CORPUS_COUNT,
        "top_k": TOP_K,
        "index_load_seconds": load_seconds,
        "warmup_queries_excluded": WARMUP_QUERIES,
        "local_retrieval_latency": latency_summary(latencies),
        "peak_rss_bytes": peak_rss_bytes(),
        "external_calls": 0,
    }
    write_scheme_output("dense", rows, audit)
    return output_path


def run_bm25_scheme(scheme: str) -> Path:
    if scheme not in ("bm25_legacy", "bm25_cjk_bigram_v1"):
        raise ValueError(f"not a BM25 scheme: {scheme}")
    load_and_verify_manifest()
    output_path = scheme_path(scheme)
    if output_path.exists():
        return verify_existing_scheme_output(scheme)
    queries, passage_ids, passage_texts = load_inputs()
    cjk = scheme == "bm25_cjk_bigram_v1"
    tokenize_started = time.perf_counter()
    tokenized = tokenize_corpus(passage_texts, cjk=cjk)
    tokenize_seconds = time.perf_counter() - tokenize_started
    del passage_texts
    gc.collect()
    index_started = time.perf_counter()
    index = bm25s.BM25()
    index.index(tokenized, show_progress=False)
    index_seconds = time.perf_counter() - index_started
    del tokenized
    gc.collect()

    def retrieve(query: Mapping[str, Any]) -> tuple[list[tuple[str, float]], int, int]:
        tokens = tokenize_query(str(query["text"]), cjk=cjk)
        scores = index.get_scores(tokens) if tokens else np.zeros(CORPUS_COUNT, dtype=np.float32)
        return stable_top_positive(passage_ids, scores, limit=TOP_K), len(tokens), int(np.count_nonzero(scores > 0.0))

    for query in queries[:WARMUP_QUERIES]:
        retrieve(query)
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    for query in queries:
        started = time.perf_counter()
        top, token_count, positive_count = retrieve(query)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed_ms)
        row = ranking_row(query, scheme, top, latency_ms=elapsed_ms)
        row["query_token_count"] = token_count
        row["positive_scored_candidate_count"] = positive_count
        rows.append(row)
    audit = {
        "scheme": scheme,
        "completed_utc": utc_now(),
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "rows": len(rows),
        "corpus_count": CORPUS_COUNT,
        "top_k": TOP_K,
        "tokenize_seconds": tokenize_seconds,
        "index_seconds": index_seconds,
        "warmup_queries_excluded": WARMUP_QUERIES,
        "local_retrieval_latency": latency_summary(latencies),
        "peak_rss_bytes": peak_rss_bytes(),
        "external_calls": 0,
    }
    write_scheme_output(scheme, rows, audit)
    return output_path


def ranking_tuples(row: Mapping[str, Any]) -> list[tuple[str, float]]:
    return [
        (str(item["passage_id"]), float(item["score"]))
        for item in row["ranking"]
    ]


def run_rrf_scheme(scheme: str) -> Path:
    branch = {
        "rrf_dense_legacy": "bm25_legacy",
        "rrf_dense_cjk_bigram_v1": "bm25_cjk_bigram_v1",
    }.get(scheme)
    if branch is None:
        raise ValueError(f"not an RRF scheme: {scheme}")
    load_and_verify_manifest()
    output_path = scheme_path(scheme)
    if output_path.exists():
        return verify_existing_scheme_output(scheme)
    queries, _, _ = load_inputs()
    dense_rows = load_scheme_rows("dense")
    bm25_rows = load_scheme_rows(branch)
    rows: list[dict[str, Any]] = []
    fusion_latencies: list[float] = []
    total_latencies: list[float] = []
    for query, dense_row, bm25_row in zip(queries, dense_rows, bm25_rows):
        dense = ranking_tuples(dense_row)
        bm25 = ranking_tuples(bm25_row)
        started = time.perf_counter()
        fused, union = rrf_rank(dense, bm25, limit=TOP_K, rrf_k=RRF_K)
        fusion_ms = (time.perf_counter() - started) * 1000.0
        total_ms = float(dense_row["latency_ms"]) + float(bm25_row["latency_ms"]) + fusion_ms
        fusion_latencies.append(fusion_ms)
        total_latencies.append(total_ms)
        row = ranking_row(query, scheme, fused, latency_ms=total_ms)
        dense_by_id = {passage_id: (rank, score) for rank, (passage_id, score) in enumerate(dense, 1)}
        bm25_by_id = {passage_id: (rank, score) for rank, (passage_id, score) in enumerate(bm25, 1)}
        for item in row["ranking"]:
            passage_id = str(item["passage_id"])
            item["rrf_score"] = item.pop("score")
            item["sources"] = [name for name, values in (("dense", dense_by_id), (branch, bm25_by_id)) if passage_id in values]
            item["dense_rank"] = dense_by_id.get(passage_id, (None, None))[0]
            item["dense_score"] = dense_by_id.get(passage_id, (None, None))[1]
            item["bm25_rank"] = bm25_by_id.get(passage_id, (None, None))[0]
            item["bm25_score"] = bm25_by_id.get(passage_id, (None, None))[1]
        relevant, _ = query_relevance(query)
        union_metrics = score_ranking(union["union_passage_ids"], relevant)
        row["branch_sources"] = ["dense", branch]
        row["dense_branch_ranking"] = dense_row["ranking"]
        row["bm25_branch_ranking"] = bm25_row["ranking"]
        row["candidate_union"] = {
            "size": union["union_size"],
            "passage_ids": union["union_passage_ids"],
            "hit": float(bool(set(relevant).intersection(union["union_passage_ids"]))),
            "recall": len(set(relevant).intersection(union["union_passage_ids"])) / len(relevant),
            "note": "branch union before fusion truncation; distinct from fused top50",
        }
        row["latency_components_ms"] = {
            "dense_retrieval": float(dense_row["latency_ms"]),
            "bm25_retrieval": float(bm25_row["latency_ms"]),
            "rrf_fusion": fusion_ms,
        }
        rows.append(row)
    audit = {
        "scheme": scheme,
        "completed_utc": utc_now(),
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "rows": len(rows),
        "branch_top_k": TOP_K,
        "final_top_k": TOP_K,
        "rrf_k": RRF_K,
        "fusion_only_latency": latency_summary(fusion_latencies),
        "sequential_local_total_latency": latency_summary(total_latencies),
        "latency_note": "per-query dense + BM25 + RRF; excludes index load/build and query embedding",
        "peak_rss_bytes": peak_rss_bytes(),
        "external_calls": 0,
    }
    write_scheme_output(scheme, rows, audit)
    return output_path


METRIC_FIELDS = {
    "mrr_at_10": "reciprocal_rank_at_10",
    "hit_at_5": "hit_at_5",
    "hit_at_20": "hit_at_20",
    "recall_at_20": "recall_at_20",
    "hit_at_50": "hit_at_50",
    "recall_at_50": "recall_at_50",
}


def aggregate_scheme(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for output_name, row_name in METRIC_FIELDS.items():
        values = [float(row[row_name]) for row in rows]
        result[output_name] = float(np.mean(np.asarray(values, dtype=np.float64)))
        if output_name.startswith("hit_at_"):
            result[f"{output_name}_n"] = int(sum(int(value) for value in values))
            result[f"{output_name}_N"] = len(values)
    result["local_latency"] = latency_summary(
        [float(row["latency_ms"]) for row in rows]
    )
    return result


def paired_bootstrap(left: Sequence[float], right: Sequence[float]) -> dict[str, Any]:
    if len(left) != QUERY_COUNT or len(right) != QUERY_COUNT:
        raise ValueError("paired bootstrap requires exactly 200 paired queries")
    differences = np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    sampled = rng.choice(
        differences, size=(BOOTSTRAP_SAMPLES, QUERY_COUNT), replace=True
    ).mean(axis=1)
    return {
        "difference": float(differences.mean()),
        "ci95_low": float(np.percentile(sampled, 2.5)),
        "ci95_high": float(np.percentile(sampled, 97.5)),
        "samples": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
    }


def compare_schemes(
    left_name: str,
    right_name: str,
    rows_by_scheme: Mapping[str, Sequence[Mapping[str, Any]]],
    metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    left_rows = rows_by_scheme[left_name]
    right_rows = rows_by_scheme[right_name]
    left_mrr = [float(row["reciprocal_rank_at_10"]) for row in left_rows]
    right_mrr = [float(row["reciprocal_rank_at_10"]) for row in right_rows]
    wins = sum(left > right for left, right in zip(left_mrr, right_mrr))
    losses = sum(left < right for left, right in zip(left_mrr, right_mrr))
    differences: dict[str, Any] = {}
    for metric_name in METRIC_FIELDS:
        left_value = float(metrics[left_name][metric_name])
        right_value = float(metrics[right_name][metric_name])
        absolute = left_value - right_value
        differences[metric_name] = {
            "absolute_change": absolute,
            "relative_change": absolute / right_value if right_value else None,
        }
    return {
        "left": left_name,
        "right": right_name,
        "interpretation": "left minus right",
        "metric_differences": differences,
        "query_mrr_win_tie_loss": {
            "win": wins,
            "tie": QUERY_COUNT - wins - losses,
            "loss": losses,
        },
        "paired_bootstrap_mrr_difference": paired_bootstrap(left_mrr, right_mrr),
    }


def aggregate_results() -> dict[str, Any]:
    load_and_verify_manifest()
    rows_by_scheme = {scheme: load_scheme_rows(scheme) for scheme in SCHEMES}
    query_orders = [
        [str(row["query_id"]) for row in rows_by_scheme[scheme]]
        for scheme in SCHEMES
    ]
    if any(order != query_orders[0] for order in query_orders[1:]) or len(set(query_orders[0])) != QUERY_COUNT:
        raise RuntimeError("scheme query order/set mismatch")
    metrics = {
        scheme: aggregate_scheme(rows_by_scheme[scheme]) for scheme in SCHEMES
    }
    hybrid_union: dict[str, Any] = {}
    for scheme in ("rrf_dense_legacy", "rrf_dense_cjk_bigram_v1"):
        unions = [row["candidate_union"] for row in rows_by_scheme[scheme]]
        sizes = [float(item["size"]) for item in unions]
        hybrid_union[scheme] = {
            "candidate_union_size": {
                "mean": float(np.mean(sizes)),
                "p50": percentile(sizes, 50),
                "p95": percentile(sizes, 95),
                "max": int(max(sizes)),
                "theoretical_max": TOP_K * 2,
            },
            "union_hit": float(np.mean([float(item["hit"]) for item in unions])),
            "union_hit_n": int(sum(int(float(item["hit"])) for item in unions)),
            "union_hit_N": QUERY_COUNT,
            "union_recall": float(np.mean([float(item["recall"]) for item in unions])),
            "note": "coverage over the pre-fusion branch union (up to 100), not fused top50",
        }
    comparison_pairs = (
        ("bm25_cjk_bigram_v1", "bm25_legacy"),
        ("dense", "bm25_legacy"),
        ("dense", "bm25_cjk_bigram_v1"),
        ("rrf_dense_legacy", "dense"),
        ("rrf_dense_cjk_bigram_v1", "dense"),
        ("rrf_dense_cjk_bigram_v1", "rrf_dense_legacy"),
    )
    comparisons = {
        f"{left}_minus_{right}": compare_schemes(
            left, right, rows_by_scheme, metrics
        )
        for left, right in comparison_pairs
    }
    paired_rows = []
    for left, right in comparison_pairs:
        for left_row, right_row in zip(rows_by_scheme[left], rows_by_scheme[right]):
            paired_rows.append(
                {
                    "query_id": str(left_row["query_id"]),
                    "left": left,
                    "right": right,
                    "differences": {
                        metric_name: float(left_row[row_field]) - float(right_row[row_field])
                        for metric_name, row_field in METRIC_FIELDS.items()
                    },
                }
            )
    paired_path = RUN_ROOT / "paired_differences.jsonl"
    write_frozen_bytes(paired_path, jsonl_bytes(paired_rows))
    raw_path = RUN_ROOT / "raw_results.jsonl"
    write_frozen_bytes(
        raw_path,
        jsonl_bytes(
            row for scheme in SCHEMES for row in rows_by_scheme[scheme]
        ),
    )
    embedding_audit = load_json(EMBEDDING_AUDIT_PATH)
    summary = {
        "schema_version": 1,
        "task": "RAG-FULL-CORPUS-HYBRID-ABLATION",
        "run_id": RUN_ID,
        "completed_utc": utc_now(),
        "query_count": QUERY_COUNT,
        "corpus_count": CORPUS_COUNT,
        "schemes": list(SCHEMES),
        "metrics": metrics,
        "hybrid_candidate_union": hybrid_union,
        "comparisons": comparisons,
        "paired_differences_path": str(paired_path.relative_to(PROJECT_ROOT)),
        "paired_differences_sha256": sha256_file(paired_path),
        "raw_results_path": str(raw_path.relative_to(PROJECT_ROOT)),
        "raw_results_sha256": sha256_file(raw_path),
        "scheme_audits": {
            scheme: load_json(scheme_audit_path(scheme)) for scheme in SCHEMES
        },
        "embedding_cost_audit": embedding_audit,
        "external_calls": {
            "embedding_new_unique_texts": embedding_audit["log"]["successful_unique_hashes"],
            "embedding_logical_batches": embedding_audit["log"]["success_log_rows"],
            "embedding_http_attempts": "not exposed by adapter",
            "ocr": 0,
            "generation_llm": 0,
            "download": 0,
        },
        "latency_scope": "warmed local retrieval/fusion only; index load/build and cached query embedding excluded; not online end-to-end",
    }
    write_json_atomic(RUN_ROOT / "summary.json", summary)
    return summary


def validate_runtime_embedding_config() -> dict[str, Any]:
    from deeptutor.services.embedding import get_embedding_config

    config = get_embedding_config()
    if config.model != EMBEDDING_MODEL:
        raise RuntimeError(f"configured model must remain {EMBEDDING_MODEL}")
    if not config.api_key:
        raise RuntimeError("configured embedding API key is absent")
    if config.send_dimensions is True and config.dim not in (None, 0, EMBEDDING_DIMENSION):
        raise RuntimeError(
            f"configured dimension would be sent and is incompatible: {config.dim}"
        )
    if int(config.batch_size) < 1:
        raise RuntimeError("configured embedding batch size is invalid")
    safe = safe_embedding_config(config)
    prior = load_json(PRIOR_MANIFEST)["embedding"]["configuration"]
    for key in (
        "binding",
        "provider_name",
        "provider_mode",
        "model",
        "configured_dimension",
        "send_dimensions",
        "endpoint_host",
        "endpoint_path",
    ):
        if safe[key] != prior[key]:
            raise RuntimeError(f"embedding configuration changed from validated pilot: {key}")
    if config.send_dimensions is None and config.model == EMBEDDING_MODEL:
        safe["dimension_behavior"] = (
            "configured 2048 is not sent for text-embedding-v4 under adapter auto mode; "
            "provider default is validated at 1024 on every response"
        )
    return safe


def audit_inputs() -> dict[str, Any]:
    queries, passage_ids, passage_texts = load_inputs()
    inventory = build_text_inventory(queries, passage_ids, passage_texts)
    prior = audit_prior_cache(set(inventory["unique"]))
    reusable = prior.pop("reusable_hashes")
    missing = [row for row in inventory["unique_rows"] if row["text_sha256"] not in reusable]
    result = {
        "logical_items": len(inventory["logical_rows"]),
        "unique_texts": len(inventory["unique_rows"]),
        "duplicate_logical_items": len(inventory["logical_rows"]) - len(inventory["unique_rows"]),
        "prior_cache": prior,
        "missing_unique_texts": len(missing),
        "missing_characters": sum(int(row["characters"]) for row in missing),
        "missing_utf8_bytes": sum(int(row["utf8_bytes"]) for row in missing),
        "logical_batches_at_max_10": math.ceil(len(missing) / EMBEDDING_BATCH_SIZE),
        "qrels": validate_original_qrels(queries, set(passage_ids)),
        "embedding_config": validate_runtime_embedding_config(),
    }
    expected = (
        result["logical_items"] == LOGICAL_ITEM_COUNT
        and result["unique_texts"] == EXPECTED_UNIQUE_TEXTS
        and prior["required_hashes_reused"] == EXPECTED_REUSED_UNIQUE
        and result["missing_unique_texts"] == AUTHORIZED_MISSING_UNIQUE
        and result["missing_characters"] == AUTHORIZED_MISSING_CHARACTERS
    )
    if not expected:
        raise RuntimeError("preflight inventory no longer matches authorization")
    result["authorization_match"] = True
    return result


def self_check() -> dict[str, Any]:
    ids = ["10", "2", "30", "4"]
    top = stable_top_scores(ids, np.asarray([0.4, 0.4, 0.1, 0.2]), limit=3)
    if [item[0] for item in top] != ["2", "10", "4"]:
        raise RuntimeError("stable dense tie self-check failed")
    fused, union = rrf_rank(
        [("1", 0.9), ("2", 0.8), ("3", 0.7)],
        [("4", 3.0), ("5", 2.0), ("6", 1.0)],
        limit=3,
        rrf_k=RRF_K,
    )
    if union["union_size"] != 6 or len(fused) != 3:
        raise RuntimeError("RRF union/final self-check failed")
    ranking = [f"p{index}" for index in range(1, 51)]
    metrics = score_ranking(ranking, {"p3", "p25", "p50", "missing"})
    if not math.isclose(float(metrics["reciprocal_rank_at_10"]), 1 / 3) or metrics["recall_at_50"] != 0.75:
        raise RuntimeError("metric cutoff self-check failed")
    mock_rows = [
        {**{field: 0.0 for field in METRIC_FIELDS.values()}, "latency_ms": 1.0}
        for _ in range(QUERY_COUNT)
    ]
    mock_rows[0]["reciprocal_rank_at_10"] = 1.0
    aggregated = aggregate_scheme(mock_rows)
    if aggregated["mrr_at_10"] != 1.0 / QUERY_COUNT or aggregated["hit_at_5"] != 0.0:
        raise RuntimeError("explicit aggregate metric mapping self-check failed")
    return {"passed": True, "checks": 4}


def validate_run() -> dict[str, Any]:
    manifest = load_and_verify_manifest()
    normalization = verify_normalized_store()
    queries, passage_ids, _ = load_inputs()
    passage_id_set = set(passage_ids)
    expected_query_ids = [str(query["query_id"]) for query in queries]
    rows_by_scheme = {scheme: load_scheme_rows(scheme) for scheme in SCHEMES}
    checks: list[dict[str, Any]] = []

    def add(check: str, passed: bool, detail: Any = None) -> None:
        checks.append({"check": check, "passed": bool(passed), "detail": detail})

    add(
        "same frozen 200 query IDs and order in all five schemes",
        all(
            [str(row["query_id"]) for row in rows_by_scheme[scheme]]
            == expected_query_ids
            for scheme in SCHEMES
        ),
    )
    rows_valid = True
    metric_valid = True
    hybrid_valid = True
    for scheme, rows in rows_by_scheme.items():
        for query, row in zip(queries, rows):
            relevant, qrel_scores = query_relevance(query)
            if row["relevant_passage_ids"] != relevant or row["positive_qrel_scores"] != qrel_scores:
                rows_valid = False
            ranking_items = row["ranking"]
            ids = [str(item["passage_id"]) for item in ranking_items]
            if len(ids) > TOP_K or len(ids) != len(set(ids)) or not set(ids) <= passage_id_set:
                rows_valid = False
            score_key = "rrf_score" if scheme.startswith("rrf_") else "score"
            actual = [(str(item["passage_id"]), float(item[score_key])) for item in ranking_items]
            expected_order = sorted(actual, key=lambda item: (-item[1], stable_id_key(item[0])))
            if actual != expected_order or [int(item["rank"]) for item in ranking_items] != list(range(1, len(ids) + 1)):
                rows_valid = False
            if scheme.startswith("bm25_") and any(score <= 0.0 for _, score in actual):
                rows_valid = False
            recomputed = score_ranking(ids, relevant)
            for field in METRIC_FIELDS.values():
                if not math.isclose(float(row[field]), float(recomputed[field]), rel_tol=0.0, abs_tol=1e-12):
                    metric_valid = False
            if row["first_relevant_rank"] != recomputed["first_relevant_rank"]:
                metric_valid = False
            if scheme.startswith("rrf_"):
                dense = [(str(item["passage_id"]), float(item["score"])) for item in row["dense_branch_ranking"]]
                bm25 = [(str(item["passage_id"]), float(item["score"])) for item in row["bm25_branch_ranking"]]
                fused, union = rrf_rank(dense, bm25, limit=TOP_K, rrf_k=RRF_K)
                if [item[0] for item in fused] != ids or any(
                    not math.isclose(score, float(item["rrf_score"]), rel_tol=0.0, abs_tol=1e-15)
                    for (passage_id, score), item in zip(fused, ranking_items)
                    if passage_id == str(item["passage_id"])
                ):
                    hybrid_valid = False
                expected_union = union["union_passage_ids"]
                union_row = row["candidate_union"]
                found = set(relevant).intersection(expected_union)
                if (
                    union_row["passage_ids"] != expected_union
                    or int(union_row["size"]) != len(expected_union)
                    or float(union_row["hit"]) != float(bool(found))
                    or not math.isclose(float(union_row["recall"]), len(found) / len(relevant), abs_tol=1e-12)
                ):
                    hybrid_valid = False
                for item in ranking_items:
                    expected_sources = []
                    passage_id = str(item["passage_id"])
                    if passage_id in {value[0] for value in dense}:
                        expected_sources.append("dense")
                    if passage_id in {value[0] for value in bm25}:
                        expected_sources.append(row["branch_sources"][1])
                    if item["sources"] != expected_sources:
                        hybrid_valid = False
    add("rankings are unique, bounded, stable-score ordered, and reference corpus IDs", rows_valid)
    add("all six requested per-query metric fields recompute exactly", metric_valid)
    add("RRF scores, branch provenance, pre-fusion union coverage, and fused top50 recompute", hybrid_valid)

    summary = load_json(RUN_ROOT / "summary.json")
    aggregates_valid = True
    for scheme in SCHEMES:
        recomputed = aggregate_scheme(rows_by_scheme[scheme])
        for metric_name in METRIC_FIELDS:
            if not math.isclose(
                float(recomputed[metric_name]),
                float(summary["metrics"][scheme][metric_name]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                aggregates_valid = False
    add("summary aggregates use explicit field mapping and recompute from raw rows", aggregates_valid)

    embedding = load_json(EMBEDDING_AUDIT_PATH)
    log = embedding["log"]
    embedding_valid = (
        int(embedding["passage_rows_complete"]) == CORPUS_COUNT
        and int(embedding["query_rows_complete"]) == QUERY_COUNT
        and int(embedding["prior_reused_unique"]) == EXPECTED_REUSED_UNIQUE
        and int(log["successful_unique_hashes"]) == AUTHORIZED_MISSING_UNIQUE
        and int(log["duplicate_success_hash_records"]) == 0
        and int(log["successful_characters"]) == AUTHORIZED_MISSING_CHARACTERS
        and int(log["success_log_rows"]) == math.ceil(AUTHORIZED_MISSING_UNIQUE / EMBEDDING_BATCH_SIZE)
    )
    add("embedding reuse/new/character/logical-batch audit matches the authorization", embedding_valid, log)
    add(
        "normalized float32 memmaps retain recorded hashes",
        all(
            sha256_file(path) == normalization[key]
            for path, key in (
                (PASSAGE_VECTORS_PATH, "passage_vectors_sha256"),
                (QUERY_VECTORS_PATH, "query_vectors_sha256"),
                (PASSAGE_STATUS_PATH, "passage_status_sha256"),
                (QUERY_STATUS_PATH, "query_status_sha256"),
            )
        ),
    )
    add(
        "combined raw output contains 1,000 rows and matches its summary hash",
        len(load_jsonl(RUN_ROOT / "raw_results.jsonl")) == QUERY_COUNT * len(SCHEMES)
        and sha256_file(RUN_ROOT / "raw_results.jsonl") == summary["raw_results_sha256"],
    )
    add(
        "all six comparison pairs retain 200 per-query metric differences",
        len(load_jsonl(RUN_ROOT / "paired_differences.jsonl")) == QUERY_COUNT * 6
        and sha256_file(RUN_ROOT / "paired_differences.jsonl")
        == summary["paired_differences_sha256"],
    )
    add(
        "ranking phases made no embedding/OCR/generation/download calls",
        all(load_json(scheme_audit_path(scheme))["external_calls"] == 0 for scheme in SCHEMES)
        and summary["external_calls"]["ocr"] == 0
        and summary["external_calls"]["generation_llm"] == 0
        and summary["external_calls"]["download"] == 0,
    )
    passed = all(check["passed"] for check in checks)
    result = {
        "schema_version": 1,
        "task": manifest["task"],
        "run_id": manifest["run_id"],
        "validated_utc": utc_now(),
        "passed": passed,
        "checks": checks,
        "limits": [
            "public mMARCO Chinese dev subset; post-hoc same-query ablation, not a fresh blind benchmark",
            "online query embedding and online end-to-end latency were not measured",
            "retrieval metrics do not measure answer correctness or citation support",
        ],
    }
    write_json_atomic(RUN_ROOT / "validation.json", result)
    if not passed:
        raise RuntimeError("validation failed; inspect validation.json")
    return result


def format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_report(summary: Mapping[str, Any]) -> Path:
    report_path = PROJECT_ROOT / "docs" / "RAG_FULL_CORPUS_HYBRID.md"
    labels = {
        "bm25_legacy": "Legacy BM25",
        "bm25_cjk_bigram_v1": "CJK Bigram BM25",
        "dense": "Dense",
        "rrf_dense_legacy": "Dense + Legacy RRF",
        "rrf_dense_cjk_bigram_v1": "Dense + CJK RRF",
    }
    table_rows = []
    for scheme in SCHEMES:
        metric = summary["metrics"][scheme]
        latency = metric["local_latency"]
        table_rows.append(
            "| {label} | {mrr:.4f} | {h5}/{n} ({h5p}) | {h20}/{n} ({h20p}) | {r20} | {h50}/{n} ({h50p}) | {r50} | {p50:.2f} | {p95:.2f} |".format(
                label=labels[scheme],
                mrr=metric["mrr_at_10"],
                h5=metric["hit_at_5_n"],
                n=QUERY_COUNT,
                h5p=format_pct(metric["hit_at_5"]),
                h20=metric["hit_at_20_n"],
                h20p=format_pct(metric["hit_at_20"]),
                r20=format_pct(metric["recall_at_20"]),
                h50=metric["hit_at_50_n"],
                h50p=format_pct(metric["hit_at_50"]),
                r50=format_pct(metric["recall_at_50"]),
                p50=latency["p50_ms"],
                p95=latency["p95_ms"],
            )
        )
    union_rows = []
    for scheme in ("rrf_dense_legacy", "rrf_dense_cjk_bigram_v1"):
        union = summary["hybrid_candidate_union"][scheme]
        sizes = union["candidate_union_size"]
        union_rows.append(
            f"| {labels[scheme]} | {sizes['mean']:.2f} | {sizes['p50']:.0f} | {sizes['p95']:.0f} | {union['union_hit_n']}/{QUERY_COUNT} ({format_pct(union['union_hit'])}) | {format_pct(union['union_recall'])} |"
        )
    embedding = summary["embedding_cost_audit"]
    usage = json.dumps(embedding["log"]["provider_reported_usage_totals"], ensure_ascii=False, sort_keys=True)
    text = f"""# RAG 全语料 Hybrid 消融评测

## 范围与冻结条件

本次是同一组冻结的 200 条公开 mMARCO 中文 dev 查询、106,813 条 passage 上的五路 post-hoc 消融：Legacy BM25、CJK Bigram BM25、Dense、Dense+Legacy RRF、Dense+CJK RRF。查询、qrels、模型和参数均未在看到排序结果后更换；每个分支和最终融合固定取 Top-50，RRF `k=60`。Top-20 扩到 Top-50 仅为报告 Hit/Recall@20、@50 与分支候选并集覆盖率，不是按结果选择。

## 五路结果

| 方案 | MRR@10 | Hit@5 | Hit@20 | Recall@20 | Hit@50 | Recall@50 | 本地延迟 P50 ms | P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table_rows)}

延迟为同一机器、单数值线程、预热后的本地检索/融合时间。Dense 查询向量已缓存；不包含索引构建/加载、在线 query embedding，也不代表线上端到端延迟。Hybrid 延迟按同次顺序执行的 Dense 检索、BM25 检索与 RRF 融合求和。

## Hybrid 候选并集覆盖

| 方案 | 并集均值 | P50 | P95 | Union Hit | Union Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(union_rows)}

候选并集是 Dense Top-50 与对应 BM25 正分 Top-50 在融合截断前的 union，最多 100 条；上表不能与最终 fused Top-50 混作同一口径。

## 嵌入复用与成本审计

- 模型与维度：`{embedding['model']}`，实际 `{embedding['actual_dimension']}` 维。
- 逻辑输入：{embedding['logical_items']:,}；唯一文本：{embedding['unique_texts']:,}。
- 复用既有唯一向量：{embedding['prior_reused_unique']:,}；新发送唯一文本：{embedding['log']['successful_unique_hashes']:,}；字符数：{embedding['log']['successful_characters']:,}。
- 成功逻辑批次：{embedding['log']['success_log_rows']:,}，单批最多 {EMBEDDING_BATCH_SIZE}，并发 {EMBEDDING_CONCURRENCY}。逻辑批次数不等于 HTTP 尝试数；适配器未暴露实际 HTTP 尝试总数。
- 端点返回 usage 汇总：`{usage}`。OCR、生成式 LLM 与下载调用均为 0。

## 恢复安全说明

每个成功批次先把 float32 向量写入 memmap 并 flush，再持久化状态字节和批次日志；恢复运行只扫描冻结 missing manifest 中状态未完成的 hash，已提交向量不会重发。向量归一化完成后记录并校验文件 SHA-256；排序原始结果按方案冻结保存。

## 解释边界

这是公开 dev 子集上的同查询 post-hoc 消融，不是新的盲测，也不是原始数百万 passage 的完整 mMARCO。指标只衡量 passage 检索；未衡量最终回答正确性、引文支持或生产流量行为。未加入 reranker、query rewrite、metadata filter 或参数调优。

完整逐查询排序、分数、分支来源和候选并集位于 `{summary['raw_results_path']}`；逐查询成对差异位于 `{summary['paired_differences_path']}`；胜平负、bootstrap 区间和聚合指标位于同目录 `summary.json`；验证证据位于同目录 `validation.json`。
"""
    temporary = report_path.with_suffix(".md.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(report_path)
    return report_path


def run_evaluation() -> dict[str, Any]:
    load_and_verify_manifest()
    verify_normalized_store()
    for phase in ("rank-dense", "rank-legacy", "rank-cjk", "fuse-legacy", "fuse-cjk"):
        subprocess.run([sys.executable, str(SCRIPT_PATH), phase], cwd=PROJECT_ROOT, check=True)
    summary = aggregate_results()
    validate_run()
    write_report(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=(
            "self-check",
            "audit-inputs",
            "prepare",
            "embed",
            "normalize",
            "rank-dense",
            "rank-legacy",
            "rank-cjk",
            "fuse-legacy",
            "fuse-cjk",
            "evaluate",
            "validate",
            "all",
        ),
    )
    args = parser.parse_args()
    if args.phase == "self-check":
        result = self_check()
    elif args.phase == "audit-inputs":
        result = audit_inputs()
    elif args.phase == "prepare":
        result = write_inventory_and_manifest()
    elif args.phase == "embed":
        result = asyncio.run(acquire_embeddings())
    elif args.phase == "normalize":
        result = normalize_vector_store()
    elif args.phase == "rank-dense":
        result = {"output": str(run_dense_scheme())}
    elif args.phase == "rank-legacy":
        result = {"output": str(run_bm25_scheme("bm25_legacy"))}
    elif args.phase == "rank-cjk":
        result = {"output": str(run_bm25_scheme("bm25_cjk_bigram_v1"))}
    elif args.phase == "fuse-legacy":
        result = {"output": str(run_rrf_scheme("rrf_dense_legacy"))}
    elif args.phase == "fuse-cjk":
        result = {"output": str(run_rrf_scheme("rrf_dense_cjk_bigram_v1"))}
    elif args.phase == "evaluate":
        result = run_evaluation()
    elif args.phase == "validate":
        result = validate_run()
    else:
        write_inventory_and_manifest()
        asyncio.run(acquire_embeddings())
        normalize_vector_store()
        result = run_evaluation()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
