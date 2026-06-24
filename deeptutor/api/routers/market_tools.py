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
