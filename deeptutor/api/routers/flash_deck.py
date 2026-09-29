"""FlashDeck API — generate flashcards for spaced-repetition review."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete
from deeptutor.services.retrieval_context import retrieve_context

logger = logging.getLogger(__name__)
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
    return await retrieve_context(kb_name, query, logger=logger)


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

def _parse_cards(raw: str, expected: int) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    result = json.loads(cleaned)
    cards = result.get("cards") if isinstance(result, dict) else None
    if not isinstance(cards, list) or len(cards) != expected:
        raise ValueError("Wrong card count")
    for i, card in enumerate(cards):
        if not isinstance(card, dict) or any(
            not isinstance(card.get(key), str) or not card[key].strip()
            for key in ("topic", "front", "back")
        ):
            raise ValueError("Incomplete card")
        card["id"] = f"c{i + 1}"
    return {"cards": cards}


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

        # Larger decks need more output space than the generic 4096-token default.
        # Retry only invalid model content, not transport/authentication errors.
        for attempt in range(2):
            raw = await llm_complete(
                user_prompt, system_prompt=system_prompt,
                max_tokens=max(4096, num_cards * 512),
            )
            try:
                return _parse_cards(raw, num_cards)
            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning("FlashDeck invalid output on attempt %s: %s", attempt + 1, type(exc).__name__)
                user_prompt += "\nThe previous output was incomplete. Return every requested card as complete JSON, with concise answers."
        return {
            "error": "The model did not return a complete flashcard set. Please try again.",
            "retryable": True,
        }

    except Exception as exc:
        logger.error(f"FlashDeck generation error: {exc}\n{traceback.format_exc()}")
        return {"error": str(exc)}
