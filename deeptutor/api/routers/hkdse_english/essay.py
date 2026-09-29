"""English essay grading and review."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete

logger = logging.getLogger(__name__)
router = APIRouter()


class EssayGradeRequest(BaseModel):
    title: str = ""
    essay: str
    genre: str = "argument"  # argument | letter | report | article
    mode: Literal["single", "review"] = "single"


_GENRE_LABELS: dict[str, str] = {
    "argument": "Argumentative Essay",
    "letter": "Formal Letter",
    "report": "Report",
    "article": "Feature Article",
}

_ENGLISH_RUBRIC = """HKDSE English Language Paper 2 Writing — Marking Criteria (max 21 marks):

I. Content (7 marks)
- Relevance to the topic and task requirements
- Quality and development of ideas
- Use of supporting details / examples

II. Language (7 marks)
- Accuracy and range of vocabulary
- Grammatical accuracy and sentence variety
- Appropriate register and tone

III. Organisation (7 marks)
- Overall structure (introduction — body — conclusion)
- Paragraphing and coherence
- Use of cohesive devices (transitions, connectors)"""


def _build_essay_grade_system_prompt() -> str:
    return """You are an HKDSE English Paper 2 examiner. Grade essays strictly according to the official marking criteria.
Provide specific feedback with quotes from the essay. Output ONLY valid JSON — no markdown fences."""


def _build_essay_grade_user_prompt(req: EssayGradeRequest) -> str:
    genre_label = _GENRE_LABELS.get(req.genre, req.genre)

    schema = {
        "content": {"score": 5, "max_score": 7, "comment": "Good ideas but needs more supporting examples..."},
        "language": {"score": 5, "max_score": 7, "comment": "Adequate vocabulary range, some grammar errors..."},
        "organisation": {"score": 5, "max_score": 7, "comment": "Clear structure, paragraphing could improve..."},
        "total_score": 15,
        "max_score": 21,
        "percentage": 71.4,
        "strengths": ["Strength 1 with quote", "Strength 2 with quote"],
        "improvements": ["Improvement 1 with specific example", "Improvement 2 with specific example"],
        "overall_comment": "Overall assessment...",
        "annotated_essay": "Original text【annotation: comment here】continued text...",
    }

    return f"""Grade this HKDSE Paper 2 {genre_label} against the official criteria:

{_ENGLISH_RUBRIC}

Topic: {req.title or "(not provided)"}

Student Essay:
---
{req.essay}
---

Return JSON in this format:
{json.dumps(schema, ensure_ascii=False, indent=2)}"""


# ---------------------------------------------------------------------------
# Ensemble grading helpers (shared with essay-grade)
# ---------------------------------------------------------------------------

_EN_AGENT_PERSONAS = {
    "strict": "strict. Grade conservatively — award high marks only when writing clearly excels.",
    "lenient": "generous. Give the benefit of the doubt — focus on what the student did well.",
    "balanced": "fair and balanced. Weigh strengths and weaknesses evenly, following the rubric exactly.",
}

_ENGLISH_DIMS = ("content", "language", "organisation")
_ESSAY_CALL_TIMEOUT = 90.0


async def _en_single_grade(req: EssayGradeRequest, persona: str) -> dict[str, Any]:
    system_prompt = _build_essay_grade_system_prompt() + (
        f"\n\nYour grading style is {_EN_AGENT_PERSONAS[persona]}"
    )
    raw = await llm_complete(_build_essay_grade_user_prompt(req), system_prompt=system_prompt, max_retries=0)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    result: dict[str, Any] = json.loads(cleaned)
    if not isinstance(result, dict):
        raise ValueError("Invalid essay grade: expected an object")
    for field in _ENGLISH_DIMS:
        dim = result.get(field)
        if (
            not isinstance(dim, dict)
            or type(dim.get("score")) is not int
            or not 0 <= dim["score"] <= 7
            or type(dim.get("max_score")) is not int
            or dim["max_score"] != 7
            or not isinstance(dim.get("comment"), str)
        ):
            raise ValueError(f"Invalid essay grade: {field} requires an integer score 0–7, max_score 7 and a comment")
    for field in ("strengths", "improvements"):
        value = result.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Invalid essay grade: {field} must be a list of strings")
    for field in ("overall_comment", "annotated_essay"):
        if not isinstance(result.get(field, ""), str):
            raise ValueError(f"Invalid essay grade: {field} must be text")
    return result


def _parse_json_en(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(cleaned)


def _essay_failure(exc: Exception, persona: str, request_id: str) -> dict[str, Any]:
    """Allowlisted diagnostic metadata only; never exception text or response bodies."""
    from deeptutor.services.llm.exceptions import LLMError, LLMTimeoutError

    status = getattr(exc, "status_code", None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    provider_id = getattr(exc, "request_id", None)
    provider_id = provider_id if isinstance(provider_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", provider_id) else None
    if isinstance(exc, (TimeoutError, LLMTimeoutError)):
        category = "timeout"
    elif isinstance(exc, json.JSONDecodeError):
        category = "invalid_json"
    elif isinstance(exc, ValueError):
        category = "invalid_structure"
    elif status in (401, 403):
        category = "authentication"
    elif status == 429:
        category = "rate_limit"
    elif isinstance(exc, LLMError):
        category = "provider_error"
    else:
        category = "internal_error"
    detail = {"persona": persona, "category": category, "status_code": status,
              "provider_request_id": provider_id, "request_id": request_id}
    logger.warning("Essay grading diagnostic: %s", detail)
    return detail


async def _essay_rater(req: EssayGradeRequest, persona: str, request_id: str):
    try:
        return await asyncio.wait_for(_en_single_grade(req, persona), _ESSAY_CALL_TIMEOUT), None
    except Exception as exc:
        return None, _essay_failure(exc, persona, request_id)


@router.post("/essay-grade")
async def grade_essay(req: EssayGradeRequest) -> dict[str, Any]:
    """Balanced default; opt-in review degrades only to a valid balanced grade."""
    request_id = uuid4().hex
    personas = ("strict", "lenient", "balanced") if req.mode == "review" else ("balanced",)
    outcomes = await asyncio.gather(*(_essay_rater(req, p, request_id) for p in personas))
    ratings = {p: value for p, (value, _) in zip(personas, outcomes)}
    failures = [failure for _, failure in outcomes if failure is not None]
    balanced = ratings["balanced"]
    grading = {"requested_mode": req.mode, "request_id": request_id, "failures": failures,
               "strategy_used": "balanced", "review_status": "not_requested"}
    if balanced is None:
        grading.update(strategy_used="none", review_status="failed")
        category = next(f["category"] for f in failures if f["persona"] == "balanced")
        retryable = category not in ("authentication", "internal_error")
        return {"error": "Balanced grading failed. Retry, or check the model configuration if the problem persists.",
                "retryable": retryable, "grading": grading}

    if req.mode == "single" or failures:
        if failures:
            grading["review_status"] = "incomplete"
        total = sum(balanced[d]["score"] for d in _ENGLISH_DIMS)
        result = {**{d: {k: balanced[d][k] for k in ("score", "max_score", "comment")} for d in _ENGLISH_DIMS},
                  "total_score": total, "max_score": 21, "percentage": round(total / 21 * 100, 1),
                  "strengths": balanced.get("strengths", []), "improvements": balanced.get("improvements", []),
                  "overall_comment": balanced.get("overall_comment", ""), "annotated_essay": balanced.get("annotated_essay", "")}
    else:
        grading.update(strategy_used="median", review_status="complete")
        three_results = [ratings[p] for p in personas]

        dims = _ENGLISH_DIMS
        aggregated: dict[str, Any] = {}
        all_confidences = []

        for dim in dims:
            scores = [s[dim]["score"] for s in three_results]
            max_s = three_results[0][dim]["max_score"]
            comments = [s[dim]["comment"] for s in three_results]

            median_score = int(statistics.median(scores))
            score_range = max(scores) - min(scores)
            confidence = max(50, round(100 - score_range / max_s * 100))
            all_confidences.append(confidence)

            median_idx = sorted(range(len(scores)), key=lambda i: abs(scores[i] - median_score))[0]
            aggregated[dim] = {
                "score": median_score, "max_score": max_s,
                "comment": comments[median_idx],
                "individual_scores": scores, "score_range": score_range, "agreement_score": confidence,
            }

        total_median = sum(aggregated[d]["score"] for d in dims)
        max_total = sum(aggregated[d]["max_score"] for d in dims)
        overall_confidence = round(statistics.mean(all_confidences))

        result = {
            **{d: aggregated[d] for d in dims},
            "total_score": total_median, "max_score": max_total,
            "percentage": round(total_median / max_total * 100, 1) if max_total > 0 else 0,
            "strengths": balanced.get("strengths", []),
            "improvements": balanced.get("improvements", []),
            "overall_comment": balanced.get("overall_comment", ""),
            "annotated_essay": balanced.get("annotated_essay", ""),
            "ensemble": {
                "method": "3-agent median",
                "agents": ["strict", "lenient", "balanced"],
                "overall_agreement": overall_confidence,
                "review_recommended": overall_confidence < 65,
                "agreement_level": "high" if overall_confidence >= 85 else "moderate" if overall_confidence >= 65 else "low",
                "agreement_breakdown": {
                    "overall": overall_confidence,
                    "interpretation": (
                        "high agreement among raters — not a probability of correctness"
                        if overall_confidence >= 85
                        else "moderate agreement — consider reviewing borderline items"
                        if overall_confidence >= 65
                        else "low agreement — manual review recommended"
                    ),
                },
            },
        }

    result["grading"] = grading
    # Comment review is separate from scoring (one extra call in either mode).
    try:
        reflect_prompt = (
            f"You gave this essay: Content={result['content']['score']}/7, "
            f"Language={result['language']['score']}/7, "
            f"Organisation={result['organisation']['score']}/7.\n"
            "Review the overall comment only. Do not change the scores. "
            "Output JSON: {"
            "\"reflection_note\": \"<one-sentence reflection>\", "
            "\"revised_overall_comment\": \"<or empty>\"}"
        )
        try:
            reflect_raw = await asyncio.wait_for(llm_complete(
                f"Essay:\n{req.essay}\n\n{reflect_prompt}",
                system_prompt="Output only valid JSON.", max_retries=0,
            ), _ESSAY_CALL_TIMEOUT)
            reflection = _parse_json_en(reflect_raw)
            if not isinstance(reflection, dict) or any(
                not isinstance(reflection.get(key, ""), str)
                for key in ("reflection_note", "revised_overall_comment")
            ):
                raise ValueError("Invalid reflection text")
            result["reflection"] = {
                "performed": True,
                "score_adjusted": False,
                "note": reflection.get("reflection_note", ""),
            }
            if reflection.get("revised_overall_comment"):
                result["overall_comment"] = reflection["revised_overall_comment"]
        except Exception as exc:
            _essay_failure(exc, "comment_review", request_id)
            result["reflection"] = {
                "performed": False, "score_adjusted": False,
                "note": "Comment review failed; original scores and comment retained.",
            }

        return result

    except Exception as exc:
        _essay_failure(exc, "comment_review", request_id)
        result["reflection"] = {"performed": False, "score_adjusted": False, "note": "Comment review unavailable."}
        return result
