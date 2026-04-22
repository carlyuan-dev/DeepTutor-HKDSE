"""FlashDeck API — generate flashcards for spaced-repetition review."""

from __future__ import annotations

import json
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.logging import get_logger
from deeptutor.services.llm import complete as llm_complete

logger = get_logger("FlashDeckAPI")
router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class GenerateCardsRequest(BaseModel):
    topics: list[str]           # weak topics from ExamGrader, or manual input
    kb_name: str | None = None
    num_cards: int = 15         # cards to generate (capped at 30)


# ---------------------------------------------------------------------------
# RAG helper
# ---------------------------------------------------------------------------

async def _rag_retrieve(kb_name: str, query: str) -> str:
    try:
        from deeptutor.services.rag.service import RAGService
        service = RAGService()
        result = await service.search(query=query, kb_name=kb_name)
        return result.get("content") or result.get("answer") or ""
    except Exception as exc:
        logger.warning(f"RAG retrieval failed (degrading to LLM-only): {exc}")
        return ""


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _build_cards_prompt(topics: list[str], context: str, num_cards: int) -> str:
    schema_example = {
        "cards": [
            {
                "id": "c1",
                "topic": "Newton's Laws",
                "front": "What does Newton's Second Law state?",
                "back": "F = ma — Force equals mass times acceleration.",
            }
        ]
    }

    parts = [
        f"Create {num_cards} flashcards to help a student review the following topics: "
        + ", ".join(topics) + ".",
        "",
        "Each card should:",
        "- Have a concise question or prompt on the FRONT.",
        "- Have a clear, complete answer on the BACK (2-4 sentences max).",
        "- Test a single concept.",
        "- Cover different aspects of each topic.",
    ]
    if context:
        parts += [
            "",
            "Use this knowledge base content as the primary source:",
            context[:5000],
        ]
    parts += [
        "",
        f"Return exactly {num_cards} cards as valid JSON (no markdown fences):",
        json.dumps(schema_example, indent=2),
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_cards(req: GenerateCardsRequest) -> dict[str, Any]:
    """Generate flashcards for the given topics."""
    num_cards = min(req.num_cards, 30)
    try:
        context = ""
        if req.kb_name and req.topics:
            context = await _rag_retrieve(req.kb_name, " ".join(req.topics))

        system_prompt = "You are an expert flashcard creator. Output only valid JSON."
        user_prompt = _build_cards_prompt(req.topics, context, num_cards)

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result: dict[str, Any] = json.loads(cleaned)

        # Assign stable IDs
        for i, card in enumerate(result.get("cards", [])):
            card.setdefault("id", f"c{i + 1}")

        return result

    except Exception as exc:
        logger.error(f"FlashDeck generation error: {exc}\n{traceback.format_exc()}")
        return {"error": str(exc)}
