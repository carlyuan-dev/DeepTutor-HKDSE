"""Best-effort text context for generation routes, not the learning-state contract.

Callers own query construction, whether retrieval is requested, and filters.
This adapter preserves available context on filter fallback and logs the outcome;
it does not implement a new retrieval policy or retry failed requests.
"""

from __future__ import annotations

import logging
from typing import Any


async def retrieve_context(
    kb_name: str,
    query: str,
    *,
    logger: logging.Logger,
    failure_message: str = "RAG retrieval failed (degrading to LLM-only): %s",
    constraint_label: str | None = None,
    **search_options: Any,
) -> str:
    """Return content, then answer, or empty text on ordinary retrieval failure.

Search options are forwarded unchanged. Cancellation is not swallowed.
The service stays lazily imported/constructed inside the fallback boundary.
"""
    try:
        from deeptutor.services.rag.service import RAGService

        result = await RAGService().search(query=query, kb_name=kb_name, **search_options)
        if constraint_label is not None:
            outcome = result.get("metadata_constraint") or {}
            if outcome.get("status") in {"not_applied", "fallback"}:
                logger.warning(
                    "%s RAG constraint %s: %s",
                    constraint_label, outcome.get("status"), outcome.get("reason", "unknown"),
                )
        return result.get("content") or result.get("answer") or ""
    except Exception as exc:  # Cancellation deliberately propagates.
        logger.warning(failure_message, exc)
        return ""
