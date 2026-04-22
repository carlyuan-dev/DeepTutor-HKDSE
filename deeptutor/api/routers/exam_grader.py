"""ExamGrader API — AI-powered grading of examination submissions."""

from __future__ import annotations

import json
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.logging import get_logger
from deeptutor.services.llm import complete as llm_complete

logger = get_logger("ExamGraderAPI")
router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Question(BaseModel):
    id: str
    type: str
    question: str
    options: list[str] | None = None
    answer: str
    explanation: str = ""
    topic: str = "General"
    points: int = 2


class GradeRequest(BaseModel):
    questions: list[Question]
    student_answers: dict[str, str]  # question_id -> student answer


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _build_grade_prompt(questions: list[Question], answers: dict[str, str]) -> str:
    items = []
    for q in questions:
        student_ans = answers.get(q.id, "").strip() or "(no answer)"
        item = {
            "id": q.id,
            "type": q.type,
            "topic": q.topic,
            "question": q.question,
            "correct_answer": q.answer,
            "student_answer": student_ans,
            "max_points": q.points,
        }
        if q.options:
            item["options"] = q.options
        items.append(item)

    schema_example = {
        "results": [
            {
                "question_id": "q1",
                "score": 2,
                "max_score": 2,
                "is_correct": True,
                "comment": "Correct. The student correctly identified...",
                "correct_answer": "...",
            }
        ],
        "total_score": 10,
        "max_score": 20,
        "percentage": 50.0,
        "weak_topics": ["Topic A", "Topic B"],
        "summary": "Overall feedback...",
    }

    return (
        "You are a strict but fair examiner. Grade the following student answers.\n\n"
        "Questions and answers:\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
        + "\n\nGrading rules:\n"
        "- For MCQ: award full points if correct, 0 if wrong.\n"
        "- For fill_blank: award full points for exact/near-exact match, partial for partially correct.\n"
        "- For short_answer: award points proportionally based on completeness and accuracy.\n"
        "- Identify topics where the student performed poorly (score < 60% of max) as weak_topics.\n"
        "- Write an encouraging but honest summary.\n\n"
        "Return ONLY valid JSON matching this schema (no markdown fences):\n"
        + json.dumps(schema_example, indent=2)
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/grade")
async def grade_submission(req: GradeRequest) -> dict[str, Any]:
    """Grade a student submission and return detailed feedback."""
    try:
        system_prompt = (
            "You are an expert examiner. Output only valid JSON — no markdown, no extra text."
        )
        user_prompt = _build_grade_prompt(req.questions, req.student_answers)

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)

        # Parse
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result: dict[str, Any] = json.loads(cleaned)

        # Compute totals if LLM missed them
        if "results" in result:
            if "total_score" not in result:
                result["total_score"] = sum(r.get("score", 0) for r in result["results"])
            if "max_score" not in result:
                result["max_score"] = sum(q.points for q in req.questions)
            if "percentage" not in result and result.get("max_score", 0) > 0:
                result["percentage"] = round(
                    result["total_score"] / result["max_score"] * 100, 1
                )

        return result

    except Exception as exc:
        logger.error(f"ExamGrader error: {exc}\n{traceback.format_exc()}")
        return {"error": str(exc)}
