from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import rag_full_corpus_hybrid_ablation as ablation


def test_stable_top_scores_breaks_equal_dense_scores_by_numeric_id() -> None:
    passage_ids = ["10", "2", "30", "4"]
    scores = np.asarray([0.4, 0.4, 0.1, 0.2], dtype=np.float32)

    ranking = ablation.stable_top_scores(passage_ids, scores, limit=3)

    assert [item[0] for item in ranking] == ["2", "10", "4"]


def test_rrf_keeps_branch_union_coverage_separate_from_fused_top_k() -> None:
    dense = [("1", 0.9), ("2", 0.8), ("3", 0.7)]
    bm25 = [("4", 3.0), ("5", 2.0), ("6", 1.0)]

    fused, audit = ablation.rrf_rank(dense, bm25, limit=3, rrf_k=60)

    assert audit["union_size"] == 6
    assert audit["union_passage_ids"] == ["1", "2", "3", "4", "5", "6"]
    assert len(fused) == 3
    assert {item[0] for item in fused} < set(audit["union_passage_ids"])


def test_score_ranking_maps_all_requested_cutoffs_without_mrr_key_alias() -> None:
    ranking = [f"p{index}" for index in range(1, 51)]
    relevant = {"p3", "p25", "p50", "missing"}

    scored = ablation.score_ranking(ranking, relevant)

    assert math.isclose(scored["reciprocal_rank_at_10"], 1.0 / 3.0)
    assert scored["hit_at_5"] == 1.0
    assert scored["hit_at_20"] == 1.0
    assert scored["recall_at_20"] == 0.25
    assert scored["hit_at_50"] == 1.0
    assert scored["recall_at_50"] == 0.75
