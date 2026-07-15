"""Market Tools API — a suite of practical learning tools for the Market tab.

Each endpoint is a focused learning utility built on the local/configured LLM
(and optionally grounded in a knowledge base via RAG). Tools included:

  • GET  /llm-status            — report the active inference engine (local/cloud + reachability)
  • POST /study-planner         — generate a personalized day-by-day revision plan
  • POST /concept-explainer     — explain a concept with analogy, example, pitfalls (RAG-capable)
  • POST /note-maker            — turn a topic / pasted text into structured study notes (RAG-capable)
  • POST /diagnostic/generate   — generate a short diagnostic quiz
  • POST /diagnostic/grade      — grade a diagnostic and return an ability profile
  • POST /mistake-book/analyze  — classify a wrong answer, explain it, and draft a similar question
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from typing import Any

import aiohttp
from fastapi import APIRouter
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete

logger = logging.getLogger(__name__)
router = APIRouter()


# ───────────────────────────────────────────────────────────────────────────
# Shared helpers
# ───────────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from an LLM response."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError("LLM did not return valid JSON")


async def _rag_retrieve(kb_name: str | None, query: str) -> str:
    """Retrieve grounded context from a KB. Degrades to empty string on failure."""
    if not kb_name:
        return ""
    try:
        from deeptutor.services.rag.service import RAGService

        result = await RAGService().search(query=query, kb_name=kb_name)
        return result.get("content") or result.get("answer") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG retrieval failed (degrading to LLM-only): %s", exc)
        return ""


# ───────────────────────────────────────────────────────────────────────────
# GET /llm-status — which inference engine is active, and is it reachable?
# ───────────────────────────────────────────────────────────────────────────

@router.get("/llm-status")
async def llm_status() -> dict[str, Any]:
    """Report the active LLM provider, whether it runs locally, and reachability.

    Lets the UI surface an "offline / on-premise" badge so users can confirm
    that inference is running on local hardware (Apple MLX / Ollama / LM Studio).
    """
    try:
        from deeptutor.services.llm.config import get_llm_config
        from deeptutor.services.provider_registry import (
            canonical_provider_name,
            find_by_name,
        )

        cfg = get_llm_config()
        canonical = canonical_provider_name(cfg.binding) or (cfg.binding or "").lower()
        spec = find_by_name(canonical)
        is_local = bool(spec and spec.is_local)
        display = spec.label if spec else (cfg.binding or "Unknown")
        base_url = cfg.effective_url or cfg.base_url or ""

        # Best-effort reachability probe (short timeout, never raises).
        reachable: bool | None = None
        if base_url:
            reachable = await _probe_endpoint(base_url, cfg.api_key)

        return {
            "binding": cfg.binding,
            "display_name": display,
            "model": cfg.model,
            "mode": "local" if is_local else "cloud",
            "is_local": is_local,
            "base_url": base_url,
            "reachable": reachable,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("llm-status error: %s", exc)
        return {"error": str(exc)}


async def _probe_endpoint(base_url: str, api_key: str | None) -> bool | None:
    """Ping an OpenAI-compatible endpoint's /models route. Returns None on timeout."""
    url = base_url.rstrip("/")
    # OpenAI-compatible servers expose /models; ollama also serves /v1/models.
    probe_url = url + "/models" if url.endswith("/v1") else url + "/v1/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(probe_url, headers=headers) as resp:
                return resp.status < 500
    except Exception:  # noqa: BLE001
        return False


# ───────────────────────────────────────────────────────────────────────────
# POST /study-planner — personalized revision schedule
# ───────────────────────────────────────────────────────────────────────────

class StudyPlanRequest(BaseModel):
    subjects: list[str]
    days_until_exam: int = 14
    hours_per_day: float = 2.0
    goals: str = ""
    current_level: str = "intermediate"  # beginner | intermediate | advanced
    language: str = "en"


@router.post("/study-planner")
async def study_planner(req: StudyPlanRequest) -> dict[str, Any]:
    """Generate a structured, day-by-day revision plan."""
    try:
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        schema = {
            "overview": "<one-paragraph strategy summary>",
            "daily_hours": req.hours_per_day,
            "days": [
                {
                    "day": 1,
                    "focus": "<main focus for the day>",
                    "subjects": ["<subject>"],
                    "tasks": ["<concrete task>", "<concrete task>"],
                    "milestone": "<what to achieve by end of day>",
                }
            ],
            "tips": ["<study tip>", "<study tip>"],
        }
        system_prompt = (
            "You are an expert HKDSE study coach. Build realistic, motivating revision "
            "plans. Output ONLY valid JSON — no markdown fences, no extra text."
        )
        user_prompt = (
            f"{lang_line}\n"
            f"Create a {req.days_until_exam}-day revision plan.\n"
            f"Subjects: {', '.join(req.subjects)}.\n"
            f"Study time available: {req.hours_per_day} hours per day.\n"
            f"Student level: {req.current_level}.\n"
            + (f"Goals: {req.goals}.\n" if req.goals else "")
            + "Distribute topics sensibly, interleave subjects, schedule review/mock days, "
            "and finish with a light consolidation day before the exam.\n"
            f"Produce exactly {req.days_until_exam} day entries.\n\n"
            f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        plan = _parse_json(raw)
        return plan
    except Exception as exc:  # noqa: BLE001
        logger.error("study-planner error: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc)}


# ───────────────────────────────────────────────────────────────────────────
# POST /concept-explainer — clear explanation with analogy + example + pitfalls
# ───────────────────────────────────────────────────────────────────────────

class ConceptRequest(BaseModel):
    concept: str
    subject: str = ""
    kb_name: str | None = None
    level: str = "intermediate"
    language: str = "en"


@router.post("/concept-explainer")
async def concept_explainer(req: ConceptRequest) -> dict[str, Any]:
    """Explain a concept with a plain-language summary, analogy, example, and pitfalls."""
    try:
        context = await _rag_retrieve(req.kb_name, req.concept)
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        schema = {
            "concept": req.concept,
            "summary": "<2-3 sentence plain-language explanation>",
            "analogy": "<an intuitive everyday analogy>",
            "key_points": ["<key point>", "<key point>"],
            "worked_example": "<a concrete worked example>",
            "common_mistakes": ["<common mistake>", "<common mistake>"],
            "check_question": "<one quick self-check question with its answer>",
        }
        system_prompt = (
            "You are a patient, expert tutor. Explain concepts clearly for a secondary "
            "school student. Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{lang_line}\n"
            f"Explain the concept: \"{req.concept}\".\n"
            + (f"Subject: {req.subject}.\n" if req.subject else "")
            + f"Target level: {req.level}.\n"
            + (f"\nGround your explanation in this source material:\n{context[:5000]}\n" if context else "")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        result = _parse_json(raw)
        result["grounded"] = bool(context)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("concept-explainer error: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc)}


# ───────────────────────────────────────────────────────────────────────────
# POST /note-maker — structured study notes from a topic or pasted text
# ───────────────────────────────────────────────────────────────────────────

class NoteRequest(BaseModel):
    topic: str = ""
    source_text: str = ""
    kb_name: str | None = None
    style: str = "outline"  # outline | cornell | mindmap
    language: str = "en"


@router.post("/note-maker")
async def note_maker(req: NoteRequest) -> dict[str, Any]:
    """Generate structured revision notes (outline / Cornell / mind-map style)."""
    try:
        query = req.topic or req.source_text[:200]
        context = await _rag_retrieve(req.kb_name, query) if not req.source_text else ""
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        schema = {
            "title": "<note title>",
            "summary": "<one-sentence summary>",
            "sections": [
                {"heading": "<section heading>", "points": ["<point>", "<point>"]}
            ],
            "key_terms": [{"term": "<term>", "definition": "<definition>"}],
            "mnemonic": "<an optional memory aid, or empty string>",
        }
        body = req.source_text or context
        system_prompt = (
            "You are a study-notes generator. Produce concise, well-structured, "
            "exam-focused notes. Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{lang_line}\n"
            f"Create {req.style}-style study notes"
            + (f" on the topic: \"{req.topic}\".\n" if req.topic else ".\n")
            + (f"\nSource material to condense:\n{body[:6000]}\n" if body else "")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        result = _parse_json(raw)
        result["grounded"] = bool(context)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("note-maker error: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc)}


# ───────────────────────────────────────────────────────────────────────────
# POST /diagnostic/generate + /diagnostic/grade — quick weak-area diagnostic
# ───────────────────────────────────────────────────────────────────────────

class DiagnosticRequest(BaseModel):
    subject: str
    topics: list[str] = []
    num_questions: int = 6
    kb_name: str | None = None
    language: str = "en"


@router.post("/diagnostic/generate")
async def diagnostic_generate(req: DiagnosticRequest) -> dict[str, Any]:
    """Generate a short diagnostic quiz spanning the requested topics."""
    try:
        context = await _rag_retrieve(req.kb_name, req.subject + " " + " ".join(req.topics))
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        schema = {
            "subject": req.subject,
            "questions": [
                {
                    "id": "q1",
                    "topic": "<topic being probed>",
                    "difficulty": "easy|medium|hard",
                    "question": "<question text>",
                    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                    "answer": "A",
                }
            ],
        }
        system_prompt = (
            "You are an assessment designer. Create diagnostic MCQs that efficiently "
            "reveal a student's weak topics. Output ONLY valid JSON — no markdown fences."
        )
        topics_line = f"Topics to probe: {', '.join(req.topics)}.\n" if req.topics else ""
        user_prompt = (
            f"{lang_line}\n"
            f"Create a {req.num_questions}-question diagnostic quiz for {req.subject}.\n"
            f"{topics_line}"
            "Spread questions across topics and difficulties so weak areas stand out. "
            "Each question is multiple choice with exactly 4 options.\n"
            + (f"\nUse this source material:\n{context[:4000]}\n" if context else "")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        quiz = _parse_json(raw)
        for i, q in enumerate(quiz.get("questions", [])):
            q.setdefault("id", f"q{i + 1}")
        return quiz
    except Exception as exc:  # noqa: BLE001
        logger.error("diagnostic/generate error: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc)}


class DiagnosticGradeRequest(BaseModel):
    subject: str
    questions: list[dict[str, Any]]
    answers: dict[str, str]  # question_id -> chosen option
    language: str = "en"


@router.post("/diagnostic/grade")
async def diagnostic_grade(req: DiagnosticGradeRequest) -> dict[str, Any]:
    """Grade a diagnostic and produce a per-topic mastery profile + next steps."""
    try:
        # Objective scoring (no LLM needed for correctness) + per-topic aggregation.
        topic_totals: dict[str, int] = {}
        topic_correct: dict[str, int] = {}
        details = []
        correct_count = 0
        for q in req.questions:
            qid = q.get("id", "")
            topic = q.get("topic", "General")
            correct_ans = str(q.get("answer", "")).strip()
            student = str(req.answers.get(qid, "")).strip()
            is_correct = bool(student) and (
                student == correct_ans
                or student[:1].upper() == correct_ans[:1].upper()
            )
            topic_totals[topic] = topic_totals.get(topic, 0) + 1
            topic_correct[topic] = topic_correct.get(topic, 0) + (1 if is_correct else 0)
            correct_count += 1 if is_correct else 0
            details.append(
                {"question_id": qid, "topic": topic, "is_correct": is_correct,
                 "student_answer": student, "correct_answer": correct_ans}
            )

        total = len(req.questions) or 1
        profile = [
            {
                "topic": t,
                "correct": topic_correct.get(t, 0),
                "total": topic_totals[t],
                "mastery": round(topic_correct.get(t, 0) / topic_totals[t] * 100, 1),
            }
            for t in topic_totals
        ]
        weak_topics = [p["topic"] for p in profile if p["mastery"] < 60]

        # LLM-generated personalized recommendation.
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        rec_schema = {"recommendation": "<2-3 sentence personalized next-step advice>"}
        rec_prompt = (
            f"{lang_line}\n"
            f"A student took a {req.subject} diagnostic. Per-topic mastery: "
            f"{json.dumps(profile, ensure_ascii=False)}. Weak topics: {weak_topics}.\n"
            "Give brief, encouraging, concrete next-step advice. "
            f"Output ONLY JSON: {json.dumps(rec_schema)}"
        )
        recommendation = ""
        try:
            rec_raw = await llm_complete(rec_prompt, system_prompt="Output only valid JSON.")
            recommendation = _parse_json(rec_raw).get("recommendation", "")
        except Exception:  # noqa: BLE001
            recommendation = ""

        return {
            "subject": req.subject,
            "score": correct_count,
            "total": total,
            "percentage": round(correct_count / total * 100, 1),
            "profile": sorted(profile, key=lambda p: p["mastery"]),
            "weak_topics": weak_topics,
            "details": details,
            "recommendation": recommendation,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("diagnostic/grade error: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc)}


# ───────────────────────────────────────────────────────────────────────────
# POST /mistake-book/analyze — classify + explain a wrong answer, draft similar Q
# ───────────────────────────────────────────────────────────────────────────

class MistakeRequest(BaseModel):
    question: str
    wrong_answer: str = ""
    correct_answer: str = ""
    subject: str = ""
    language: str = "en"


@router.post("/mistake-book/analyze")
async def mistake_analyze(req: MistakeRequest) -> dict[str, Any]:
    """Analyze a wrong answer: tag the topic, explain the error, draft a similar question."""
    try:
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        schema = {
            "topic": "<the knowledge point this question tests>",
            "error_type": "<conceptual | careless | knowledge-gap | misread>",
            "explanation": "<why the wrong answer is wrong and how to think correctly>",
            "correct_answer": "<the correct answer with brief reasoning>",
            "similar_question": {
                "question": "<a new practice question testing the same point>",
                "answer": "<its answer>",
            },
            "review_tip": "<one tip to avoid this mistake next time>",
        }
        system_prompt = (
            "You are a supportive tutor analyzing a student's mistake. "
            "Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{lang_line}\n"
            + (f"Subject: {req.subject}.\n" if req.subject else "")
            + f"Question: {req.question}\n"
            + (f"Student's (wrong) answer: {req.wrong_answer}\n" if req.wrong_answer else "")
            + (f"Correct answer (if known): {req.correct_answer}\n" if req.correct_answer else "")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("mistake-book/analyze error: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════
# Extended learning ecosystem — additional tools
# ═══════════════════════════════════════════════════════════════════════════

def _lang_line(language: str) -> str:
    return "Respond in 繁體中文." if language == "zh" else "Respond in English."


# ── Step Solver ──────────────────────────────────────────────────────────────

class StepSolverRequest(BaseModel):
    problem: str
    subject: str = ""
    language: str = "en"


@router.post("/step-solver")
async def step_solver(req: StepSolverRequest) -> dict[str, Any]:
    """Solve any problem with an explained, step-by-step worked solution."""
    try:
        schema = {
            "key_idea": "<the main concept / strategy needed>",
            "steps": [{"step": "<short step title>", "detail": "<explanation of this step>"}],
            "final_answer": "<the final answer>",
            "common_pitfall": "<a mistake students often make here>",
        }
        system_prompt = (
            "You are a patient tutor who shows full working. Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            + (f"Subject: {req.subject}.\n" if req.subject else "")
            + f"Solve this problem step by step, explaining the reasoning at each step:\n{req.problem}\n\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("step-solver error: %s", exc)
        return {"error": str(exc)}


# ── Socratic Tutor (multi-turn guided questioning) ───────────────────────────

class SocraticTurn(BaseModel):
    role: str  # "student" | "tutor"
    content: str


class SocraticRequest(BaseModel):
    topic: str
    history: list[SocraticTurn] = []
    student_message: str
    language: str = "en"


@router.post("/socratic")
async def socratic(req: SocraticRequest) -> dict[str, Any]:
    """Guide the student toward understanding by asking questions, not giving answers."""
    try:
        convo = "\n".join(f"{t.role}: {t.content}" for t in req.history)
        schema = {
            "reply": "<your Socratic response — a guiding question or gentle hint, NOT the full answer>",
            "is_breakthrough": False,
            "encouragement": "<a brief encouraging note>",
        }
        system_prompt = (
            "You are a Socratic tutor. NEVER give the final answer directly. Ask probing "
            "questions and small hints that lead the student to discover it themselves. "
            "Only confirm the answer once the student has essentially reached it. "
            "Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Topic the student is learning: {req.topic}\n"
            + (f"Conversation so far:\n{convo}\n" if convo else "")
            + f"student: {req.student_message}\n\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("socratic error: %s", exc)
        return {"error": str(exc)}


# ── Flash Quiz (rapid MCQ; answers returned for client-side instant feedback) ─

class FlashQuizRequest(BaseModel):
    topic: str
    num_questions: int = 8
    difficulty: str = "medium"
    kb_name: str | None = None
    language: str = "en"


@router.post("/flash-quiz/generate")
async def flash_quiz(req: FlashQuizRequest) -> dict[str, Any]:
    """Generate rapid-fire MCQs with answers + explanations for instant feedback."""
    try:
        context = await _rag_retrieve(req.kb_name, req.topic)
        schema = {
            "topic": req.topic,
            "questions": [
                {"id": "q1", "question": "<question>", "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                 "answer": "A", "explanation": "<why this is correct>"}
            ],
        }
        system_prompt = "You write crisp multiple-choice quiz questions. Output ONLY valid JSON — no markdown fences."
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Create a {req.num_questions}-question rapid quiz on \"{req.topic}\" at {req.difficulty} difficulty. "
            "Each question has exactly 4 options and a short explanation.\n"
            + (f"\nUse this source material:\n{context[:4000]}\n" if context else "")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        quiz = _parse_json(raw)
        for i, q in enumerate(quiz.get("questions", [])):
            q.setdefault("id", f"q{i + 1}")
        quiz["grounded"] = bool(context)
        return quiz
    except Exception as exc:  # noqa: BLE001
        logger.error("flash-quiz error: %s", exc)
        return {"error": str(exc)}


# ── Cloze Practice (fill-in-the-blank) ───────────────────────────────────────

class ClozeRequest(BaseModel):
    topic: str = ""
    source_text: str = ""
    num_blanks: int = 6
    language: str = "en"


@router.post("/cloze")
async def cloze(req: ClozeRequest) -> dict[str, Any]:
    """Generate a fill-in-the-blank passage from a topic or pasted text."""
    try:
        schema = {
            "title": "<short title>",
            "text": "<a coherent passage where blanks are written as [[1]], [[2]], ...>",
            "blanks": [{"id": 1, "answer": "<answer>", "hint": "<a small hint>"}],
        }
        system_prompt = "You design cloze (fill-in-the-blank) exercises. Output ONLY valid JSON — no markdown fences."
        body = req.source_text or req.topic
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Create a cloze passage with {req.num_blanks} blanks "
            + (f"based on this text:\n{req.source_text[:4000]}\n" if req.source_text else f"about: {req.topic}\n")
            + "Mark each blank inline as [[1]], [[2]], etc. Blank out meaningful key terms.\n"
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("cloze error: %s", exc)
        return {"error": str(exc)}


# ── Past Paper Practice (RAG-grounded) ───────────────────────────────────────

class PastPaperRequest(BaseModel):
    kb_name: str
    subject: str = ""
    topic_focus: str = ""
    num_questions: int = 5
    language: str = "en"


@router.post("/past-paper")
async def past_paper(req: PastPaperRequest) -> dict[str, Any]:
    """Generate practice questions grounded in ingested past-paper knowledge bases."""
    try:
        query = req.topic_focus or req.subject or "exam questions"
        context = await _rag_retrieve(req.kb_name, query)
        schema = {
            "questions": [
                {"id": "q1", "topic": "<topic>", "question": "<question modelled on the past paper>",
                 "answer": "<model answer>", "marks": 4, "source_note": "<which part of the source it draws on>"}
            ],
        }
        system_prompt = (
            "You are an HKDSE examiner creating practice questions in the STYLE of real past papers. "
            "Base questions on the provided source material. Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Create {req.num_questions} exam-style practice questions"
            + (f" focused on {req.topic_focus}" if req.topic_focus else "")
            + f" for {req.subject or 'this subject'}.\n"
            + (f"\nPast-paper source material:\n{context[:5000]}\n" if context else "\n(No source retrieved — generate representative questions.)\n")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        result = _parse_json(raw)
        for i, q in enumerate(result.get("questions", [])):
            q.setdefault("id", f"q{i + 1}")
        result["grounded"] = bool(context)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("past-paper error: %s", exc)
        return {"error": str(exc)}


# ── Essay Outline Builder ────────────────────────────────────────────────────

class EssayOutlineRequest(BaseModel):
    prompt: str
    essay_type: str = "argumentative"  # argumentative | narrative | expository | letter
    language: str = "en"


@router.post("/essay-outline")
async def essay_outline(req: EssayOutlineRequest) -> dict[str, Any]:
    """Produce a thesis and structured outline for an essay prompt."""
    try:
        schema = {
            "thesis": "<a clear thesis / central idea>",
            "hook": "<an engaging opening idea>",
            "sections": [{"section": "<e.g. Body Paragraph 1>", "points": ["<point>", "<evidence/example>"]}],
            "conclusion_idea": "<how to conclude effectively>",
            "tips": ["<writing tip>"],
        }
        system_prompt = "You are a writing coach who builds clear essay outlines. Output ONLY valid JSON — no markdown fences."
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Build a {req.essay_type} essay outline for this prompt:\n{req.prompt}\n\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("essay-outline error: %s", exc)
        return {"error": str(exc)}


# ── Writing Coach (polish + explain) ─────────────────────────────────────────

class WritingCoachRequest(BaseModel):
    text: str
    focus: str = "all"  # grammar | style | clarity | all
    language: str = "en"


@router.post("/writing-coach")
async def writing_coach(req: WritingCoachRequest) -> dict[str, Any]:
    """Improve a piece of writing and explain each change."""
    try:
        schema = {
            "improved_text": "<the revised version>",
            "issues": [{"original": "<original phrase>", "suggestion": "<improved phrase>", "reason": "<why>"}],
            "score": 0,
            "summary": "<overall feedback in 1-2 sentences>",
        }
        system_prompt = "You are an encouraging writing coach. Output ONLY valid JSON — no markdown fences."
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Improve the following writing (focus: {req.focus}). Give a score out of 100, a clean improved "
            f"version, and itemize the key fixes.\n\nText:\n{req.text[:5000]}\n\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("writing-coach error: %s", exc)
        return {"error": str(exc)}


# ── Vocabulary Builder ───────────────────────────────────────────────────────

class VocabRequest(BaseModel):
    topic: str
    num_words: int = 10
    language: str = "en"


@router.post("/vocab-builder")
async def vocab_builder(req: VocabRequest) -> dict[str, Any]:
    """Build a vocabulary list with definitions, examples, and mnemonics."""
    try:
        schema = {
            "topic": req.topic,
            "words": [
                {"word": "<word/term>", "definition": "<concise definition>",
                 "example": "<example sentence>", "synonym": "<a synonym or related term>",
                 "mnemonic": "<a memory aid>"}
            ],
        }
        system_prompt = "You build study vocabulary lists. Output ONLY valid JSON — no markdown fences."
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Build a vocabulary list of {req.num_words} useful words/terms for: \"{req.topic}\".\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("vocab-builder error: %s", exc)
        return {"error": str(exc)}


# ── Feynman Self-Check ───────────────────────────────────────────────────────

class FeynmanRequest(BaseModel):
    concept: str
    explanation: str
    language: str = "en"


@router.post("/feynman")
async def feynman(req: FeynmanRequest) -> dict[str, Any]:
    """Evaluate a student's own explanation of a concept (Feynman technique)."""
    try:
        schema = {
            "score": 0,
            "understood": ["<things the student explained well>"],
            "gaps": ["<misconceptions or missing pieces>"],
            "feedback": "<constructive feedback>",
            "follow_up_question": "<a question to deepen understanding>",
        }
        system_prompt = (
            "You assess a student's understanding using the Feynman technique. Be specific about gaps. "
            "Output ONLY valid JSON — no markdown fences."
        )
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Concept: {req.concept}\n"
            f"Student's explanation in their own words:\n{req.explanation}\n\n"
            "Score their understanding out of 100, list what they got right, the gaps/misconceptions, "
            "and a follow-up question.\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("feynman error: %s", exc)
        return {"error": str(exc)}


# ── Concept Map ──────────────────────────────────────────────────────────────

class ConceptMapRequest(BaseModel):
    topic: str
    kb_name: str | None = None
    language: str = "en"


@router.post("/concept-map")
async def concept_map(req: ConceptMapRequest) -> dict[str, Any]:
    """Generate a concept map (nodes + relationships) for a topic."""
    try:
        context = await _rag_retrieve(req.kb_name, req.topic)
        schema = {
            "root": req.topic,
            "nodes": [{"id": "n1", "label": "<concept>", "description": "<short description>"}],
            "edges": [{"from": "n1", "to": "n2", "relation": "<relationship label>"}],
        }
        system_prompt = "You build concept maps for studying. Output ONLY valid JSON — no markdown fences."
        user_prompt = (
            f"{_lang_line(req.language)}\n"
            f"Build a concept map for: \"{req.topic}\". Include 6-10 nodes and the relationships between them.\n"
            + (f"\nGround it in this material:\n{context[:4000]}\n" if context else "")
            + f"\nOutput JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        result = _parse_json(raw)
        result["grounded"] = bool(context)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("concept-map error: %s", exc)
        return {"error": str(exc)}


# ── Translator & Glossary ────────────────────────────────────────────────────

class TranslatorRequest(BaseModel):
    text: str
    target_lang: str = "English"  # e.g. English | 繁體中文
    language: str = "en"


@router.post("/translator")
async def translator(req: TranslatorRequest) -> dict[str, Any]:
    """Translate academic text and extract a glossary of key terms."""
    try:
        schema = {
            "translation": "<the translated text>",
            "glossary": [{"term": "<key term in source>", "translation": "<its translation>", "note": "<usage note>"}],
        }
        system_prompt = "You are an academic translator. Output ONLY valid JSON — no markdown fences."
        user_prompt = (
            f"Translate the following text into {req.target_lang}, then extract a glossary of key academic "
            f"terms with their translations and brief usage notes.\n\nText:\n{req.text[:5000]}\n\n"
            + f"Output JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        return _parse_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("translator error: %s", exc)
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# V2 Optimizations — Deeper learning logic (multi-turn, verification, memory)
# ═══════════════════════════════════════════════════════════════════════════════

import hashlib
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── In-memory conversation store for Socratic sessions ─────────────────────

_socratic_sessions: dict[str, dict[str, Any]] = {}

_SOCRATIC_SYSTEM = """You are a Socratic tutor. Your goal is to guide the student to discover the answer themselves through carefully crafted questions — NEVER give the answer directly.

Rules:
- Ask ONE question at a time, building on the student's previous response.
- If the student's answer is partially correct, acknowledge what's right, then probe the gap.
- If the student is completely stuck after 2 attempts, give a small hint (not the answer).
- If the student demonstrates clear understanding, confirm it and move on to deepen their knowledge.
- Keep responses concise — 2-3 sentences max."""


class SocraticStartRequest(BaseModel):
    topic: str
    context: str = ""
    language: str = "en"


@router.post("/socratic/start")
async def socratic_start(req: SocraticStartRequest) -> dict[str, Any]:
    """Begin a multi-turn Socratic tutoring session. Returns the first question."""
    try:
        session_id = hashlib.sha256(f"{req.topic}{time.time()}".encode()).hexdigest()[:12]
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."

        intro_prompt = (
            f"{lang_line}\n"
            f"The student wants to understand: {req.topic}.\n"
            + (f"Context: {req.context}\n" if req.context else "")
            + "Start a Socratic tutoring session. First, briefly set the stage (1 sentence), "
            "then ask the FIRST guiding question to probe their understanding. "
            "Do NOT give the answer. Make them think.\n\n"
            "Return JSON: {\"intro\": \"<brief setup>\", \"question\": \"<first guiding question>\", \"hint\": \"<optional small hint or empty>\"}"
        )
        raw = await llm_complete(intro_prompt, system_prompt=_SOCRATIC_SYSTEM)
        result = _parse_json(raw)

        session = {
            "topic": req.topic,
            "language": req.language,
            "rounds": 0,
            "stuck_count": 0,
            "history": [],
            "current_question": result.get("question", ""),
            "understanding": "exploring",
            "created_at": datetime.now().isoformat(),
        }
        _socratic_sessions[session_id] = session

        return {
            "session_id": session_id,
            "intro": result.get("intro", ""),
            "question": result.get("question", ""),
            "hint": result.get("hint", ""),
            "round": 1,
        }
    except Exception as exc:
        logger.error("socratic/start error: %s", exc)
        return {"error": str(exc)}


class SocraticRespondRequest(BaseModel):
    session_id: str
    answer: str


@router.post("/socratic/respond")
async def socratic_respond(req: SocraticRespondRequest) -> dict[str, Any]:
    """Student responds → LLM evaluates → generates next question or concludes."""
    try:
        session = _socratic_sessions.get(req.session_id)
        if not session:
            return {"error": "Session not found — please start a new session."}

        session["rounds"] += 1
        session["history"].append({"round": session["rounds"], "answer": req.answer})
        lang_line = "Respond in 繁體中文." if session["language"] == "zh" else "Respond in English."

        # Determine if student is stuck
        stuck_markers = ["i don't know", "不知道", "no idea", "not sure", "idk", "不懂", "不会"]
        is_stuck = any(m in req.answer.lower() for m in stuck_markers) or len(req.answer.strip()) < 10
        if is_stuck:
            session["stuck_count"] += 1
        else:
            session["stuck_count"] = max(0, session["stuck_count"] - 1)

        # Build conversation history for prompt
        history_text = "\n".join(
            f"Q{h['round']}: {h.get('question', '')}\nA: {h['answer']}"
            for h in session["history"]
        )

        if session["stuck_count"] >= 2 or session["rounds"] >= 5:
            # Student is stuck or max rounds reached → give explanation + wrap up
            conclude_prompt = (
                f"{lang_line}\nTopic: {session['topic']}\n\n"
                f"Conversation history:\n{history_text}\n\n"
                f"The student is struggling (stuck count={session['stuck_count']}) or max rounds reached. "
                "Give a clear, concise explanation of the concept now, then suggest next steps.\n\n"
                "Return JSON: {\"conclusion\": \"<explanation>\", \"recommendation\": \"<what to practice next>\", \"complete\": true}"
            )
            raw = await llm_complete(conclude_prompt, system_prompt="Output only valid JSON.")
            result = _parse_json(raw)
            _socratic_sessions.pop(req.session_id, None)
            return {
                **result,
                "session_id": req.session_id,
                "round": session["rounds"],
                "complete": True,
            }

        # Continue the dialogue
        next_prompt = (
            f"{lang_line}\nTopic: {session['topic']}\n\n"
            f"Conversation history:\n{history_text}\n\n"
            f"The student just answered. Evaluate: is their understanding correct/partial/wrong? "
            "If correct → ask a follow-up question to deepen their understanding. "
            "If partial → acknowledge what's right, then probe the gap. "
            "If wrong → give a small hint (not the answer) and re-ask. "
            "If the student clearly understands → conclude with praise and a recommendation.\n\n"
            "Return JSON: {\"evaluation\": \"<correct|partial|wrong>\", \"question\": \"<next question or empty if done>\", \"hint\": \"<optional hint>\", \"complete\": true/false, \"praise\": \"<acknowledgment if earned>\"}"
        )
        raw = await llm_complete(next_prompt, system_prompt=_SOCRATIC_SYSTEM)
        result = _parse_json(raw)
        session["current_question"] = result.get("question", "")

        if result.get("complete"):
            _socratic_sessions.pop(req.session_id, None)

        return {
            **result,
            "session_id": req.session_id,
            "round": session["rounds"],
        }
    except Exception as exc:
        logger.error("socratic/respond error: %s", exc)
        return {"error": str(exc)}


# ── Concept Explainer v2 — with self-check verification ────────────────────

class ConceptVerifyRequest(BaseModel):
    concept: str
    original_explanation: str = ""  # the explanation that was shown to the student
    check_question: str             # the self-check question
    student_answer: str
    language: str = "en"


@router.post("/concept-explainer/verify")
async def concept_explainer_verify(req: ConceptVerifyRequest) -> dict[str, Any]:
    """Verify a student's answer to the self-check question from Concept Explainer."""
    try:
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
        verify_prompt = (
            f"{lang_line}\n"
            f"Concept: {req.concept}\n"
            f"Self-check question: {req.check_question}\n"
            f"Student's answer: {req.student_answer}\n\n"
            "Evaluate if the answer is correct/partial/wrong. "
            "If the student understands → praise and suggest a harder follow-up question. "
            "If partial → explain what's missing, but don't give the full answer — give a hint. "
            "If wrong → identify the specific misunderstanding and re-explain the key point briefly.\n\n"
            "Return JSON: {\"verdict\": \"<correct|partial|wrong>\", "
            "\"feedback\": \"<explanation>\", "
            "\"follow_up_question\": \"<new question or empty>\", "
            "\"re_explanation\": \"<brief re-explanation if needed, or empty>\"}"
        )
        raw = await llm_complete(verify_prompt, system_prompt="Output only valid JSON.")
        return _parse_json(raw)
    except Exception as exc:
        logger.error("concept-explainer/verify error: %s", exc)
        return {"error": str(exc)}


# ── Mistake Notebook v2 — persistent storage + SM-2 review scheduling ──────

_MISTAKE_PATH = Path(os.environ.get("DEEPTUTOR_DATA_DIR", "data")) / "user" / "mistakes.json"


def _load_mistakes() -> dict[str, Any]:
    if _MISTAKE_PATH.exists():
        try:
            with open(_MISTAKE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"mistakes": []}


def _save_mistakes(data: dict[str, Any]) -> None:
    _MISTAKE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MISTAKE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


class MistakeRecordRequest(BaseModel):
    question: str
    student_answer: str = ""
    correct_answer: str = ""
    topic: str = ""
    subject: str = ""
    error_type: str = ""  # conceptual | careless | knowledge-gap | misread
    language: str = "en"


@router.post("/mistake-book/record")
async def mistake_record(req: MistakeRecordRequest) -> dict[str, Any]:
    """Record a mistake with SM-2 scheduling state."""
    try:
        data = _load_mistakes()
        now = datetime.now()
        mistake = {
            "id": hashlib.sha256(f"{req.question}{req.topic}{now.isoformat()}".encode()).hexdigest()[:10],
            "question": req.question,
            "student_answer": req.student_answer,
            "correct_answer": req.correct_answer,
            "topic": req.topic,
            "subject": req.subject,
            "error_type": req.error_type,
            "created_at": now.isoformat(),
            # SM-2 state
            "interval": 1,        # days until next review
            "ease_factor": 2.5,   # default SM-2 ease factor
            "repetitions": 0,     # times reviewed correctly
            "next_review": (now + timedelta(days=1)).isoformat(),
            "review_count": 0,
        }

        # Also get LLM analysis for richer feedback
        if req.student_answer and req.correct_answer:
            lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."
            analyze_prompt = (
                f"{lang_line}\n"
                + (f"Subject: {req.subject}.\n" if req.subject else "")
                + f"Question: {req.question}\n"
                + (f"Student answer: {req.student_answer}\n" if req.student_answer else "")
                + (f"Correct answer: {req.correct_answer}\n" if req.correct_answer else "")
                + (f"Error type: {req.error_type}.\n" if req.error_type else "")
                + "Output JSON: {\"root_cause\": \"<why the student made this mistake>\", "
                "\"fix_tip\": \"<one specific tip to avoid this mistake>\", "
                "\"similar_question\": \"<a new practice question on the same concept>\"}"
            )
            try:
                raw = await llm_complete(analyze_prompt, system_prompt="Output only valid JSON.")
                analysis = _parse_json(raw)
                mistake["root_cause"] = analysis.get("root_cause", "")
                mistake["fix_tip"] = analysis.get("fix_tip", "")
                mistake["similar_question"] = analysis.get("similar_question", "")
            except Exception:
                pass

        data["mistakes"].append(mistake)
        _save_mistakes(data)

        return {
            "recorded": True,
            "mistake_id": mistake["id"],
            "next_review": mistake["next_review"],
            "total_mistakes": len(data["mistakes"]),
            **({k: mistake[k] for k in ["root_cause", "fix_tip", "similar_question"]} if "root_cause" in mistake else {}),
        }
    except Exception as exc:
        logger.error("mistake-book/record error: %s", exc)
        return {"error": str(exc)}


class MistakeReviewRequest(BaseModel):
    limit: int = 10
    topic: str = ""
    subject: str = ""


@router.get("/mistake-book/review")
async def mistake_review(limit: int = 10, topic: str = "", subject: str = "") -> dict[str, Any]:
    """Get mistakes that are due for review (next_review <= now)."""
    try:
        data = _load_mistakes()
        now = datetime.now()
        due = []
        for m in data["mistakes"]:
            next_review = datetime.fromisoformat(m.get("next_review", now.isoformat()))
            if next_review <= now:
                if topic and m.get("topic") != topic:
                    continue
                if subject and m.get("subject") != subject:
                    continue
                due.append(m)
            if len(due) >= limit:
                break

        # Group by topic for summary
        topic_counts: dict[str, int] = {}
        for m in data["mistakes"]:
            t = m.get("topic", "Unknown")
            topic_counts[t] = topic_counts.get(t, 0) + 1

        return {
            "due_count": len(due),
            "total_count": len(data["mistakes"]),
            "due_reviews": due,
            "topic_summary": sorted(topic_counts.items(), key=lambda x: -x[1])[:10],
        }
    except Exception as exc:
        logger.error("mistake-book/review error: %s", exc)
        return {"error": str(exc)}


class MistakeUpdateRequest(BaseModel):
    mistake_id: str
    rating: int  # 0=again, 1=hard, 2=good, 3=easy


@router.post("/mistake-book/update")
async def mistake_update(req: MistakeUpdateRequest) -> dict[str, Any]:
    """Update a mistake's SM-2 state after review. Called after student re-attempts."""
    try:
        data = _load_mistakes()
        now = datetime.now()
        found = None
        for m in data["mistakes"]:
            if m["id"] == req.mistake_id:
                found = m
                break
        if not found:
            return {"error": f"Mistake {req.mistake_id} not found"}

        # SM-2 algorithm
        q_map = {0: 0, 1: 3, 2: 4, 3: 5}
        q = q_map.get(req.rating, 3)

        if q < 3:
            # Failed — reset
            found["repetitions"] = 0
            found["interval"] = 1
        else:
            if found["repetitions"] == 0:
                found["interval"] = 1
            elif found["repetitions"] == 1:
                found["interval"] = 6
            else:
                found["interval"] = round(found["interval"] * found["ease_factor"])
            found["repetitions"] += 1

        found["ease_factor"] = max(1.3, found["ease_factor"] + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        found["next_review"] = (now + timedelta(days=found["interval"])).isoformat()
        found["review_count"] = found.get("review_count", 0) + 1
        found["last_reviewed"] = now.isoformat()

        _save_mistakes(data)

        # If mastered (interval >= 21 days), remove from active review
        if found["interval"] >= 21:
            data["mistakes"].remove(found)
            _save_mistakes(data)
            return {
                "updated": True,
                "mistake_id": req.mistake_id,
                "interval": found["interval"],
                "next_review": found["next_review"],
                "mastered": True,
            }

        return {
            "updated": True,
            "mistake_id": req.mistake_id,
            "interval": found["interval"],
            "next_review": found["next_review"],
            "ease_factor": round(found["ease_factor"], 2),
            "mastered": False,
        }
    except Exception as exc:
        logger.error("mistake-book/update error: %s", exc)
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# V3 — Cross-tool pipelines (Diagnosis→Planner, Mistakes→ConceptMap)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Diagnosis → Study Planner bridge ───────────────────────────────────────

class DiagnosisToPlanRequest(BaseModel):
    subject: str
    weak_topics: list[str]
    profile: list[dict[str, Any]]  # [{topic, mastery, correct, total}]
    days_until_exam: int = 14
    hours_per_day: float = 2.0
    language: str = "en"


@router.post("/diagnostic/to-plan")
async def diagnostic_to_plan(req: DiagnosisToPlanRequest) -> dict[str, Any]:
    """Convert diagnostic results into a targeted revision plan focused on weak areas."""
    try:
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."

        # Build a rich weak-area profile for the planner
        weak_detail = "\n".join(
            f"- {p['topic']}: mastery {p['mastery']}% ({p['correct']}/{p['total']} correct)"
            for p in req.profile if p["mastery"] < 70
        )

        schema = {
            "diagnostic_summary": "<one-sentence overview of student's current level>",
            "priority_areas": ["<weak topic 1>", "<weak topic 2>"],
            "daily_hours": req.hours_per_day,
            "days": [
                {
                    "day": 1,
                    "focus": "<weak topic to target>",
                    "tasks": ["<concrete remediation task>", "<practice task>"],
                    "review_tasks": ["<previously covered topic to review>"],
                    "milestone": "<measurable goal for the day>",
                }
            ],
            "recommended_resources": ["<suggestion for extra practice>"],
        }

        system_prompt = (
            "You are an expert HKDSE study coach. Create a targeted remediation plan "
            "that focuses on the student's weakest areas first, then gradually interleaves "
            "review. Output ONLY valid JSON — no markdown fences."
        )

        user_prompt = (
            f"{lang_line}\n"
            f"Subject: {req.subject}.\n"
            f"Days until exam: {req.days_until_exam}.\n"
            f"Study time: {req.hours_per_day} hours/day.\n\n"
            f"Diagnostic results — weak areas:\n{weak_detail}\n\n"
            f"Full profile: {json.dumps(req.profile, ensure_ascii=False)}\n\n"
            f"Create a {req.days_until_exam}-day plan that:\n"
            f"1. Spends 60% of time on weak topics first\n"
            f"2. Interleaves review of previously covered material\n"
            f"3. Includes a mock/review day every 5 days\n"
            f"4. Ends with light consolidation the day before the exam\n\n"
            f"Output JSON:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        plan = _parse_json(raw)
        plan["weak_topics_input"] = req.weak_topics
        plan["generated_from"] = "diagnostic"
        return plan

    except Exception as exc:
        logger.error("diagnostic/to-plan error: %s", exc)
        return {"error": str(exc)}


# ── Mistakes → Concept Map bridge ──────────────────────────────────────────

class MistakesToConceptMapRequest(BaseModel):
    topic_summary: list[list[Any]]  # [[topic, count], ...] from mistake-book/review
    subject: str = ""
    language: str = "en"


@router.post("/mistake-book/to-concept-map")
async def mistakes_to_concept_map(req: MistakesToConceptMapRequest) -> dict[str, Any]:
    """Generate a concept map from accumulated mistakes, highlighting weak areas."""
    try:
        lang_line = "Respond in 繁體中文." if req.language == "zh" else "Respond in English."

        topics_text = "\n".join(
            f"- {item[0]}: {item[1]} mistakes" if isinstance(item, list) and len(item) >= 2
            else f"- {item}"
            for item in req.topic_summary[:10]
        )

        schema = {
            "mermaid": "graph TD\n  Root[Weak Areas] --> T1[Topic1]\n  ...",
            "analysis": "<why these topics are connected and where to focus>",
            "weak_nodes": ["<topic with most mistakes>"],
            "prerequisites": [{"topic": "<topic>", "depends_on": ["<prerequisite 1>"]}],
        }

        system_prompt = (
            "You are a knowledge graph expert. Create a concept map in Mermaid format "
            "showing the relationships between the student's weak topics. "
            "Output ONLY valid JSON — no markdown fences."
        )

        user_prompt = (
            f"{lang_line}\n"
            + (f"Subject: {req.subject}.\n" if req.subject else "")
            + f"The student made mistakes on these topics (with error counts):\n{topics_text}\n\n"
            "Create a concept map that:\n"
            "1. Groups related weak topics under common parent concepts\n"
            "2. Marks prerequisite dependencies (e.g. if 'quadratic equations' is weak, "
            "maybe 'algebra basics' is a hidden gap)\n"
            "3. Annotates each node with the mistake count\n"
            "4. Uses Mermaid graph TD syntax for the mermaid field\n\n"
            f"Output JSON:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        result = _parse_json(raw)
        result["source"] = "mistake-book"
        result["topic_count"] = len(req.topic_summary)
        return result

    except Exception as exc:
        logger.error("mistake-book/to-concept-map error: %s", exc)
        return {"error": str(exc)}


# ── Essay model answer generator (5** exemplar) ────────────────────────────

class ModelAnswerRequest(BaseModel):
    title: str = ""
    essay: str = ""          # student's essay (optional — for comparison)
    genre: str = "argumentative"
    language: str = "zh"     # zh = Chinese, en = English
    scoring_criteria: str = ""  # optional custom rubric


@router.post("/essay/model-answer")
async def essay_model_answer(req: ModelAnswerRequest) -> dict[str, Any]:
    """Generate a 5** model answer for comparison with the student's essay."""
    try:
        is_chinese = req.language == "zh"
        genre_label = (
            {"narrative": "記敘文", "argumentative": "議論文", "descriptive": "描寫文"}.get(req.genre, req.genre)
            if is_chinese
            else {"argument": "argumentative essay", "letter": "formal letter",
                  "report": "report", "article": "feature article"}.get(req.genre, req.genre)
        )

        schema = {
            "model_essay": "<full 5** model essay in the same genre, ~650 words>",
            "key_features": ["<what makes this essay top-tier: e.g. sophisticated vocabulary>"],
            "comparison_notes": ["<specific gap between the student's essay and the model>"] if req.essay else [],
            "scoring_breakdown": {"content": "<score/40 and why>", "expression": "<score/40 and why>", "organization": "<score/20 and why>"} if is_chinese else {"content": "<score/7 and why>", "language": "<score/7 and why>", "organisation": "<score/7 and why>"},
            "learnable_techniques": ["<technique 1 the student can apply immediately>"],
        }

        lang_line = "用繁體中文回應。" if is_chinese else "Respond in English."
        system_prompt = (
            "You are an HKDSE examiner and expert essay writer. Write a model 5** essay "
            "that demonstrates the highest level of writing. Output ONLY valid JSON — no markdown fences."
        )

        comparison_block = ""
        if req.essay:
            comparison_block = (
                f"\nStudent's essay (for comparison):\n{req.essay[:2000]}\n"
                "Please include comparison_notes showing specific gaps between the student's essay and the model.\n"
            )

        rubric_block = req.scoring_criteria or (
            "HKDSE Chinese Paper 2 rubric: Content (40), Expression (40), Organisation (20)"
            if is_chinese
            else "HKDSE English Paper 2: Content (7), Language (7), Organisation (7)"
        )

        user_prompt = (
            f"{lang_line}\n"
            f"Write a 5** {genre_label} on the topic: {req.title or '(choose an appropriate HKDSE topic)'}.\n"
            f"Scoring criteria: {rubric_block}\n"
            f"{comparison_block}"
            "The model essay should demonstrate:\n"
            "- Deep, original ideas with concrete examples\n"
            "- Sophisticated vocabulary and varied sentence structures\n"
            "- Clear organisation with smooth transitions\n"
            "- A distinctive voice and mature writing style\n\n"
            f"Output JSON:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )

        raw = await llm_complete(user_prompt, system_prompt=system_prompt)
        result = _parse_json(raw)
        result["genre"] = req.genre
        result["title"] = req.title
        return result

    except Exception as exc:
        logger.error("essay/model-answer error: %s", exc)
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════════
# Teacher Dashboard — aggregate all tool data into a single view
# ═══════════════════════════════════════════════════════════════════════════════

_DIAGNOSTIC_LOG_PATH = Path(os.environ.get("DEEPTUTOR_DATA_DIR", "data")) / "user" / "diagnostic_log.json"


def _load_diagnostic_log() -> list[dict[str, Any]]:
    if _DIAGNOSTIC_LOG_PATH.exists():
        try:
            with open(_DIAGNOSTIC_LOG_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_diagnostic_log(log: list[dict[str, Any]]) -> None:
    _DIAGNOSTIC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_DIAGNOSTIC_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False, default=str)


class LogDiagnosticRequest(BaseModel):
    subject: str
    score: int
    total: int
    percentage: float
    weak_topics: list[str]
    profile: list[dict[str, Any]]  # [{topic, mastery, correct, total}]


@router.post("/dashboard/log-diagnostic")
async def log_diagnostic(req: LogDiagnosticRequest) -> dict[str, Any]:
    """Log a completed diagnostic for dashboard tracking."""
    try:
        log = _load_diagnostic_log()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "subject": req.subject,
            "score": req.score,
            "total": req.total,
            "percentage": req.percentage,
            "weak_topics": req.weak_topics,
            "profile": req.profile,
        }
        log.append(entry)
        # Keep last 50 entries
        if len(log) > 50:
            log = log[-50:]
        _save_diagnostic_log(log)
        return {"logged": True, "total_entries": len(log)}
    except Exception as exc:
        logger.error("dashboard/log-diagnostic error: %s", exc)
        return {"error": str(exc)}


@router.get("/dashboard/overview")
async def dashboard_overview() -> dict[str, Any]:
    """Aggregate data from all tools for the teacher dashboard."""
    try:
        # ── Mistakes data ──
        mistakes_data = _load_mistakes()
        all_mistakes = mistakes_data.get("mistakes", [])
        active_mistakes = [m for m in all_mistakes if datetime.fromisoformat(m.get("next_review", "")) <= datetime.now()]
        mastered = [m for m in all_mistakes if m.get("interval", 0) >= 21]

        # Topic heatmap from mistakes
        topic_counts: dict[str, int] = {}
        for m in all_mistakes:
            t = m.get("topic", "Unknown")
            topic_counts[t] = topic_counts.get(t, 0) + 1

        # Error type distribution
        error_types: dict[str, int] = {}
        for m in all_mistakes:
            et = m.get("error_type", "unknown")
            error_types[et] = error_types.get(et, 0) + 1

        # ── Diagnostic log ──
        diag_log = _load_diagnostic_log()

        # Progress over time (last 10 diagnostics)
        progress = [
            {"date": d["timestamp"][:10], "subject": d["subject"],
             "percentage": d["percentage"], "weak_topics": d["weak_topics"]}
            for d in diag_log[-10:]
        ]

        # ── KB stats ──
        kb_info = {}
        try:
            from deeptutor.knowledge.manager import KnowledgeBaseManager
            mgr = KnowledgeBaseManager()
            for kb in mgr.list_knowledge_bases():
                info = mgr.get_info(kb)
                kb_info[kb] = {
                    "status": info.get("status"),
                    "documents": info.get("statistics", {}).get("raw_documents", 0),
                }
        except Exception:
            kb_info = {"error": "Could not load KB data"}

        # ── Aggregate topic weakness from all sources ──
        all_weak_topics: dict[str, int] = {}
        # From mistakes
        for t, c in topic_counts.items():
            all_weak_topics[t] = all_weak_topics.get(t, 0) + c
        # From diagnostics
        for d in diag_log:
            for t in d.get("weak_topics", []):
                all_weak_topics[t] = all_weak_topics.get(t, 0) + 1

        sorted_weak = sorted(all_weak_topics.items(), key=lambda x: -x[1])[:15]

        # ── Recommended next actions ──
        actions = []
        if active_mistakes:
            actions.append({"action": "Review due mistakes", "count": len(active_mistakes),
                           "link": "/market/mistake-book", "priority": "high"})
        if sorted_weak:
            top_weak = sorted_weak[0]
            actions.append({"action": f"Focus drill on: {top_weak[0]}", "count": top_weak[1],
                           "link": "/market/flash-quiz", "priority": "high"})
        if len(diag_log) >= 2:
            last = diag_log[-1]
            prev = diag_log[-2]
            if last["percentage"] < prev["percentage"]:
                actions.append({"action": "Score declining — schedule review session",
                               "link": "/market/study-planner", "priority": "warning"})
        actions.append({"action": "Generate targeted practice paper",
                       "link": "/market/paper-forge", "priority": "normal"})

        return {
            "overview": {
                "total_mistakes": len(all_mistakes),
                "active_reviews": len(active_mistakes),
                "mastered_topics": len(mastered),
                "diagnostics_completed": len(diag_log),
                "knowledge_bases": len(kb_info),
            },
            "topic_heatmap": [{"topic": t, "count": c} for t, c in sorted_weak],
            "error_type_distribution": error_types,
            "progress": progress,
            "kb_status": kb_info,
            "recommended_actions": actions,
        }
    except Exception as exc:
        logger.error("dashboard/overview error: %s", exc)
        return {"error": str(exc)}
