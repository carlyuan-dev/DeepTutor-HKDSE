from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def test_constraint_normalization_accepts_only_exact_supported_values() -> None:
    from deeptutor.services.rag.metadata_constraints import normalize_metadata_constraints

    accepted = normalize_metadata_constraints(
        {"subject": "english", "genre": "narrative"}
    )
    wrong_value = normalize_metadata_constraints({"genre": "history"})
    substring_value = normalize_metadata_constraints({"genre": "narrative essay"})
    non_string_value = normalize_metadata_constraints({"genre": ["narrative"]})
    wrong_key = normalize_metadata_constraints({"passage_type": "narrative"})

    assert accepted.status == "eligible"
    assert accepted.constraints == {"genre": "narrative", "subject": "english"}
    assert wrong_value.status == "not_applied"
    assert wrong_value.reason == "unsupported_value:genre"
    assert wrong_value.constraints == {}
    assert substring_value.reason == "unsupported_value:genre"
    assert substring_value.constraints == {}
    assert non_string_value.reason == "unsupported_value:genre"
    assert non_string_value.constraints == {}
    assert wrong_key.status == "not_applied"
    assert wrong_key.reason == "unsupported_key:passage_type"
    assert wrong_key.constraints == {}


def _fake_index(metadata_rows: list[dict[str, str]]):
    docs = {
        f"node-{index}": SimpleNamespace(metadata=metadata)
        for index, metadata in enumerate(metadata_rows, start=1)
    }
    return SimpleNamespace(
        docstore=SimpleNamespace(docs=docs),
        vector_store=SimpleNamespace(data=SimpleNamespace(embedding_dict={})),
        storage_context=SimpleNamespace(vector_stores={}),
    )


def test_constrained_storage_uses_exact_filters_when_metadata_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage

    index = _fake_index(
        [
            {"subject": "english", "genre": "narrative"},
            {"subject": "english", "genre": "narrative"},
            {"subject": "english", "genre": "argumentative"},
        ]
    )
    captured: dict[str, object] = {}

    filtered_node = SimpleNamespace(
        node=SimpleNamespace(metadata={"subject": "english", "genre": "narrative"})
    )

    class Retriever:
        def retrieve(self, query: str):
            captured["query"] = query
            return [filtered_node]

    def build_retriever(_index, _storage_dir, **kwargs):
        captured.update(kwargs)
        return Retriever()

    monkeypatch.setattr(storage.StorageContext, "from_defaults", lambda persist_dir: object())
    monkeypatch.setattr(storage, "load_index_from_storage", lambda _ctx: index)
    monkeypatch.setattr(storage.retrievers, "build_retriever", build_retriever)

    nodes, outcome = storage.retrieve_nodes_with_constraints(
        tmp_path,
        "travel problem",
        top_k=5,
        constraints={"subject": "english", "genre": "narrative"},
    )

    assert nodes == [filtered_node]
    assert outcome == {
        "status": "applied",
        "reason": "matching_metadata",
        "constraints": {"genre": "narrative", "subject": "english"},
        "eligible_node_count": 2,
    }
    assert captured["eligible_node_count"] == 2
    filters = captured["filters"]
    assert [(flt.key, flt.value) for flt in filters.filters] == [
        ("genre", "narrative"),
        ("subject", "english"),
    ]


def test_constrained_storage_falls_back_when_old_index_has_no_matching_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage

    index = _fake_index([{"file_name": "old.pdf"}])
    calls: list[dict[str, object]] = []

    class Retriever:
        def retrieve(self, query: str):
            return ["unfiltered-node"]

    def build_retriever(_index, _storage_dir, **kwargs):
        calls.append(kwargs)
        return Retriever()

    monkeypatch.setattr(storage.StorageContext, "from_defaults", lambda persist_dir: object())
    monkeypatch.setattr(storage, "load_index_from_storage", lambda _ctx: index)
    monkeypatch.setattr(storage.retrievers, "build_retriever", build_retriever)

    nodes, outcome = storage.retrieve_nodes_with_constraints(
        tmp_path,
        "reading",
        constraints={"language_form": "vernacular"},
    )

    assert nodes == ["unfiltered-node"]
    assert calls == [{"top_k": 5}]
    assert outcome == {
        "status": "fallback",
        "reason": "no_matching_metadata",
        "constraints": {"language_form": "vernacular"},
        "eligible_node_count": 0,
    }


def test_constrained_storage_falls_back_after_filter_execution_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage

    index = _fake_index([{"genre": "narrative"}])
    calls = 0

    class Retriever:
        def __init__(self, *, fail: bool) -> None:
            self.fail = fail

        def retrieve(self, query: str):
            if self.fail:
                raise TypeError("backend filter unsupported")
            return ["unfiltered-node"]

    def build_retriever(_index, _storage_dir, **kwargs):
        nonlocal calls
        calls += 1
        return Retriever(fail="filters" in kwargs)

    monkeypatch.setattr(storage.StorageContext, "from_defaults", lambda persist_dir: object())
    monkeypatch.setattr(storage, "load_index_from_storage", lambda _ctx: index)
    monkeypatch.setattr(storage.retrievers, "build_retriever", build_retriever)

    nodes, outcome = storage.retrieve_nodes_with_constraints(
        tmp_path,
        "reading",
        constraints={"genre": "narrative"},
    )

    assert nodes == ["unfiltered-node"]
    assert calls == 2
    assert outcome == {
        "status": "fallback",
        "reason": "filter_error:TypeError",
        "constraints": {"genre": "narrative"},
        "eligible_node_count": 1,
    }


def test_constrained_storage_falls_back_after_empty_filtered_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage

    index = _fake_index([{"genre": "narrative"}])
    calls: list[dict[str, object]] = []

    class Retriever:
        def __init__(self, *, filtered: bool) -> None:
            self.filtered = filtered

        def retrieve(self, query: str):
            return [] if self.filtered else ["unfiltered-node"]

    def build_retriever(_index, _storage_dir, **kwargs):
        calls.append(kwargs)
        return Retriever(filtered="filters" in kwargs)

    monkeypatch.setattr(storage.StorageContext, "from_defaults", lambda persist_dir: object())
    monkeypatch.setattr(storage, "load_index_from_storage", lambda _ctx: index)
    monkeypatch.setattr(storage.retrievers, "build_retriever", build_retriever)

    nodes, outcome = storage.retrieve_nodes_with_constraints(
        tmp_path,
        "reading",
        constraints={"genre": "narrative"},
    )

    assert nodes == ["unfiltered-node"]
    assert len(calls) == 2
    assert outcome == {
        "status": "fallback",
        "reason": "empty_filtered_result",
        "constraints": {"genre": "narrative"},
        "eligible_node_count": 1,
    }


def test_constrained_storage_removes_backend_filter_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage

    index = _fake_index([{"genre": "narrative"}, {"genre": "argumentative"}])
    eligible = SimpleNamespace(
        node=SimpleNamespace(metadata={"genre": "narrative"}), score=0.0
    )
    leaked = SimpleNamespace(
        node=SimpleNamespace(metadata={"genre": "argumentative"}), score=0.0
    )

    class Retriever:
        def retrieve(self, query: str):
            return [leaked, eligible]

    monkeypatch.setattr(storage.StorageContext, "from_defaults", lambda persist_dir: object())
    monkeypatch.setattr(storage, "load_index_from_storage", lambda _ctx: index)
    monkeypatch.setattr(
        storage.retrievers, "build_retriever", lambda *_args, **_kwargs: Retriever()
    )

    nodes, outcome = storage.retrieve_nodes_with_constraints(
        tmp_path, "missing terms", constraints={"genre": "narrative"}
    )

    assert nodes == [eligible]
    assert outcome["status"] == "applied"


def test_filtered_bm25_uses_only_eligible_nodes_and_never_shared_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import retrievers

    captured: dict[str, object] = {}
    eligible_nodes = [SimpleNamespace(node_id="eligible")]

    class FakeBM25:
        @classmethod
        def from_persist_dir(cls, *_args, **_kwargs):
            raise AssertionError("filtered retrieval must not load a shared sidecar")

        @classmethod
        def from_defaults(cls, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(similarity_top_k=kwargs["similarity_top_k"])

    monkeypatch.setattr(retrievers, "_bm25_class", lambda _profile: FakeBM25)
    retrievers.bm25_persist_dir(tmp_path, "legacy").mkdir()

    retriever = retrievers.build_bm25_retriever(
        SimpleNamespace(docstore=SimpleNamespace(docs={})),
        tmp_path,
        top_k=5,
        eligible_nodes=eligible_nodes,
    )

    assert retriever is not None
    assert captured == {"nodes": eligible_nodes, "similarity_top_k": 1}


def test_real_cjk_bm25_constraints_are_request_scoped_and_cache_is_reused(
    tmp_path: Path,
) -> None:
    from llama_index.core.schema import TextNode

    from deeptutor.services.rag.pipelines.llamaindex import retrievers

    narrative = TextNode(
        text="校園旅行見聞",
        metadata={"subject": "chinese", "genre": "narrative"},
    )
    argumentative = TextNode(
        text="學生應否使用手機辯論",
        metadata={"subject": "chinese", "genre": "argumentative"},
    )
    index = SimpleNamespace(
        docstore=SimpleNamespace(
            docs={narrative.node_id: narrative, argumentative.node_id: argumentative}
        )
    )
    profile = "cjk_bigram_v1"

    assert retrievers.persist_bm25_retriever(
        index, tmp_path, top_k=2, tokenizer_profile=profile
    )
    sidecar = retrievers.bm25_persist_dir(tmp_path, profile)
    before = {
        path.relative_to(sidecar): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sidecar.rglob("*")
        if path.is_file()
    }

    filtered_narrative = retrievers.build_bm25_retriever(
        index,
        tmp_path,
        top_k=1,
        tokenizer_profile=profile,
        eligible_nodes=[narrative],
    )
    narrative_results = filtered_narrative.retrieve("手機")
    assert narrative_results
    assert all(item.node.metadata["genre"] == "narrative" for item in narrative_results)

    cached_unfiltered = retrievers.build_bm25_retriever(
        index, tmp_path, top_k=1, tokenizer_profile=profile
    )
    unfiltered_results = cached_unfiltered.retrieve("手機")
    assert unfiltered_results[0].node.metadata["genre"] == "argumentative"

    filtered_argumentative = retrievers.build_bm25_retriever(
        index,
        tmp_path,
        top_k=1,
        tokenizer_profile=profile,
        eligible_nodes=[argumentative],
    )
    argumentative_results = filtered_argumentative.retrieve("旅行")
    assert argumentative_results
    assert all(
        item.node.metadata["genre"] == "argumentative"
        for item in argumentative_results
    )

    after = {
        path.relative_to(sidecar): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sidecar.rglob("*")
        if path.is_file()
    }
    assert after == before


@pytest.mark.asyncio
async def test_pipeline_reports_invalid_constraint_without_filtering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage
    from deeptutor.services.rag.pipelines.llamaindex.pipeline import LlamaIndexPipeline

    storage_dir = tmp_path / "kb" / "version-1"
    storage_dir.mkdir(parents=True)
    (storage_dir / "docstore.json").write_text("{}", encoding="utf-8")
    node = SimpleNamespace(
        node=SimpleNamespace(
            text="fallback context",
            metadata={"file_name": "old.pdf"},
            node_id="node-1",
        ),
        score=0.5,
    )
    monkeypatch.setattr(LlamaIndexPipeline, "_configure_settings", lambda self: None)
    monkeypatch.setattr(storage, "retrieve_nodes", lambda *_args, **_kwargs: [node])

    pipeline = LlamaIndexPipeline(
        kb_base_dir=str(tmp_path), signature_provider=lambda: None
    )
    result = await pipeline.search(
        "history reading", "kb", metadata_constraints={"genre": "history"}
    )

    assert result["content"] == "fallback context"
    assert result["metadata_constraint"] == {
        "status": "not_applied",
        "reason": "unsupported_value:genre",
        "requested": {"genre": "history"},
        "constraints": {},
    }


@pytest.mark.asyncio
async def test_pipeline_reports_constraint_not_applied_when_index_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex.pipeline import LlamaIndexPipeline

    monkeypatch.setattr(LlamaIndexPipeline, "_configure_settings", lambda self: None)
    pipeline = LlamaIndexPipeline(kb_base_dir=str(tmp_path), signature_provider=lambda: None)

    result = await pipeline.search(
        "reading", "missing-kb", metadata_constraints={"genre": "narrative"}
    )

    assert result["needs_reindex"] is True
    assert result["metadata_constraint"] == {
        "status": "not_applied",
        "reason": "index_unavailable",
        "requested": {"genre": "narrative"},
        "constraints": {"genre": "narrative"},
    }


@pytest.mark.asyncio
async def test_pipeline_reports_constraint_not_applied_on_search_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeptutor.services.rag.pipelines.llamaindex import storage
    from deeptutor.services.rag.pipelines.llamaindex.pipeline import LlamaIndexPipeline

    storage_dir = tmp_path / "kb" / "version-1"
    storage_dir.mkdir(parents=True)
    (storage_dir / "docstore.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LlamaIndexPipeline, "_configure_settings", lambda self: None)

    def fail(*_args, **_kwargs):
        raise RuntimeError("retrieval failed")

    monkeypatch.setattr(storage, "retrieve_nodes_with_constraints", fail)
    pipeline = LlamaIndexPipeline(kb_base_dir=str(tmp_path), signature_provider=lambda: None)

    result = await pipeline.search(
        "reading", "kb", metadata_constraints={"genre": "narrative"}
    )

    assert result["metadata_constraint"] == {
        "status": "not_applied",
        "reason": "search_error:RuntimeError",
        "requested": {"genre": "narrative"},
        "constraints": {"genre": "narrative"},
    }


@pytest.mark.asyncio
async def test_english_handler_passes_structured_constraint_to_rag_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deeptutor.api.routers.hkdse_english import paper as hkdse_english
    from deeptutor.services.rag import service as service_module

    captured: dict[str, object] = {}

    class FakeRAGService:
        async def search(self, **kwargs):
            captured.update(kwargs)
            return {
                "content": "wired context",
                "metadata_constraint": {"status": "applied"},
            }

    monkeypatch.setattr(service_module, "RAGService", FakeRAGService)

    content = await hkdse_english._rag_retrieve(
        "english-kb",
        "narrative",
        metadata_constraints={"genre": "narrative"},
    )

    assert content == "wired context"
    assert captured == {
        "query": "narrative",
        "kb_name": "english-kb",
        "metadata_constraints": {"genre": "narrative"},
    }
