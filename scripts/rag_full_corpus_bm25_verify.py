#!/usr/bin/env python3
"""Independently verify frozen full-corpus BM25 evaluation artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = (
    PROJECT_ROOT
    / "data"
    / "evaluations"
    / "rag_full_corpus_bm25_validation"
    / "runs"
    / "mmarco_zh_dev_200_full_106813"
)
SNAPSHOT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evaluations"
    / "rag_public_holdout_final"
    / "runs"
    / "mmarco_zh_dev_200_seed20260911"
    / "selected_snapshot.json"
)
SCHEMES = ("bm25_legacy", "bm25_cjk_bigram_v1")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id_key(value: str) -> tuple[int, int | str, str]:
    text = str(value)
    return (0, int(text), text) if text.isdecimal() else (1, text, text)


def aggregate_scheme_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    if not count:
        raise ValueError("rows must not be empty")
    hit_n = sum(int(float(row["hit_at_5"])) for row in rows)
    return {
        "mrr_at_10": sum(float(row["reciprocal_rank_at_10"]) for row in rows) / count,
        "hit_at_5": hit_n / count,
        "recall_at_5": sum(float(row["recall_at_5"]) for row in rows) / count,
        "hit_at_5_n": hit_n,
        "hit_at_5_N": count,
    }


def score_ranking(ranking: Sequence[str], relevant: set[str]) -> dict[str, Any]:
    first = next(
        (
            rank
            for rank, passage_id in enumerate(ranking[:10], 1)
            if passage_id in relevant
        ),
        None,
    )
    found = relevant.intersection(ranking[:5])
    return {
        "reciprocal_rank_at_10": 0.0 if first is None else 1.0 / first,
        "hit_at_5": float(bool(found)),
        "recall_at_5": len(found) / len(relevant),
        "first_relevant_rank": first,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def verify() -> dict[str, Any]:
    manifest_path = RUN_ROOT / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    expected_manifest_sha = (
        RUN_ROOT / "manifest.sha256"
    ).read_text(encoding="utf-8").split()[0]
    manifest = load_json(manifest_path)
    summary = load_json(RUN_ROOT / "summary.json")
    snapshot = load_json(SNAPSHOT_PATH)
    query_by_id = {str(row["query_id"]): row for row in snapshot["queries"]}

    checks: list[dict[str, Any]] = [
        {
            "check": "manifest checksum",
            "passed": manifest_sha == expected_manifest_sha,
        },
        {
            "check": "full-corpus scope and frozen query lineage",
            "passed": manifest["source"]["corpus_count"] == 106813
            and manifest["query_lineage"]["query_count"] == 200
            and manifest["query_lineage"]["prior_snapshot_sha256"]
            == sha256_file(SNAPSHOT_PATH),
        },
    ]

    rows_by_scheme: dict[str, list[dict[str, Any]]] = {}
    ranking_valid = True
    direct_qrels_valid = True
    metric_valid = True
    for scheme in SCHEMES:
        path = RUN_ROOT / f"{scheme}.jsonl"
        rows = load_jsonl(path)
        rows_by_scheme[scheme] = rows
        if len(rows) != 200 or any(row["scheme"] != scheme for row in rows):
            ranking_valid = False
            continue
        for row in rows:
            query = query_by_id.get(str(row["query_id"]))
            if query is None:
                direct_qrels_valid = False
                continue
            expected_relevant = {
                str(item["passage_id"]) for item in query["positive_qrels"]
            }
            if set(row["relevant_passage_ids"]) != expected_relevant:
                direct_qrels_valid = False
            ranking = [str(item["passage_id"]) for item in row["ranking"]]
            scores = [float(item["score"]) for item in row["ranking"]]
            if len(ranking) > 20 or any(score <= 0.0 for score in scores):
                ranking_valid = False
            for index in range(len(ranking) - 1):
                left = (-scores[index], stable_id_key(ranking[index]))
                right = (-scores[index + 1], stable_id_key(ranking[index + 1]))
                if left > right:
                    ranking_valid = False
            rescored = score_ranking(ranking, expected_relevant)
            if any(
                rescored[key] != row[key]
                for key in (
                    "reciprocal_rank_at_10",
                    "hit_at_5",
                    "recall_at_5",
                    "first_relevant_rank",
                )
            ):
                metric_valid = False
    checks.extend(
        [
            {
                "check": "400 query-scheme rows, positive-score top20, stable ties",
                "passed": ranking_valid,
            },
            {
                "check": "raw rows retain the original frozen passage qrels",
                "passed": direct_qrels_valid,
            },
            {
                "check": "MRR@10, Hit@5 and Recall@5 recompute per query",
                "passed": metric_valid,
            },
        ]
    )

    recomputed = {
        scheme: aggregate_scheme_rows(rows_by_scheme[scheme]) for scheme in SCHEMES
    }
    aggregate_match = all(
        math.isclose(
            float(recomputed[scheme][key]),
            float(summary["metrics"][scheme][key]),
            abs_tol=1e-12,
        )
        for scheme in SCHEMES
        for key in (
            "mrr_at_10",
            "hit_at_5",
            "recall_at_5",
            "hit_at_5_n",
            "hit_at_5_N",
        )
    )
    legacy = {
        str(row["query_id"]): float(row["reciprocal_rank_at_10"])
        for row in rows_by_scheme["bm25_legacy"]
    }
    cjk = {
        str(row["query_id"]): float(row["reciprocal_rank_at_10"])
        for row in rows_by_scheme["bm25_cjk_bigram_v1"]
    }
    query_ids = list(query_by_id)
    wins = sum(cjk[query_id] > legacy[query_id] for query_id in query_ids)
    losses = sum(cjk[query_id] < legacy[query_id] for query_id in query_ids)
    expected_wtl = summary["comparisons"]["cjk_minus_legacy"][
        "query_win_tie_loss"
    ]
    checks.append(
        {
            "check": "independent aggregates and query win/tie/loss match summary",
            "passed": aggregate_match
            and expected_wtl
            == {"win": wins, "tie": 200 - wins - losses, "loss": losses},
        }
    )
    combined_rows = load_jsonl(RUN_ROOT / "raw_results.jsonl")
    checks.append(
        {
            "check": "combined raw result count/hash and zero-external-call contract",
            "passed": len(combined_rows) == 400
            and sha256_file(RUN_ROOT / "raw_results.jsonl")
            == summary["raw_results_sha256"]
            and summary["external_calls"]
            == {"embedding": 0, "ocr": 0, "llm": 0, "download": 0},
        }
    )

    result = {
        "schema_version": 1,
        "task": "RAG-FULL-CORPUS-BM25-VALIDATION",
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "recomputed_metrics": recomputed,
        "recomputed_query_win_tie_loss": {
            "win": wins,
            "tie": 200 - wins - losses,
            "loss": losses,
        },
        "verifier_script_sha256": sha256_file(Path(__file__).resolve()),
        "in_run_validator_note": "The frozen runner's validation.json is false because its aggregation check stores reciprocal_rank_at_10 but reads mrr_at_10; rankings and summary are not changed. This independent verifier uses an explicit field mapping.",
        "external_calls": 0,
    }
    output = RUN_ROOT / "independent_validation.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    if not result["passed"]:
        raise RuntimeError("independent verification failed")
    return result


def main() -> int:
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
