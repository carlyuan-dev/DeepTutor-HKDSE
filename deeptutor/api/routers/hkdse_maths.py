"""HKDSE Mathematics — 數學科 API (Step Checker + Topic Drill)."""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# F2 — Step-by-Step Solution Checker
# ═══════════════════════════════════════════════════════════════════════════════

class StepCheckRequest(BaseModel):
    question: str                            # 题目
    student_steps: list[str]                 # 学生的解题步骤（每行一步）


class StepResult(BaseModel):
    step_index: int                          # 第几步
    student_step: str                       # 学生的步骤原文
    is_correct: bool                        # 该步是否正确
    comment: str                            # 评语
    corrected_step: str = ""                # 正确步骤（如果错了）


class StepCheckResult(BaseModel):
    steps: list[StepResult]
    first_error_index: int | None = None     # 第一个错误的步骤索引（-1 表示全对）
    overall_correct: bool
    full_solution: str                       # 完整正确解法
    summary: str                             # 总结


def _build_step_check_system_prompt() -> str:
    return """You are an experienced HKDSE Mathematics examiner. Your job is to check a student's step-by-step solution.

For each step:
- If correct, mark it correct and briefly explain why.
- If incorrect, mark it incorrect, explain what went wrong, and provide the corrected step.
- Identify the FIRST step where the error occurs (if any).
- Provide the full correct solution from start to finish.
- Even if one step is wrong, continue checking subsequent steps (they might still be correct relative to the student's earlier error, OR they might have independent errors).

Output ONLY valid JSON — no markdown fences, no extra commentary."""


def _build_step_check_user_prompt(req: StepCheckRequest) -> str:
    steps_text = "\n".join(
        f"Step {i+1}: {step}" for i, step in enumerate(req.student_steps)
    )

    schema = {
        "steps": [
            {
                "step_index": 0,
                "student_step": "y = x^2 + 2x + 3",
                "is_correct": True,
                "comment": "Correct. The student correctly wrote the quadratic function.",
                "corrected_step": "",
            },
            {
                "step_index": 1,
                "student_step": "x = -2/2 = -1",
                "is_correct": False,
                "comment": "Incorrect. The axis of symmetry formula is x = -b/(2a). For y = x²+2x+3, a=1, b=2, so x = -2/(2·1) = -1 is actually correct. But the student wrote '-2/2' instead of '-2/(2·1)' — while the result happens to be the same, the step is sloppy. Mark as partially correct.",
                "corrected_step": "x = -b/(2a) = -2/(2·1) = -1",
            },
        ],
        "first_error_index": None,
        "overall_correct": True,
        "full_solution": "1. Identify a=1, b=2, c=3.\n2. Vertex: x = -b/(2a) = -2/2 = -1\n3. y = f(-1) = (-1)² + 2(-1) + 3 = 2\n4. Answer: vertex is (-1, 2).",
        "summary": "The student correctly found the axis of symmetry but should show the formula more clearly. Overall good understanding of quadratic functions.",
    }

    return f"""Check this student's step-by-step math solution.

Question: {req.question}

Student's steps:
{steps_text}

Analyze each step carefully. Check:
- Arithmetic correctness
- Formula application
- Logical flow between steps
- Whether the final answer follows from the steps

Return JSON following this schema:
{json.dumps(schema, ensure_ascii=False, indent=2)}"""


@router.post("/step-check")
async def check_steps(req: StepCheckRequest) -> dict[str, Any]:
    """Check a student's step-by-step math solution."""
    try:
        raw = await llm_complete(
            _build_step_check_user_prompt(req),
            system_prompt=_build_step_check_system_prompt(),
        )

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result: dict[str, Any] = json.loads(cleaned)
        return result

    except Exception as e:
        logger.error(f"Step check error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — Topic Drill (generate practice questions for a specific topic)
# ═══════════════════════════════════════════════════════════════════════════════

class TopicDrillRequest(BaseModel):
    topic: str                               # HKDSE syllabus topic
    difficulty: str = "basic"                # basic | applied | challenge
    num_questions: int = 5                   # 5-15


@router.post("/topic-drill")
async def topic_drill(req: TopicDrillRequest) -> dict[str, Any]:
    """Generate a set of practice questions for a specific HKDSE maths topic."""
    try:
        system_prompt = (
            "You are an HKDSE Mathematics teacher. Generate practice questions with full worked solutions. "
            "Output ONLY valid JSON — no markdown fences."
        )

        schema = {
            "topic": req.topic,
            "difficulty": req.difficulty,
            "questions": [
                {
                    "id": "q1",
                    "question": "<question text>",
                    "answer": "<correct answer>",
                    "worked_solution": "<step-by-step solution>",
                    "tips": "<study tip>",
                }
            ],
        }

        user_prompt = (
            f"Create {req.num_questions} HKDSE Mathematics practice questions.\n"
            f"Topic: {req.topic}\n"
            f"Difficulty: {req.difficulty} ("
            + {"basic": "straightforward recall", "applied": "application and problem-solving",
               "challenge": "challenging, multi-step"}.get(req.difficulty, req.difficulty)
            + ")\n"
            f"Each question must include a full worked solution with clear steps.\n\n"
            f"Return JSON:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result: dict[str, Any] = json.loads(cleaned)
        for i, q in enumerate(result.get("questions", [])):
            q.setdefault("id", f"q{i+1}")
        return result

    except Exception as e:
        logger.error(f"Topic drill error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
