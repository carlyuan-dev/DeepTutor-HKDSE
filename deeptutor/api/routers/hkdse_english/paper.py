"""English reading paper generation."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete
from deeptutor.services.retrieval_context import retrieve_context

logger = logging.getLogger(__name__)
router = APIRouter()


class GeneratePaperRequest(BaseModel):
    kb_name: str | None = None
    title: str = "HKDSE English Paper 1"
    passage_type: str = "informational"  # informational | argumentative | narrative
    question_types: list[str] = ["mcq", "short_answer", "summary"]
    num_questions: int = 8
    difficulty: str = "medium"
    topic_focus: str = ""


_TYPE_DESC: dict[str, str] = {
    "mcq": "Multiple Choice (4 options)",
    "short_answer": "Short Answer (1-3 sentences)",
    "summary": "Summary Writing (50-80 words)",
    "fill_blank": "Fill in the Blank",
}


async def _rag_retrieve(
    kb_name: str,
    query: str,
    *,
    metadata_constraints: dict[str, str] | None = None,
) -> str:
    return await retrieve_context(
        kb_name, query, logger=logger,
        metadata_constraints=metadata_constraints,
        constraint_label="English paper-gen",
        failure_message="RAG failed for paper-gen (degrading): %s",
    )


def _build_paper_system_prompt() -> str:
    return (
        "You are an experienced HKDSE English Paper 1 examiner. "
        "Output ONLY valid JSON — no markdown fences, no extra commentary."
    )


def _build_paper_user_prompt(req: GeneratePaperRequest, context: str) -> str:
    type_desc = "; ".join(f"{k} = {v}" for k, v in _TYPE_DESC.items() if k in req.question_types)
    passage_label = {"informational": "informational text", "argumentative": "argumentative article",
                     "narrative": "narrative prose"}.get(req.passage_type, req.passage_type)

    schema = {
        "title": req.title,
        "passage": "<reading passage of 300-400 words>",
        "questions": [
            {"id": "q1", "type": "mcq", "topic": "Main idea", "points": 2,
             "question": "<question>", "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
             "answer": "A", "explanation": "<explanation>"},
            {"id": "q2", "type": "short_answer", "topic": "Detail", "points": 3,
             "question": "<question>", "answer": "<model answer>", "explanation": "<explanation>"},
        ],
    }

    lines = [
        f"Create a HKDSE Paper 1 Reading Comprehension paper titled \"{req.title}\".",
        f"Passage type: {passage_label}. Write a reading passage of 300-400 words.",
        f"Difficulty: {req.difficulty}.",
        f"Generate {req.num_questions} questions covering these types: {type_desc}.",
        "Ensure questions test a range of skills: literal comprehension, inference, vocabulary in context, and summary.",
    ]
    if req.topic_focus:
        lines.append(
            f"Weak-topic focus: {req.topic_focus}. "
            "Target these weaknesses when designing the passage and questions."
        )
    if context:
        lines.append(f"\nUse this source material for reference:\n{context[:4000]}")

    lines.append(f"\nReturn JSON matching this schema:\n{json.dumps(schema, indent=2)}")
    return "\n".join(lines)


@router.post("/generate-paper")
async def generate_paper(req: GeneratePaperRequest):
    """Generate a HKDSE Paper 1 style reading comprehension paper."""

    async def _stream():
        try:
            yield json.dumps({"type": "progress", "message": "Retrieving source material..."}) + "\n"

            context = ""
            if req.kb_name:
                genre = req.passage_type or "reading comprehension"
                query = genre
                if req.topic_focus:
                    query += f"\nWeak-topic focus: {req.topic_focus}"
                context = await _rag_retrieve(
                    req.kb_name,
                    query,
                    metadata_constraints={"genre": genre},
                )

            yield json.dumps({"type": "progress", "message": "Generating passage and questions..."}) + "\n"

            raw = await llm_complete(
                _build_paper_user_prompt(req, context),
                system_prompt=_build_paper_system_prompt(),
            )

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            paper: dict[str, Any] = json.loads(cleaned)

            for i, q in enumerate(paper.get("questions", [])):
                q.setdefault("id", f"q{i+1}")
                q.setdefault("points", 2)
                q.setdefault("topic", "General")
                q.setdefault("explanation", "")

            yield json.dumps({"type": "done", "paper": paper}) + "\n"

        except Exception as e:
            logger.error(f"English paper generation error: {e}\n{traceback.format_exc()}")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
