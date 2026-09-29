from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from llama_index.core import (
    Document,
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.embeddings.mock_embed_model import MockEmbedding
from llama_index.core.schema import TextNode


def _doc_ids(results) -> list[str]:
    return [str(result.node.metadata.get("doc_id")) for result in results]


def test_cjk_bigram_profile_matches_traditional_text_and_preserves_mixed_tokens() -> (
    None
):
    from deeptutor.services.rag.pipelines.llamaindex.bm25_tokenization import (
        CJKBigramBM25Retriever,
        prepare_cjk_bigram_text,
    )

    prepared = prepare_cjk_bigram_text("HKDSE中文 Paper 2 A級")

    assert prepared.split() == ["hkdse", "中文", "paper", "2", "a", "級"]

    retriever = CJKBigramBM25Retriever.from_defaults(
        nodes=[
            TextNode(
                text="子墨子以道義勸楚王停止攻宋，並以守城演練說服公輸盤。",
                metadata={"doc_id": "relevant"},
            ),
            TextNode(
                text="中國語文課程包含閱讀、寫作、聆聽及說話學習範疇。",
                metadata={"doc_id": "other"},
            ),
        ],
        similarity_top_k=2,
    )

    assert (
        _doc_ids(retriever.retrieve("墨子如何以攻城演練勸楚王放棄攻宋？"))[0]
        == "relevant"
    )


def test_adapted_sidecar_is_isolated_and_loads_the_same_ranking(tmp_path: Path) -> None:
    from deeptutor.services.rag.pipelines.llamaindex.config import (
        CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
        LEGACY_BM25_TOKENIZER_PROFILE,
    )
    from deeptutor.services.rag.pipelines.llamaindex.retrievers import (
        bm25_persist_dir,
        build_bm25_retriever,
        persist_bm25_retriever,
    )

    Settings.embed_model = MockEmbedding(embed_dim=4)
    index = VectorStoreIndex.from_documents(
        [
            Document(text="蠟梅在霜雪中綻放並散發幽香", metadata={"doc_id": "wax"}),
            Document(text="課程評核與寫作要求", metadata={"doc_id": "curriculum"}),
        ]
    )

    assert persist_bm25_retriever(
        index,
        tmp_path,
        top_k=2,
        tokenizer_profile=LEGACY_BM25_TOKENIZER_PROFILE,
    )
    legacy_dir = bm25_persist_dir(tmp_path, LEGACY_BM25_TOKENIZER_PROFILE)
    adapted_dir = bm25_persist_dir(tmp_path, CJK_BIGRAM_BM25_TOKENIZER_PROFILE)
    assert legacy_dir != adapted_dir
    assert legacy_dir.is_dir()
    assert not adapted_dir.exists()

    first = build_bm25_retriever(
        index,
        tmp_path,
        top_k=2,
        tokenizer_profile=CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
    )
    first_ranking = _doc_ids(first.retrieve("霜雪中的蠟梅有甚麼幽香？"))
    assert adapted_dir.is_dir()
    assert (adapted_dir / "deeptutor_bm25_manifest.json").is_file()

    loaded = build_bm25_retriever(
        index,
        tmp_path,
        top_k=2,
        tokenizer_profile=CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
    )
    assert _doc_ids(loaded.retrieve("霜雪中的蠟梅有甚麼幽香？")) == first_ranking
    assert first_ranking[0] == "wax"


def test_cjk_profile_is_opt_in_and_unknown_values_fall_back_to_legacy(
    monkeypatch,
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import config

    monkeypatch.delenv("DEEPTUTOR_RAG_BM25_TOKENIZER_PROFILE", raising=False)
    assert config.retrieval_config_from_env().bm25_tokenizer_profile == "legacy"

    monkeypatch.setenv("DEEPTUTOR_RAG_BM25_TOKENIZER_PROFILE", " cjk_bigram_v1 ")
    assert config.retrieval_config_from_env().bm25_tokenizer_profile == "cjk_bigram_v1"

    monkeypatch.setenv("DEEPTUTOR_RAG_BM25_TOKENIZER_PROFILE", "unknown")
    assert config.retrieval_config_from_env().bm25_tokenizer_profile == "legacy"


def test_production_retriever_path_forwards_the_cjk_profile(
    tmp_path: Path, monkeypatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import retrievers
    from deeptutor.services.rag.pipelines.llamaindex.config import RetrievalConfig

    observed: dict[str, str] = {}

    def _capture(index, storage_dir, *, top_k, tokenizer_profile):
        observed["profile"] = tokenizer_profile
        return None

    class _Index:
        def as_retriever(self, *, similarity_top_k):
            return ("vector", similarity_top_k)

    monkeypatch.setattr(retrievers, "build_bm25_retriever", _capture)

    fallback = retrievers.build_retriever(
        _Index(),
        tmp_path,
        top_k=5,
        config=RetrievalConfig(bm25_tokenizer_profile="cjk_bigram_v1"),
    )

    assert observed == {"profile": "cjk_bigram_v1"}
    assert fallback == ("vector", 5)


def test_incremental_insert_invalidates_cjk_sidecar_before_next_query(
    tmp_path: Path,
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage
    from deeptutor.services.rag.pipelines.llamaindex.config import (
        CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
    )
    from deeptutor.services.rag.pipelines.llamaindex.retrievers import (
        build_bm25_retriever,
    )

    Settings.embed_model = MockEmbedding(embed_dim=4)
    Settings.chunk_size = 64
    Settings.chunk_overlap = 8
    storage.create_index(
        [Document(text="原有課程內容", metadata={"doc_id": "old"})],
        tmp_path,
        show_progress=False,
    )
    initial_index = load_index_from_storage(
        StorageContext.from_defaults(persist_dir=str(tmp_path))
    )
    initial = build_bm25_retriever(
        initial_index,
        tmp_path,
        top_k=2,
        tokenizer_profile=CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
    )
    assert initial is not None
    assert _doc_ids(initial.retrieve("新增獨有詞彙")) == ["old"]

    storage.insert_documents(
        tmp_path,
        tmp_path,
        [Document(text="新增獨有詞彙只在此文件", metadata={"doc_id": "new"})],
    )

    updated_index = load_index_from_storage(
        StorageContext.from_defaults(persist_dir=str(tmp_path))
    )
    updated = build_bm25_retriever(
        updated_index,
        tmp_path,
        top_k=2,
        tokenizer_profile=CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
    )
    assert updated is not None
    assert _doc_ids(updated.retrieve("新增獨有詞彙"))[0] == "new"


def test_vector_profile_import_does_not_require_optional_bm25_dependencies() -> None:
    script = """
import sys

class BlockBM25Imports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"bm25s", "Stemmer"} or fullname.startswith(
            "llama_index.retrievers.bm25"
        ):
            raise ImportError(f"blocked optional dependency: {fullname}")
        return None

sys.meta_path.insert(0, BlockBM25Imports())

from deeptutor.services.rag.pipelines.llamaindex.config import RetrievalConfig
from deeptutor.services.rag.pipelines.llamaindex import retrievers

class Index:
    def as_retriever(self, *, similarity_top_k):
        return ("vector", similarity_top_k)

assert retrievers.build_retriever(
    Index(),
    __import__("pathlib").Path("."),
    top_k=3,
    config=RetrievalConfig(profile="vector"),
) == ("vector", 3)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
