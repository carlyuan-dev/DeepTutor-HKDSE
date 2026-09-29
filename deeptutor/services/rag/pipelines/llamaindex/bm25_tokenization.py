"""Versioned BM25 tokenization for mixed Chinese and Latin text."""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
from importlib import metadata as importlib_metadata
import json
import re
from typing import Any

import bm25s
import Stemmer
from llama_index.core.schema import BaseNode, MetadataMode, QueryBundle
from llama_index.core.vector_stores.utils import node_to_metadata_dict
from llama_index.retrievers.bm25 import BM25Retriever


CJK_BIGRAM_TOKENIZER_VERSION = "cjk_bigram_v1"
CJK_BIGRAM_TOKEN_PATTERN = r"(?u)\b\w+\b"
_CJK_RUN = r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+"
_LATIN_WORD = r"[A-Za-z]+(?:['’-][A-Za-z]+)*"
_NUMBER = r"\d+(?:\.\d+)?%?"
_MIXED_TOKEN_RE = re.compile(f"{_CJK_RUN}|{_LATIN_WORD}|{_NUMBER}")


def prepare_cjk_bigram_text(text: str) -> str:
    """Return a space-delimited retrieval representation for mixed text.

    Chinese runs become overlapping character bigrams (or a unigram for a
    one-character run). Latin words and numeric expressions remain intact;
    BM25Retriever applies its normal English stemming afterwards.
    """
    tokens: list[str] = []
    for match in _MIXED_TOKEN_RE.finditer(str(text or "")):
        value = match.group(0)
        if re.fullmatch(_CJK_RUN, value):
            if len(value) == 1:
                tokens.append(value)
            else:
                tokens.extend(
                    value[index : index + 2] for index in range(len(value) - 1)
                )
        else:
            tokens.append(value.lower())
    return " ".join(tokens)


def cjk_bigram_tokenizer_manifest() -> dict[str, Any]:
    """Return the stable spec and runtime versions used by the sidecar."""
    spec = {
        "profile": CJK_BIGRAM_TOKENIZER_VERSION,
        "algorithm": "overlapping_cjk_character_bigrams",
        "cjk_ranges": "U+3400-4DBF,U+4E00-9FFF,U+F900-FAFF",
        "latin": "lowercase_whole_words_then_english_stemming",
        "numbers": "whole_numeric_expression",
        "token_pattern": CJK_BIGRAM_TOKEN_PATTERN,
        "traditional_simplified_normalization": False,
    }
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True)
    try:
        bm25s_version = importlib_metadata.version("bm25s")
    except importlib_metadata.PackageNotFoundError:
        bm25s_version = "unknown"
    try:
        stemmer_version = importlib_metadata.version("PyStemmer")
    except importlib_metadata.PackageNotFoundError:
        stemmer_version = "unknown"
    return {
        **spec,
        "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "runtime": {"bm25s": bm25s_version, "PyStemmer": stemmer_version},
    }


class CJKBigramBM25Retriever(BM25Retriever):
    """BM25Retriever with identical index/query CJK bigram preparation."""

    def __init__(
        self,
        *,
        nodes: Sequence[BaseNode] | None = None,
        existing_bm25: bm25s.BM25 | None = None,
        stemmer: Any | None = None,
        language: str = "en",
        similarity_top_k: int = 2,
        verbose: bool = False,
        skip_stemming: bool = False,
        token_pattern: str = CJK_BIGRAM_TOKEN_PATTERN,
        filters: Any | None = None,
        corpus_weight_mask: list[int] | None = None,
        **kwargs: Any,
    ) -> None:
        active_stemmer = stemmer or Stemmer.Stemmer("english")
        if existing_bm25 is None:
            if nodes is None:
                raise ValueError(
                    "nodes are required when no persisted BM25 index is supplied"
                )
            corpus = [
                node_to_metadata_dict(node) | {"node_id": node.node_id}
                for node in nodes
            ]
            prepared = [
                prepare_cjk_bigram_text(
                    node.get_content(metadata_mode=MetadataMode.EMBED)
                )
                for node in nodes
            ]
            corpus_tokens = bm25s.tokenize(
                prepared,
                stopwords=language,
                stemmer=active_stemmer if not skip_stemming else None,
                token_pattern=token_pattern,
                show_progress=verbose,
            )
            existing_bm25 = bm25s.BM25()
            existing_bm25.index(corpus_tokens, show_progress=verbose)
            existing_bm25.corpus = corpus

        super().__init__(
            existing_bm25=existing_bm25,
            stemmer=active_stemmer,
            similarity_top_k=similarity_top_k,
            verbose=verbose,
            skip_stemming=skip_stemming,
            token_pattern=token_pattern,
            filters=filters,
            corpus_weight_mask=corpus_weight_mask,
            **kwargs,
        )

    @classmethod
    def from_defaults(
        cls,
        *,
        index: Any | None = None,
        nodes: Sequence[BaseNode] | None = None,
        docstore: Any | None = None,
        **kwargs: Any,
    ) -> "CJKBigramBM25Retriever":
        if sum(value is not None for value in (index, nodes, docstore)) != 1:
            raise ValueError("Please pass exactly one of index, nodes, or docstore.")
        if index is not None:
            docstore = index.docstore
        if docstore is not None:
            nodes = list(docstore.docs.values())
        return cls(nodes=nodes, **kwargs)

    def _retrieve(self, query_bundle: QueryBundle):
        prepared = QueryBundle(
            query_str=prepare_cjk_bigram_text(query_bundle.query_str)
        )
        return super()._retrieve(prepared)


__all__ = [
    "CJKBigramBM25Retriever",
    "CJK_BIGRAM_TOKENIZER_VERSION",
    "cjk_bigram_tokenizer_manifest",
    "prepare_cjk_bigram_text",
]
