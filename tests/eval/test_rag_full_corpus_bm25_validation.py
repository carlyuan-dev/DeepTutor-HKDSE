from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import rag_full_corpus_bm25_validation as validation


def test_stable_top_positive_filters_nonpositive_and_breaks_score_ties_by_id() -> None:
    passage_ids = ["10", "2", "30", "4", "alpha"]
    scores = np.asarray([0.4, 0.4, 0.0, -0.1, 0.4], dtype=np.float32)

    ranking = validation.stable_top_positive(passage_ids, scores, limit=3)

    assert ranking == [("2", float(scores[1])), ("10", float(scores[0])), ("alpha", float(scores[4]))]


def test_score_ranking_uses_passage_qrels_for_mrr_hit_and_recall() -> None:
    scored = validation.score_ranking(["x", "positive-a", "z"], {"positive-a", "positive-b"})

    assert math.isclose(scored["reciprocal_rank_at_10"], 0.5)
    assert scored["hit_at_5"] == 1.0
    assert scored["recall_at_5"] == 0.5
    assert scored["first_relevant_rank"] == 2


def test_load_parquet_rows_accepts_tuple_columns(tmp_path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    source = tmp_path / "queries.parquet"
    pq.write_table(pa.Table.from_pylist([
        {"_id": "q1", "text": "代數練習", "unused": "ignored"},
        {"_id": "q2", "text": "閱讀理解", "unused": "ignored"},
    ]), source)
    rows = validation.load_parquet_rows(source, columns=("_id", "text"))
    assert rows == [
        {"_id": "q1", "text": "代數練習"},
        {"_id": "q2", "text": "閱讀理解"},
    ]
