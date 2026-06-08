"""PaperForge API — generate examination papers from a knowledge base."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    kb_name: str | None = None
    title: str = "Examination Paper"
    question_types: list[str] = ["mcq", "short_answer"]  # mcq | fill_blank | short_answer
    num_questions: int = 10
    difficulty: str = "medium"  # easy | medium | hard
    topic_focus: str = ""


# ---------------------------------------------------------------------------
# RAG helper (graceful degradation when RAG not installed)
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
# Prompt builder
# ---------------------------------------------------------------------------

_TYPE_LABELS = {
    "mcq": "Multiple Choice (4 options, single correct)",
    "fill_blank": "Fill in the Blank",
    "short_answer": "Short Answer",
}

_DIFF_LABELS = {
    "easy": "straightforward recall questions",
    "medium": "questions requiring comprehension and application",
    "hard": "challenging analytical and synthesis questions",
}


def _build_system_prompt() -> str:
    return (
        "You are an expert exam question writer. "
        "Your output must be valid JSON only — no markdown fences, no extra text. "
        "Follow the schema exactly."
    )


def _build_user_prompt(req: GenerateRequest, context: str) -> str:
    type_desc = "; ".join(
        f"{t} = {_TYPE_LABELS.get(t, t)}" for t in req.question_types
    )
    diff_desc = _DIFF_LABELS.get(req.difficulty, "medium difficulty")

    schema = {
        "title": req.title,
        "questions": [
            {
                "id": "q1",
                "type": "<one of: " + ", ".join(req.question_types) + ">",
                "topic": "<topic or concept being tested>",
                "question": "<question text>",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "answer": "<correct answer or model answer>",
                "explanation": "<brief explanation>",
                "points": 2,
            }
        ],
    }

    parts = [
        f"Generate an exam paper titled \"{req.title}\".",
        f"Total questions: {req.num_questions}.",
        f"Question types: {type_desc}.",
        f"Difficulty: {diff_desc}.",
    ]
    if req.topic_focus:
        parts.append(f"Focus on the topic: {req.topic_focus}.")
    if context:
        parts.append(f"\nUse the following knowledge base content as source material:\n\n{context[:6000]}")
    parts.append(
        "\nIMPORTANT:"
        "\n- For mcq questions include 'options' array with exactly 4 items."
        "\n- For fill_blank and short_answer omit 'options'."
        "\n- Distribute questions evenly across the requested types."
        f"\n- Return exactly {req.num_questions} questions."
        "\n\nOutput JSON matching this schema:\n" + json.dumps(schema, indent=2)
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Streaming endpoint
# ---------------------------------------------------------------------------

@router.post("/generate")
async def generate_paper(req: GenerateRequest):
    """Stream a generated exam paper as NDJSON lines."""

    async def _stream():
        try:
            yield json.dumps({"type": "progress", "message": "Retrieving knowledge base content..."}) + "\n"

            context = ""
            if req.kb_name:
                query = req.topic_focus or req.title or "key concepts"
                context = await _rag_retrieve(req.kb_name, query)

            yield json.dumps({"type": "progress", "message": "Generating questions with AI..."}) + "\n"

            system_prompt = _build_system_prompt()
            user_prompt = _build_user_prompt(req, context)

            raw = await llm_complete(user_prompt, system_prompt=system_prompt)

            # Parse JSON from LLM response
            paper: dict[str, Any] = {}
            try:
                # Strip possible markdown code fences
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.splitlines()
                    cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                paper = json.loads(cleaned)
            except json.JSONDecodeError:
                # Try extracting JSON block
                import re
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    paper = json.loads(m.group())
                else:
                    raise ValueError("LLM did not return valid JSON")

            # Ensure required fields
            if "questions" not in paper:
                raise ValueError("LLM response missing 'questions' field")

            # Assign stable IDs and default points
            for i, q in enumerate(paper.get("questions", [])):
                q.setdefault("id", f"q{i + 1}")
                q.setdefault("points", 2)
                q.setdefault("topic", "General")
                q.setdefault("explanation", "")

            yield json.dumps({"type": "done", "paper": paper}) + "\n"

        except Exception as exc:
            logger.error(f"PaperForge generation error: {exc}\n{traceback.format_exc()}")
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
