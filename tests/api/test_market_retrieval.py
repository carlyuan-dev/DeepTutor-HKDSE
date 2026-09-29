"""Offline contracts for the Market routes' optional retrieval context."""

import asyncio
import builtins
import logging
from unittest.mock import AsyncMock

import pytest

from deeptutor.api.routers import flash_deck, hkdse_chinese, market_tools, paper_forge
from deeptutor.api.routers.hkdse_english import paper as hkdse_english
from deeptutor.services.rag import service


ROUTES = [paper_forge, flash_deck, market_tools, hkdse_chinese, hkdse_english]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("result,expected", [
    ({"content": "reference", "answer": "fallback"}, "reference"),
    ({"content": "", "answer": "fallback"}, "fallback"),
    ({}, ""),
])
async def test_context_selection_and_search_arguments(monkeypatch, route, result, expected):
    search = AsyncMock(return_value=result)
    monkeypatch.setattr(service.RAGService, "search", search)
    assert await route._rag_retrieve("course", "original query") == expected
    kwargs = {"query": "original query", "kb_name": "course"}
    if route in (hkdse_chinese, hkdse_english):
        kwargs["metadata_constraints"] = None
    search.assert_awaited_once_with(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_failure_returns_empty_context_and_keeps_route_logger(monkeypatch, caplog, route):
    search = AsyncMock(side_effect=RuntimeError("offline retrieval failure"))
    monkeypatch.setattr(service.RAGService, "search", search)
    with caplog.at_level(logging.WARNING):
        assert await route._rag_retrieve("course", "query") == ""
    assert any(r.name == route.__name__ and "offline retrieval failure" in r.message
               for r in caplog.records)
    assert search.await_count == 1  # No retry introduced by the extraction.


@pytest.mark.asyncio
@pytest.mark.parametrize("route,constraints", [
    (hkdse_chinese, {"language_form": "classical"}),
    (hkdse_english, {"genre": "narrative"}),
])
@pytest.mark.parametrize("status", ["not_applied", "fallback"])
async def test_constraint_fallback_warns_but_preserves_returned_context(
    monkeypatch, caplog, route, constraints, status,
):
    search = AsyncMock(return_value={"content": "available context",
                                    "metadata_constraint": {"status": status, "reason": "no match"}})
    monkeypatch.setattr(service.RAGService, "search", search)
    with caplog.at_level(logging.WARNING):
        assert await route._rag_retrieve("course", "query", metadata_constraints=constraints) == "available context"
    search.assert_awaited_once_with(query="query", kb_name="course", metadata_constraints=constraints)
    assert any(r.name == route.__name__ and status in r.message and "no match" in r.message
               for r in caplog.records)


@pytest.mark.asyncio
async def test_market_without_kb_does_not_construct_service(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Retrieval must not start without a KB")
    monkeypatch.setattr(service, "RAGService", forbidden)
    assert await market_tools._rag_retrieve(None, "query") == ""
    assert await market_tools._rag_retrieve("", "query") == ""


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_to_empty_context(monkeypatch):
    monkeypatch.setattr(service.RAGService, "search", AsyncMock(side_effect=asyncio.CancelledError))
    for route in ROUTES:
        with pytest.raises(asyncio.CancelledError):
            await route._rag_retrieve("course", "query")


@pytest.mark.asyncio
async def test_unavailable_retrieval_import_still_degrades(monkeypatch):
    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "deeptutor.services.rag.service":
            raise ImportError("Retrieval dependency unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    for route in ROUTES:
        assert await route._rag_retrieve("course", "query") == ""
