"""HKDSE English Language — 英文科 API (Paper Generator + Essay Coach)."""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import traceback
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# F1 — Paper Generator
# ═══════════════════════════════════════════════════════════════════════════════

class GeneratePaperRequest(BaseModel):
    kb_name: str | None = None
    title: str = "HKDSE English Paper 1"
    passage_type: str = "informational"  # informational | argumentative | narrative
    question_types: list[str] = ["mcq", "short_answer", "summary"]
    num_questions: int = 8
    difficulty: str = "medium"


_TYPE_DESC: dict[str, str] = {
    "mcq": "Multiple Choice (4 options)",
    "short_answer": "Short Answer (1-3 sentences)",
    "summary": "Summary Writing (50-80 words)",
    "fill_blank": "Fill in the Blank",
}


async def _rag_retrieve(kb_name: str, query: str) -> str:
    try:
        from deeptutor.services.rag.service import RAGService
        svc = RAGService()
        result = await svc.search(query=query, kb_name=kb_name)
        return result.get("content") or result.get("answer") or ""
    except Exception as e:
        logger.warning(f"RAG failed for paper-gen (degrading): {e}")
        return ""


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
                query = req.passage_type or "reading comprehension"
                context = await _rag_retrieve(req.kb_name, query)

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


# ═══════════════════════════════════════════════════════════════════════════════
# F2 — Essay Coach
# ═══════════════════════════════════════════════════════════════════════════════

class EssayGradeRequest(BaseModel):
    title: str = ""
    essay: str
    genre: str = "argument"  # argument | letter | report | article


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


async def _en_single_grade(req: EssayGradeRequest, persona: str) -> dict[str, Any]:
    system_prompt = _build_essay_grade_system_prompt() + (
        f"\n\nYour grading style is {_EN_AGENT_PERSONAS[persona]}"
    )
    raw = await llm_complete(_build_essay_grade_user_prompt(req), system_prompt=system_prompt)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    result: dict[str, Any] = json.loads(cleaned)
    for field in _ENGLISH_DIMS:
        if field not in result:
            result[field] = {"score": 0, "max_score": 7, "comment": "Data missing"}
    return result


def _parse_json_en(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(cleaned)


@router.post("/essay-grade")
async def grade_essay(req: EssayGradeRequest) -> dict[str, Any]:
    """Grade an English essay — 3-agent ensemble + self-reflection + confidence."""
    try:
        # ── Phase 1: 3-agent ensemble grading ──
        tasks = [_en_single_grade(req, p) for p in ("strict", "lenient", "balanced")]
        three_results = await asyncio.gather(*tasks)

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
                "individual_scores": scores, "score_range": score_range, "confidence": confidence,
            }

        total_median = sum(aggregated[d]["score"] for d in dims)
        max_total = sum(aggregated[d]["max_score"] for d in dims)
        overall_confidence = round(statistics.mean(all_confidences))

        balanced = three_results[2]
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
                "overall_confidence": overall_confidence,
                "agreement_level": "high" if overall_confidence >= 85 else "moderate" if overall_confidence >= 65 else "low",
                "confidence_breakdown": {
                    "overall": overall_confidence,
                    "interpretation": (
                        "high agreement among raters — score is reliable"
                        if overall_confidence >= 85
                        else "moderate agreement — consider reviewing borderline items"
                        if overall_confidence >= 65
                        else "low agreement — manual review recommended"
                    ),
                },
            },
        }

        # ── Phase 2: Self-reflection ──
        reflect_prompt = (
            f"You gave this essay: Content={result['content']['score']}/7, "
            f"Language={result['language']['score']}/7, "
            f"Organisation={result['organisation']['score']}/7.\n"
            "Re-examine your grading. Did you miss any strengths or weaknesses? "
            "Output JSON: {\"score_adjusted\": true/false, "
            "\"reflection_note\": \"<one-sentence reflection>\", "
            "\"revised_overall_comment\": \"<or empty>\"}"
        )
        try:
            reflect_raw = await llm_complete(
                f"Essay:\n{req.essay}\n\n{reflect_prompt}",
                system_prompt="Output only valid JSON.",
            )
            reflection = _parse_json_en(reflect_raw)
            result["reflection"] = {
                "performed": True,
                "score_adjusted": reflection.get("score_adjusted", False),
                "note": reflection.get("reflection_note", ""),
            }
            if reflection.get("revised_overall_comment"):
                result["overall_comment"] = reflection["revised_overall_comment"]
        except Exception:
            result["reflection"] = {"performed": True, "note": "Reflection ran but failed to parse."}

        return result

    except Exception as e:
        logger.error(f"English essay grading error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — Integrated Skills Simulator
# ═══════════════════════════════════════════════════════════════════════════════

class IntegratedSkillsRequest(BaseModel):
    stage: str = "note_making"            # note_making | summary | output
    task_type: str = "letter"             # letter | report | article
    input_texts: list[str]                # 兩篇輸入文本
    student_response: str                 # 學生的答案


@router.post("/integrated-skills")
async def integrated_skills_feedback(req: IntegratedSkillsRequest) -> dict[str, Any]:
    """為 HKDSE Paper 3 Integrated Skills 各階段提供 AI 回饋。"""
    try:
        stage_labels = {
            "note_making": "Note-making (筆記)",
            "summary": "Summary Writing (摘要)",
            "output": f"Output Text - {req.task_type} (輸出文本)",
        }
        stage_label = stage_labels.get(req.stage, req.stage)

        text1 = req.input_texts[0] if len(req.input_texts) > 0 else "(not provided)"
        text2 = req.input_texts[1] if len(req.input_texts) > 1 else "(not provided)"

        schema = {
            "stage": req.stage,
            "feedback": {"score": 3, "max_score": 5, "comment": "具體評語..."},
            "strengths": ["優點一"],
            "improvements": ["改進建議一"],
            "model_answer": "模範答案...",
        }

        system_prompt = (
            "You are an HKDSE English Paper 3 examiner. Provide detailed feedback "
            "on the student's integrated skills task. Output ONLY valid JSON."
        )

        user_prompt = (
            f"Evaluate this HKDSE Paper 3 {stage_label} response.\n\n"
            f"Task type: {req.task_type}\n\n"
            f"Input Text 1:\n{text1[:2000]}\n\n"
            f"Input Text 2:\n{text2[:2000]}\n\n"
            f"Student Response:\n{req.student_response}\n\n"
            f"Provide feedback and a model answer.\n"
            f"Return JSON:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return json.loads(cleaned)

    except Exception as e:
        logger.error(f"Integrated Skills error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
