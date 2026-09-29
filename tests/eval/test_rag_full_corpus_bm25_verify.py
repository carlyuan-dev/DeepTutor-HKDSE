from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import rag_full_corpus_bm25_verify as verify


def test_aggregate_scheme_rows_maps_reciprocal_rank_to_mrr() -> None:
    rows = [
        {
            "reciprocal_rank_at_10": 1.0,
            "hit_at_5": 1.0,
            "recall_at_5": 0.5,
        },
        {
            "reciprocal_rank_at_10": 0.0,
            "hit_at_5": 0.0,
            "recall_at_5": 0.0,
        },
    ]

    assert verify.aggregate_scheme_rows(rows) == {
        "mrr_at_10": 0.5,
        "hit_at_5": 0.5,
        "recall_at_5": 0.25,
        "hit_at_5_n": 1,
        "hit_at_5_N": 2,
    }
