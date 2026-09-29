"""Retriever composition for the LlamaIndex RAG pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES

from .config import (
    CJK_BIGRAM_BM25_TOKENIZER_PROFILE,
    HYBRID_PROFILE,
    LEGACY_BM25_TOKENIZER_PROFILE,
    VECTOR_PROFILE,
    RetrievalConfig,
    normalize_bm25_tokenizer_profile,
    retrieval_config_from_env,
)

logger = logging.getLogger(__name__)

BM25_PERSIST_DIRNAME = "bm25_retriever"
BM25_MANIFEST_FILENAME = "deeptutor_bm25_manifest.json"


def _import_bm25_retriever():
    try:
        from llama_index.retrievers.bm25 import BM25Retriever

        return BM25Retriever
    except ImportError:
        return None


def _import_cjk_bm25_components():
    """Load CJK BM25 only when that profile is selected.

    Importing the vector-only path must not require bm25s, PyStemmer, or the
    LlamaIndex BM25 integration.
    """
    try:
        from .bm25_tokenization import (
            CJKBigramBM25Retriever,
            cjk_bigram_tokenizer_manifest,
        )

        return CJKBigramBM25Retriever, cjk_bigram_tokenizer_manifest
    except ImportError:
        return None, None


def bm25_persist_dir(storage_dir: Path, tokenizer_profile: str) -> Path:
    """Return an isolated sidecar path for a versioned tokenizer profile."""
    profile = normalize_bm25_tokenizer_profile(tokenizer_profile)
    if profile == LEGACY_BM25_TOKENIZER_PROFILE:
        return storage_dir / BM25_PERSIST_DIRNAME
    _, manifest_factory = _import_cjk_bm25_components()
    if manifest_factory is None:
        raise RuntimeError("CJK BM25 dependencies are not installed")
    manifest = manifest_factory()
    return (
        storage_dir / f"{BM25_PERSIST_DIRNAME}-{profile}-{manifest['fingerprint'][:12]}"
    )


def _bm25_class(tokenizer_profile: str):
    profile = normalize_bm25_tokenizer_profile(tokenizer_profile)
    if profile == CJK_BIGRAM_BM25_TOKENIZER_PROFILE:
        bm25_cls, _ = _import_cjk_bm25_components()
        return bm25_cls
    return _import_bm25_retriever()


def _profile_manifest(tokenizer_profile: str) -> dict[str, Any] | None:
    profile = normalize_bm25_tokenizer_profile(tokenizer_profile)
    if profile == CJK_BIGRAM_BM25_TOKENIZER_PROFILE:
        _, manifest_factory = _import_cjk_bm25_components()
        return manifest_factory() if manifest_factory is not None else None
    return None


def invalidate_bm25_sidecars(storage_dir: Path) -> int:
    """Remove every BM25 sidecar tied to a mutated storage corpus."""
    if not storage_dir.is_dir():
        return 0
    removed = 0
    for path in storage_dir.iterdir():
        is_sidecar = path.name == BM25_PERSIST_DIRNAME or path.name.startswith(
            f"{BM25_PERSIST_DIRNAME}-"
        )
        if is_sidecar and path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            if not path.exists():
                removed += 1
    return removed


def _manifest_matches(persist_dir: Path, tokenizer_profile: str) -> bool:
    expected = _profile_manifest(tokenizer_profile)
    if expected is None:
        return True
    manifest_path = persist_dir / BM25_MANIFEST_FILENAME
    try:
        actual = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return actual == expected


def _write_profile_manifest(persist_dir: Path, tokenizer_profile: str) -> None:
    manifest = _profile_manifest(tokenizer_profile)
    if manifest is not None:
        (persist_dir / BM25_MANIFEST_FILENAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _set_similarity_top_k(retriever: Any, top_k: int) -> Any:
    if hasattr(retriever, "similarity_top_k"):
        retriever.similarity_top_k = top_k
    return retriever


def _index_node_count(index: Any) -> int | None:
    """Best-effort count of nodes in the index, used to clamp BM25 top_k.

    bm25s raises when the requested ``k`` exceeds the corpus size, so we must
    never ask BM25 for more results than there are nodes (small KBs from a few
    short documents routinely have fewer chunks than the candidate top_k).
    """
    try:
        docs = index.docstore.docs
        return len(docs)
    except Exception:
        return None


def build_bm25_retriever(
    index: Any,
    storage_dir: Path,
    *,
    top_k: int,
    tokenizer_profile: str = LEGACY_BM25_TOKENIZER_PROFILE,
    eligible_node_count: int | None = None,
    eligible_nodes: list[Any] | None = None,
) -> Any | None:
    """Build or load LlamaIndex's official BM25 retriever if available."""
    top_k = max(1, int(top_k))
    node_count = _index_node_count(index)
    if node_count:
        # Clamp to corpus size: bm25s errors out when k > number of nodes.
        top_k = min(top_k, node_count)
    if eligible_nodes is not None:
        eligible_node_count = len(eligible_nodes)
    if eligible_node_count is not None:
        top_k = min(top_k, max(1, int(eligible_node_count)))
    tokenizer_profile = normalize_bm25_tokenizer_profile(tokenizer_profile)
    bm25_cls = _bm25_class(tokenizer_profile)
    if bm25_cls is None:
        logger.info(
            "LlamaIndex BM25 retriever package is not installed; falling back to vector retrieval."
        )
        return None

    # A constrained BM25 retriever must be ephemeral and built only from the
    # exact eligible nodes. LlamaIndex's weight mask can leak excluded nodes on
    # zero-score ties, and persisting it would contaminate later queries.
    if eligible_nodes is not None:
        try:
            return bm25_cls.from_defaults(
                nodes=eligible_nodes,
                similarity_top_k=top_k,
            )
        except Exception as exc:
            logger.warning(
                "Failed to build constrained BM25 retriever; falling back to "
                "filtered vector retrieval: %s",
                exc,
            )
            return None

    persist_dir = bm25_persist_dir(storage_dir, tokenizer_profile)
    if persist_dir.exists() and _manifest_matches(persist_dir, tokenizer_profile):
        try:
            retriever = bm25_cls.from_persist_dir(str(persist_dir))
            return _set_similarity_top_k(retriever, top_k)
        except Exception as exc:
            logger.warning(
                "Failed to load persisted BM25 retriever from %s: %s", persist_dir, exc
            )

    try:
        retriever = bm25_cls.from_defaults(index=index, similarity_top_k=top_k)
        if tokenizer_profile != LEGACY_BM25_TOKENIZER_PROFILE:
            if persist_dir.exists():
                shutil.rmtree(persist_dir, ignore_errors=True)
            persist_dir.mkdir(parents=True, exist_ok=True)
            retriever.persist(str(persist_dir))
            _write_profile_manifest(persist_dir, tokenizer_profile)
        return retriever
    except Exception as exc:
        logger.warning(
            "Failed to build BM25 retriever; falling back to vector retrieval: %s", exc
        )
        return None


def persist_bm25_retriever(
    index: Any,
    storage_dir: Path,
    *,
    top_k: int,
    tokenizer_profile: str = LEGACY_BM25_TOKENIZER_PROFILE,
) -> bool:
    """Persist BM25 sidecar index for faster hybrid retrieval.

    Missing optional dependencies are non-fatal because hybrid retrieval can
    still be enabled in deployments that install ``llama-index-retrievers-bm25``.
    """
    top_k = max(1, int(top_k))
    tokenizer_profile = normalize_bm25_tokenizer_profile(tokenizer_profile)
    bm25_cls = _bm25_class(tokenizer_profile)
    if bm25_cls is None:
        return False

    persist_dir = bm25_persist_dir(storage_dir, tokenizer_profile)
    if persist_dir.exists():
        shutil.rmtree(persist_dir, ignore_errors=True)

    try:
        retriever = bm25_cls.from_defaults(index=index, similarity_top_k=top_k)
    except Exception as exc:
        logger.warning("Failed to build BM25 retriever for persistence: %s", exc)
        return False

    if not hasattr(retriever, "persist"):
        return False

    persist_dir.mkdir(parents=True, exist_ok=True)
    try:
        retriever.persist(str(persist_dir))
        _write_profile_manifest(persist_dir, tokenizer_profile)
        return True
    except Exception as exc:
        logger.warning("Failed to persist BM25 retriever to %s: %s", persist_dir, exc)
        return False


def build_retriever(
    index: Any,
    storage_dir: Path,
    *,
    top_k: int = 5,
    config: RetrievalConfig | None = None,
    filters: Any | None = None,
    eligible_node_count: int | None = None,
    eligible_nodes: list[Any] | None = None,
) -> Any:
    """Compose the retrieval stack from official LlamaIndex retrievers."""
    top_k = max(1, int(top_k))
    if eligible_nodes is not None:
        eligible_node_count = len(eligible_nodes)
    if filters is not None and eligible_node_count is not None:
        top_k = min(top_k, max(1, int(eligible_node_count)))
    vector_kwargs = {"filters": filters} if filters is not None else {}
    retrieval_config = config or retrieval_config_from_env()
    if retrieval_config.profile == VECTOR_PROFILE:
        return index.as_retriever(similarity_top_k=top_k, **vector_kwargs)

    bm25_top_k = retrieval_config.candidate_top_k(
        top_k, retrieval_config.bm25_top_k_multiplier
    )
    bm25_kwargs: dict[str, Any] = {
        "top_k": bm25_top_k,
        "tokenizer_profile": retrieval_config.bm25_tokenizer_profile,
    }
    if filters is not None:
        bm25_kwargs["eligible_node_count"] = eligible_node_count
        bm25_kwargs["eligible_nodes"] = eligible_nodes
    bm25_retriever = build_bm25_retriever(
        index,
        storage_dir,
        **bm25_kwargs,
    )
    if bm25_retriever is None:
        return index.as_retriever(similarity_top_k=top_k, **vector_kwargs)

    if retrieval_config.profile == HYBRID_PROFILE:
        vector_top_k = retrieval_config.candidate_top_k(
            top_k, retrieval_config.vector_top_k_multiplier
        )
        if filters is not None and eligible_node_count is not None:
            vector_top_k = min(vector_top_k, max(1, int(eligible_node_count)))
        vector_retriever = index.as_retriever(
            similarity_top_k=vector_top_k, **vector_kwargs
        )
        return QueryFusionRetriever(
            [vector_retriever, bm25_retriever],
            llm=MockLLM(),
            mode=FUSION_MODES.RECIPROCAL_RANK,
            similarity_top_k=top_k,
            num_queries=retrieval_config.fusion_num_queries,
            use_async=False,
        )

    return index.as_retriever(similarity_top_k=top_k, **vector_kwargs)


__all__ = [
    "BM25_PERSIST_DIRNAME",
    "bm25_persist_dir",
    "build_bm25_retriever",
    "build_retriever",
    "invalidate_bm25_sidecars",
    "persist_bm25_retriever",
]
