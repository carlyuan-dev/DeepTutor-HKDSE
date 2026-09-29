#!/usr/bin/env python3
"""Validate legacy vs CJK-bigram BM25 on the full pinned mMARCO Chinese corpus."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
import gc
import hashlib
import heapq
import json
import math
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time
from typing import Any

import bm25s
import numpy as np
import Stemmer

from deeptutor.services.rag.pipelines.llamaindex.bm25_tokenization import (
    CJK_BIGRAM_TOKEN_PATTERN,
    cjk_bigram_tokenizer_manifest,
    prepare_cjk_bigram_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_EVAL_ROOT = PROJECT_ROOT / "data" / "evaluations" / "rag_public_holdout_final"
REVISION = "ff68e85c3a75b54db4eb603cf7dd4dd54ea1cdb3"
SOURCE_ROOT = PUBLIC_EVAL_ROOT / "source" / REVISION
SOURCE_FILES = {
    "corpus": SOURCE_ROOT / "corpus-dev.parquet",
    "qrels": SOURCE_ROOT / "qrels-dev.parquet",
    "queries": SOURCE_ROOT / "queries-dev.parquet",
    "dataset_card": SOURCE_ROOT / "README.md",
}
PRIOR_RUN_ROOT = (
    PUBLIC_EVAL_ROOT / "runs" / "mmarco_zh_dev_200_seed20260911"
)
PRIOR_SNAPSHOT = PRIOR_RUN_ROOT / "selected_snapshot.json"
PRIOR_MANIFEST = PRIOR_RUN_ROOT / "manifest.json"
DEV_BIGRAM_RUN = (
    PROJECT_ROOT
    / "data"
    / "evaluations"
    / "rag_chinese_tokenization_ablation"
    / "runs"
    / "20260909T063609Z"
    / "run_config.json"
)
EVAL_ROOT = PROJECT_ROOT / "data" / "evaluations" / "rag_full_corpus_bm25_validation"
RUN_ID = "mmarco_zh_dev_200_full_106813"
RUN_ROOT = EVAL_ROOT / "runs" / RUN_ID
SCRIPT_PATH = Path(__file__).resolve()

QUERY_COUNT = 200
CORPUS_COUNT = 106_813
TOP_K = 20
MRR_K = 10
HIT_K = 5
BOOTSTRAP_SAMPLES = 5_000
BOOTSTRAP_SEED = 20260911
SCHEMES = ("bm25_legacy", "bm25_cjk_bigram_v1")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id_key(value: str) -> tuple[int, int | str, str]:
    text = str(value)
    return (0, int(text), text) if text.isdecimal() else (1, text, text)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def write_frozen_json(path: Path, value: Any) -> str:
    payload = canonical_json_bytes(value)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"refusing to replace frozen artifact: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return sha256_bytes(payload)


def verify_frozen_file(path: Path, checksum_path: Path) -> str:
    expected = checksum_path.read_text(encoding="utf-8").strip().split()[0]
    actual = sha256_file(path)
    if expected != actual:
        raise RuntimeError(f"frozen checksum mismatch: {path}")
    return actual


def stable_top_positive(
    passage_ids: Sequence[str], scores: Sequence[float], *, limit: int
) -> list[tuple[str, float]]:
    """Return positive scores ordered by score desc then stable passage ID."""
    if len(passage_ids) != len(scores):
        raise ValueError("passage_ids and scores must have equal lengths")
    eligible = (
        (str(passage_id), float(score))
        for passage_id, score in zip(passage_ids, scores)
        if float(score) > 0.0
    )
    return heapq.nsmallest(
        max(0, int(limit)),
        eligible,
        key=lambda item: (-item[1], stable_id_key(item[0])),
    )


def score_ranking(
    ranking: Sequence[str], relevant_passage_ids: Iterable[str]
) -> dict[str, float | int | None]:
    relevant = {str(value) for value in relevant_passage_ids}
    if not relevant:
        raise ValueError("at least one relevant passage is required")
    first_rank = next(
        (
            rank
            for rank, passage_id in enumerate(ranking[:MRR_K], 1)
            if passage_id in relevant
        ),
        None,
    )
    found_at_5 = relevant.intersection(ranking[:HIT_K])
    return {
        "reciprocal_rank_at_10": (
            0.0 if first_rank is None else 1.0 / first_rank
        ),
        "hit_at_5": float(bool(found_at_5)),
        "recall_at_5": len(found_at_5) / len(relevant),
        "first_relevant_rank": first_rank,
    }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_parquet_rows(
    path: Path, *, columns: Sequence[str] | None = None
) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    selected_columns = list(columns) if columns is not None else None
    return pq.read_table(path, columns=selected_columns).to_pylist()


def load_full_corpus() -> tuple[list[str], list[str]]:
    rows = load_parquet_rows(SOURCE_FILES["corpus"], columns=("_id", "text"))
    pairs = [(str(row["_id"]), "" if row["text"] is None else str(row["text"])) for row in rows]
    if len(pairs) != CORPUS_COUNT:
        raise RuntimeError(f"expected {CORPUS_COUNT} corpus rows, got {len(pairs)}")
    if len({passage_id for passage_id, _ in pairs}) != CORPUS_COUNT:
        raise RuntimeError("full corpus passage IDs are not unique")
    pairs.sort(key=lambda item: stable_id_key(item[0]))
    return [item[0] for item in pairs], [item[1] for item in pairs]


def original_query_and_qrels() -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    query_rows = load_parquet_rows(SOURCE_FILES["queries"], columns=("_id", "text"))
    queries = {
        str(row["_id"]): "" if row["text"] is None else str(row["text"])
        for row in query_rows
    }
    qrel_rows = load_parquet_rows(
        SOURCE_FILES["qrels"], columns=("query-id", "corpus-id", "score")
    )
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for row in qrel_rows:
        score = int(row["score"])
        if score > 0:
            qrels[str(row["query-id"])][str(row["corpus-id"])] = score
    return queries, dict(qrels)


def validate_prior_lineage(
    snapshot: Mapping[str, Any],
    source_queries: Mapping[str, str],
    source_qrels: Mapping[str, Mapping[str, int]],
    corpus_ids: set[str],
) -> dict[str, Any]:
    selected_queries = list(snapshot.get("queries") or [])
    if len(selected_queries) != QUERY_COUNT:
        raise RuntimeError("prior snapshot does not contain the frozen 200 queries")
    query_ids: list[str] = []
    qrel_counts: Counter[int] = Counter()
    positive_ids: set[str] = set()
    for row in selected_queries:
        query_id = str(row["query_id"])
        query_ids.append(query_id)
        if source_queries.get(query_id) != str(row["text"]):
            raise RuntimeError(f"query text changed from source: {query_id}")
        expected = {
            str(item["passage_id"]): int(item["score"])
            for item in row["positive_qrels"]
        }
        if expected != dict(source_qrels.get(query_id, {})):
            raise RuntimeError(f"qrels changed from source: {query_id}")
        if not expected or not set(expected) <= corpus_ids:
            raise RuntimeError(f"missing full-corpus positive for {query_id}")
        qrel_counts[len(expected)] += 1
        positive_ids.update(expected)
    if len(set(query_ids)) != QUERY_COUNT:
        raise RuntimeError("prior frozen query IDs are not distinct")

    prior_candidates = list(snapshot.get("candidates") or [])
    prior_candidate_ids = {str(row["passage_id"]) for row in prior_candidates}
    if len(prior_candidate_ids) != 3000 or not positive_ids <= prior_candidate_ids:
        raise RuntimeError("prior 3000-passage pool does not contain all positives")
    return {
        "query_count": QUERY_COUNT,
        "query_ids": query_ids,
        "query_ids_sha256": sha256_bytes(canonical_json_bytes(query_ids)),
        "query_text_and_qrels_sha256": sha256_bytes(
            canonical_json_bytes(selected_queries)
        ),
        "positive_qrels_total": sum(
            len(row["positive_qrels"]) for row in selected_queries
        ),
        "unique_positive_passages": len(positive_ids),
        "relevant_passages_per_query_distribution": {
            str(count): frequency for count, frequency in sorted(qrel_counts.items())
        },
        "prior_pool": {
            "candidate_count": len(prior_candidate_ids),
            "all_positive_passages": len(positive_ids),
            "random_other_passages": len(prior_candidate_ids - positive_ids),
        },
    }


def full_corpus_digest(passage_ids: Sequence[str], texts: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for passage_id, text in zip(passage_ids, texts):
        digest.update(passage_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(text.encode("utf-8")).digest())
        digest.update(b"\n")
    return digest.hexdigest()


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

    versions: dict[str, str] = {
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    for name in ("bm25s", "PyStemmer", "pyarrow"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "unknown"
    return versions


def build_manifest() -> dict[str, Any]:
    missing = [str(path) for path in [*SOURCE_FILES.values(), PRIOR_SNAPSHOT, PRIOR_MANIFEST, DEV_BIGRAM_RUN] if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing frozen input files: {missing}")
    prior_manifest = load_json(PRIOR_MANIFEST)
    prior_snapshot = load_json(PRIOR_SNAPSHOT)
    dev_run = load_json(DEV_BIGRAM_RUN)
    passage_ids, corpus_texts = load_full_corpus()
    source_queries, source_qrels = original_query_and_qrels()
    lineage = validate_prior_lineage(
        prior_snapshot, source_queries, source_qrels, set(passage_ids)
    )
    source_file_audit: dict[str, Any] = {}
    for name, path in SOURCE_FILES.items():
        actual_hash = sha256_file(path)
        prior_info = prior_manifest["source"]["files"][name]
        if actual_hash != prior_info["sha256"]:
            raise RuntimeError(f"source file changed since prior freeze: {name}")
        source_file_audit[name] = {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "sha256": actual_hash,
            "bytes": path.stat().st_size,
        }
    cjk_manifest = cjk_bigram_tokenizer_manifest()
    frozen_utc = utc_now()
    return {
        "schema_version": 1,
        "task": "RAG-FULL-CORPUS-BM25-VALIDATION",
        "run_id": RUN_ID,
        "frozen_utc": frozen_utc,
        "experiment_role": "post-hoc corpus-scale robustness validation after observing the 3000-passage result; queries and retrieval strategies unchanged; not a new blind test",
        "source": {
            "dataset_id": "mteb/MMarcoRetrieval",
            "dataset_description": "Chinese mMARCO retrieval data packaged by MTEB",
            "revision": REVISION,
            "split": "dev",
            "corpus_scope": "all 106813 passages in the pinned MTEB-packaged dev corpus; not the original multi-million-passage mMARCO corpus",
            "qrels_provenance": "pinned mteb/MMarcoRetrieval default config, dev split, original rows with score > 0",
            "license": prior_manifest["source"]["license"],
            "files": source_file_audit,
            "corpus_count": len(passage_ids),
            "empty_passage_count": sum(not text.strip() for text in corpus_texts),
            "stable_id_and_text_sha256_digest": full_corpus_digest(
                passage_ids, corpus_texts
            ),
        },
        "query_lineage": {
            **lineage,
            "prior_snapshot_path": str(PRIOR_SNAPSHOT.relative_to(PROJECT_ROOT)),
            "prior_snapshot_sha256": sha256_file(PRIOR_SNAPSHOT),
            "prior_public_manifest_path": str(PRIOR_MANIFEST.relative_to(PROJECT_ROOT)),
            "prior_public_manifest_sha256": sha256_file(PRIOR_MANIFEST),
            "selection_reused_without_change": True,
        },
        "timeline": {
            "cjk_bigram_selected_on_24_query_development_set_started_utc": dev_run["started_utc"],
            "cjk_bigram_selected_on_24_query_development_set_completed_utc": dev_run["completed_utc"],
            "public_200_query_small_pool_manifest_frozen_utc": prior_manifest["frozen_utc"],
            "public_small_pool_rankings_observed_before_this_validation": True,
            "current_full_corpus_manifest_frozen_utc": frozen_utc,
        },
        "retrieval": {
            "schemes": list(SCHEMES),
            "only_variable": "BM25 tokenizer profile",
            "shared_full_corpus": True,
            "top_k": TOP_K,
            "nonpositive_policy": "score <= 0 excluded",
            "tie_break": "descending BM25 score then stable numeric-or-lexical passage ID",
            "bm25_defaults": "bm25s.BM25() defaults, identical in both branches",
            "legacy": {
                "profile": "legacy",
                "token_pattern": r"(?u)\b\w\w+\b",
                "stopwords": "en",
                "stemmer": "english",
            },
            "cjk_bigram_v1": cjk_manifest,
            "profile_difference_note": "CJK runs become overlapping character bigrams, one-character runs are retained as unigrams, Latin words are lowercased then English-stemmed, numeric expressions stay whole, and token_pattern changes to (?u)\\b\\w+\\b; no simplified/traditional normalization",
            "metadata_filter": False,
            "reranker": False,
            "query_rewrite": False,
            "parameter_tuning": False,
        },
        "cache_semantics": {
            "cjk_profile_fingerprint": "SHA-256 of the tokenizer spec fields only; it does not include arbitrary code or corpus content",
            "runtime_validation": "bm25s and PyStemmer versions are stored separately in the complete profile manifest; persisted CJK sidecar loading compares the complete manifest for equality",
            "corpus_invalidation": "production create_index/insert_documents explicitly call invalidate_bm25_sidecars before rebuilding; freshness depends on those mutation paths, not automatic corpus hashing",
            "this_evaluation": "no persisted sidecar is read or written; each profile is rebuilt from the pinned full corpus",
        },
        "metrics": {
            "unit": "passage",
            "mrr_at_10": "reciprocal rank of first original positive passage within top 10, else 0",
            "hit_at_5": "query-level indicator that top 5 contains at least one original positive passage",
            "recall_at_5": "number of original positive passages in top 5 divided by that query's positive count",
            "unjudged_policy": "treated as nonrelevant for metrics; not asserted to be exhaustive negatives",
            "bootstrap": {
                "samples": BOOTSTRAP_SAMPLES,
                "seed": BOOTSTRAP_SEED,
                "method": "paired query bootstrap percentile 95% CI for CJK-minus-legacy MRR@10",
            },
        },
        "external_calls": {"embedding": 0, "ocr": 0, "llm": 0, "download": 0},
        "runtime": runtime_versions(),
        "code": repo_state(),
    }


def prepare_manifest() -> dict[str, Any]:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = RUN_ROOT / "manifest.json"
    checksum_path = RUN_ROOT / "manifest.sha256"
    if manifest_path.exists():
        verify_frozen_file(manifest_path, checksum_path)
        manifest = load_json(manifest_path)
        if manifest["code"]["script_sha256"] != sha256_file(SCRIPT_PATH):
            raise RuntimeError("script changed after manifest freeze")
        return manifest
    manifest = build_manifest()
    manifest_sha = write_frozen_json(manifest_path, manifest)
    checksum_path.write_text(f"{manifest_sha}  manifest.json\n", encoding="utf-8")
    return manifest


def load_and_verify_manifest() -> dict[str, Any]:
    manifest_path = RUN_ROOT / "manifest.json"
    verify_frozen_file(manifest_path, RUN_ROOT / "manifest.sha256")
    manifest = load_json(manifest_path)
    if manifest["code"]["script_sha256"] != sha256_file(SCRIPT_PATH):
        raise RuntimeError("script changed after manifest freeze")
    for name, path in SOURCE_FILES.items():
        if sha256_file(path) != manifest["source"]["files"][name]["sha256"]:
            raise RuntimeError(f"source hash changed: {name}")
    if sha256_file(PRIOR_SNAPSHOT) != manifest["query_lineage"]["prior_snapshot_sha256"]:
        raise RuntimeError("prior query snapshot changed")
    return manifest


def tokenize_corpus(texts: Sequence[str], *, cjk: bool) -> Any:
    stemmer = Stemmer.Stemmer("english")
    prepared = (
        [prepare_cjk_bigram_text(text) for text in texts] if cjk else list(texts)
    )
    tokenized = bm25s.tokenize(
        prepared,
        stopwords="en",
        stemmer=stemmer,
        token_pattern=(
            CJK_BIGRAM_TOKEN_PATTERN if cjk else r"(?u)\b\w\w+\b"
        ),
        show_progress=False,
    )
    del prepared
    gc.collect()
    return tokenized


def tokenize_query(text: str, *, cjk: bool) -> list[str]:
    prepared = prepare_cjk_bigram_text(text) if cjk else text
    tokens = bm25s.tokenize(
        prepared,
        stopwords="en",
        stemmer=Stemmer.Stemmer("english"),
        token_pattern=(
            CJK_BIGRAM_TOKEN_PATTERN if cjk else r"(?u)\b\w\w+\b"
        ),
        return_ids=False,
        show_progress=False,
    )
    return list(tokens[0]) if tokens else []


def peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def run_scheme(scheme: str) -> Path:
    if scheme not in SCHEMES:
        raise ValueError(f"unknown scheme: {scheme}")
    manifest = load_and_verify_manifest()
    output_path = RUN_ROOT / f"{scheme}.jsonl"
    audit_path = RUN_ROOT / f"{scheme}_audit.json"
    if output_path.exists():
        rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line]
        if len(rows) != QUERY_COUNT or any(row["scheme"] != scheme for row in rows):
            raise RuntimeError(f"invalid existing scheme output: {output_path}")
        return output_path

    snapshot = load_json(PRIOR_SNAPSHOT)
    passage_ids, corpus_texts = load_full_corpus()
    source_queries, source_qrels = original_query_and_qrels()
    validate_prior_lineage(snapshot, source_queries, source_qrels, set(passage_ids))
    cjk = scheme == "bm25_cjk_bigram_v1"
    started_utc = utc_now()
    started = time.perf_counter()
    tokenized = tokenize_corpus(corpus_texts, cjk=cjk)
    tokenize_seconds = time.perf_counter() - started
    del corpus_texts
    gc.collect()
    index_started = time.perf_counter()
    index = bm25s.BM25()
    index.index(tokenized, show_progress=False)
    index_seconds = time.perf_counter() - index_started
    del tokenized
    gc.collect()

    rows: list[dict[str, Any]] = []
    retrieval_started = time.perf_counter()
    for query in snapshot["queries"]:
        query_id = str(query["query_id"])
        text = str(query["text"])
        relevant = [str(item["passage_id"]) for item in query["positive_qrels"]]
        query_tokens = tokenize_query(text, cjk=cjk)
        if query_tokens:
            scores = index.get_scores(query_tokens)
        else:
            scores = np.zeros(len(passage_ids), dtype=np.float32)
        top = stable_top_positive(passage_ids, scores, limit=TOP_K)
        ranking = [passage_id for passage_id, _ in top]
        rows.append(
            {
                "query_id": query_id,
                "scheme": scheme,
                "relevant_passage_ids": relevant,
                "positive_qrel_scores": {
                    str(item["passage_id"]): int(item["score"])
                    for item in query["positive_qrels"]
                },
                "query_token_count": len(query_tokens),
                "positive_scored_candidate_count": int(np.count_nonzero(scores > 0.0)),
                "ranking": [
                    {"rank": rank, "passage_id": passage_id, "score": score}
                    for rank, (passage_id, score) in enumerate(top, 1)
                ],
                **score_ranking(ranking, relevant),
            }
        )
    retrieval_seconds = time.perf_counter() - retrieval_started
    payload = b"".join(canonical_json_bytes(row) for row in rows)
    temporary = output_path.with_suffix(".jsonl.tmp")
    temporary.write_bytes(payload)
    temporary.replace(output_path)
    audit = {
        "scheme": scheme,
        "started_utc": started_utc,
        "completed_utc": utc_now(),
        "manifest_sha256": sha256_file(RUN_ROOT / "manifest.json"),
        "rows": len(rows),
        "corpus_count": len(passage_ids),
        "tokenize_seconds": tokenize_seconds,
        "index_seconds": index_seconds,
        "retrieval_seconds": retrieval_seconds,
        "peak_rss_bytes": peak_rss_bytes(),
        "raw_results_sha256": sha256_file(output_path),
        "external_calls": 0,
    }
    write_json_atomic(audit_path, audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return output_path


def paired_bootstrap(left: Sequence[float], right: Sequence[float]) -> dict[str, Any]:
    if len(left) != len(right) or len(left) != QUERY_COUNT:
        raise ValueError("paired bootstrap requires the frozen 200-query vectors")
    differences = np.asarray(left, dtype=np.float64) - np.asarray(
        right, dtype=np.float64
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    sampled = rng.choice(
        differences,
        size=(BOOTSTRAP_SAMPLES, len(differences)),
        replace=True,
    ).mean(axis=1)
    return {
        "difference": float(differences.mean()),
        "ci95_low": float(np.percentile(sampled, 2.5)),
        "ci95_high": float(np.percentile(sampled, 97.5)),
        "samples": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
    }


def load_scheme_rows(scheme: str) -> list[dict[str, Any]]:
    path = RUN_ROOT / f"{scheme}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != QUERY_COUNT:
        raise RuntimeError(f"{scheme} row count changed")
    return rows


def aggregate_results() -> dict[str, Any]:
    all_rows = {scheme: load_scheme_rows(scheme) for scheme in SCHEMES}
    query_orders = [[str(row["query_id"]) for row in all_rows[scheme]] for scheme in SCHEMES]
    if query_orders[0] != query_orders[1] or len(set(query_orders[0])) != QUERY_COUNT:
        raise RuntimeError("scheme query order/set mismatch")
    metrics: dict[str, dict[str, Any]] = {}
    for scheme, rows in all_rows.items():
        metrics[scheme] = {
            "mrr_at_10": sum(float(row["reciprocal_rank_at_10"]) for row in rows) / QUERY_COUNT,
            "hit_at_5": sum(float(row["hit_at_5"]) for row in rows) / QUERY_COUNT,
            "hit_at_5_n": sum(int(float(row["hit_at_5"])) for row in rows),
            "hit_at_5_N": QUERY_COUNT,
            "recall_at_5": sum(float(row["recall_at_5"]) for row in rows) / QUERY_COUNT,
        }
    legacy_values = [float(row["reciprocal_rank_at_10"]) for row in all_rows["bm25_legacy"]]
    cjk_values = [float(row["reciprocal_rank_at_10"]) for row in all_rows["bm25_cjk_bigram_v1"]]
    wins = sum(cjk > legacy for cjk, legacy in zip(cjk_values, legacy_values))
    losses = sum(cjk < legacy for cjk, legacy in zip(cjk_values, legacy_values))
    mrr_absolute = metrics["bm25_cjk_bigram_v1"]["mrr_at_10"] - metrics["bm25_legacy"]["mrr_at_10"]
    hit_absolute = metrics["bm25_cjk_bigram_v1"]["hit_at_5"] - metrics["bm25_legacy"]["hit_at_5"]
    comparison = {
        "cjk_minus_legacy": {
            "mrr_at_10_absolute_change": mrr_absolute,
            "mrr_at_10_relative_change": mrr_absolute / metrics["bm25_legacy"]["mrr_at_10"] if metrics["bm25_legacy"]["mrr_at_10"] else None,
            "hit_at_5_absolute_change": hit_absolute,
            "hit_at_5_relative_change": hit_absolute / metrics["bm25_legacy"]["hit_at_5"] if metrics["bm25_legacy"]["hit_at_5"] else None,
            "hit_at_5_n_change": metrics["bm25_cjk_bigram_v1"]["hit_at_5_n"] - metrics["bm25_legacy"]["hit_at_5_n"],
            "query_win_tie_loss": {
                "win": wins,
                "tie": QUERY_COUNT - wins - losses,
                "loss": losses,
            },
            "paired_bootstrap_mrr_difference": paired_bootstrap(cjk_values, legacy_values),
        }
    }
    combined_path = RUN_ROOT / "raw_results.jsonl"
    if not combined_path.exists():
        payload = b"".join(
            canonical_json_bytes(row)
            for scheme in SCHEMES
            for row in all_rows[scheme]
        )
        combined_path.write_bytes(payload)
    else:
        expected = b"".join(
            canonical_json_bytes(row)
            for scheme in SCHEMES
            for row in all_rows[scheme]
        )
        if combined_path.read_bytes() != expected:
            raise RuntimeError("refusing to replace combined frozen raw results")
    summary = {
        "schema_version": 1,
        "task": "RAG-FULL-CORPUS-BM25-VALIDATION",
        "run_id": RUN_ID,
        "completed_utc": utc_now(),
        "query_count": QUERY_COUNT,
        "corpus_count": CORPUS_COUNT,
        "metrics": metrics,
        "comparisons": comparison,
        "raw_results_path": str(combined_path.relative_to(PROJECT_ROOT)),
        "raw_results_sha256": sha256_file(combined_path),
        "scheme_audits": {
            scheme: load_json(RUN_ROOT / f"{scheme}_audit.json")
            for scheme in SCHEMES
        },
        "external_calls": {"embedding": 0, "ocr": 0, "llm": 0, "download": 0},
    }
    write_json_atomic(RUN_ROOT / "summary.json", summary)
    return summary


def run_evaluation() -> dict[str, Any]:
    load_and_verify_manifest()
    for phase in ("scheme-legacy", "scheme-cjk"):
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH), phase],
            cwd=PROJECT_ROOT,
            check=True,
        )
    return aggregate_results()


def validate_run() -> dict[str, Any]:
    manifest = load_and_verify_manifest()
    snapshot = load_json(PRIOR_SNAPSHOT)
    rows_by_scheme = {scheme: load_scheme_rows(scheme) for scheme in SCHEMES}
    checks: list[dict[str, Any]] = []
    expected_query_ids = [str(row["query_id"]) for row in snapshot["queries"]]
    checks.append(
        {
            "check": "same frozen 200 query IDs in both schemes",
            "passed": all(
                [str(row["query_id"]) for row in rows_by_scheme[scheme]]
                == expected_query_ids
                for scheme in SCHEMES
            ),
        }
    )
    recomputed_metrics: dict[str, Any] = defaultdict(
        lambda: defaultdict(float)
    )
    ranking_checks = True
    for scheme, rows in rows_by_scheme.items():
        for query, row in zip(snapshot["queries"], rows):
            ranking = [str(item["passage_id"]) for item in row["ranking"]]
            scores = [float(item["score"]) for item in row["ranking"]]
            relevant = [str(item["passage_id"]) for item in query["positive_qrels"]]
            rescored = score_ranking(ranking, relevant)
            ranking_checks = ranking_checks and len(ranking) <= TOP_K and all(
                score > 0.0 for score in scores
            )
            ranking_checks = ranking_checks and all(
                (-scores[index], stable_id_key(ranking[index]))
                <= (-scores[index + 1], stable_id_key(ranking[index + 1]))
                for index in range(len(ranking) - 1)
            )
            ranking_checks = ranking_checks and all(
                rescored[key] == row[key]
                for key in (
                    "reciprocal_rank_at_10",
                    "hit_at_5",
                    "recall_at_5",
                    "first_relevant_rank",
                )
            )
            for key in ("reciprocal_rank_at_10", "hit_at_5", "recall_at_5"):
                recomputed_metrics[scheme][key] += float(rescored[key]) / QUERY_COUNT
    checks.append(
        {
            "check": "all rankings use positive scores, top20, stable tie order, and direct passage qrels",
            "passed": ranking_checks,
        }
    )
    summary = load_json(RUN_ROOT / "summary.json")
    metrics_match = all(
        math.isclose(
            recomputed_metrics[scheme][key],
            float(summary["metrics"][scheme][key]),
            abs_tol=1e-12,
        )
        for scheme in SCHEMES
        for key in ("mrr_at_10", "hit_at_5", "recall_at_5")
    )
    checks.append(
        {
            "check": "independent aggregation matches summary",
            "passed": metrics_match,
        }
    )
    checks.append(
        {
            "check": "full MTEB-packaged corpus identity and count frozen",
            "passed": manifest["source"]["corpus_count"] == CORPUS_COUNT
            and not manifest["source"]["empty_passage_count"]
            and bool(manifest["source"]["stable_id_and_text_sha256_digest"]),
        }
    )
    checks.append(
        {
            "check": "query relevance distribution and prior pool composition",
            "passed": manifest["query_lineage"]["relevant_passages_per_query_distribution"]
            == {"1": 193, "2": 6, "3": 1}
            and manifest["query_lineage"]["prior_pool"]
            == {
                "candidate_count": 3000,
                "all_positive_passages": 208,
                "random_other_passages": 2792,
            },
        }
    )
    checks.append(
        {
            "check": "zero external-call contract",
            "passed": summary["external_calls"]
            == {"embedding": 0, "ocr": 0, "llm": 0, "download": 0},
        }
    )
    validation = {
        "completed_utc": utc_now(),
        "passed": all(bool(row["passed"]) for row in checks),
        "checks": checks,
    }
    write_json_atomic(RUN_ROOT / "validation.json", validation)
    if not validation["passed"]:
        raise RuntimeError("core validation failed")
    return validation


def self_check() -> dict[str, Any]:
    ranking = stable_top_positive(
        ["10", "2", "3", "alpha"],
        np.asarray([0.4, 0.4, 0.0, 0.4], dtype=np.float32),
        limit=3,
    )
    if [row[0] for row in ranking] != ["2", "10", "alpha"]:
        raise RuntimeError("stable positive ranking self-check failed")
    metric = score_ranking(["x", "positive-a"], {"positive-a", "positive-b"})
    if metric != {
        "reciprocal_rank_at_10": 0.5,
        "hit_at_5": 1.0,
        "recall_at_5": 0.5,
        "first_relevant_rank": 2,
    }:
        raise RuntimeError("metric self-check failed")
    return {
        "passed": True,
        "ranking": [row[0] for row in ranking],
        "metric": metric,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        nargs="?",
        default="all",
        choices=(
            "self-check",
            "prepare",
            "scheme-legacy",
            "scheme-cjk",
            "evaluate",
            "validate",
            "all",
        ),
    )
    args = parser.parse_args()
    if args.phase == "self-check":
        print(json.dumps(self_check(), ensure_ascii=False, indent=2))
        return 0
    if args.phase in {"prepare", "all"}:
        manifest = prepare_manifest()
        print(
            json.dumps(
                {
                    "manifest": str(RUN_ROOT / "manifest.json"),
                    "queries": manifest["query_lineage"]["query_count"],
                    "corpus": manifest["source"]["corpus_count"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.phase == "prepare":
            return 0
    if args.phase == "scheme-legacy":
        run_scheme("bm25_legacy")
        return 0
    if args.phase == "scheme-cjk":
        run_scheme("bm25_cjk_bigram_v1")
        return 0
    if args.phase in {"evaluate", "all"}:
        summary = run_evaluation()
        print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))
        if args.phase == "evaluate":
            return 0
    validation = validate_run()
    print(json.dumps({"validation": validation}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
