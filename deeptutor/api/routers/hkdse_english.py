"""HKDSE English Language — 英文科 API (Paper Generator + Essay Coach)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import statistics
import traceback
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.services.llm import complete as llm_complete
from deeptutor.services.llm import stream as llm_stream

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


# ═══════════════════════════════════════════════════════════════════════════════
# F4 — Oral Practice (Paper 4)
# ═══════════════════════════════════════════════════════════════════════════════

_ORAL_TOPICS_CACHE: list[dict[str, Any]] | None = None


def _load_oral_topics() -> list[dict[str, Any]]:
    """Load DSE Paper 4 topics from JSON. Caches after first load."""
    global _ORAL_TOPICS_CACHE
    if _ORAL_TOPICS_CACHE is not None:
        return _ORAL_TOPICS_CACHE
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "oral_topics.json")
    path = os.path.abspath(path)
    try:
        with open(path) as f:
            data = json.load(f)
        _ORAL_TOPICS_CACHE = data.get("topics", [])
        logger.info("Loaded %d oral topics from %s", len(_ORAL_TOPICS_CACHE), path)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load oral topics from %s: %s. Using fallback.", path, e)
        _ORAL_TOPICS_CACHE = []
    return _ORAL_TOPICS_CACHE


# ═══════════════════════════════════════════════════════════════════════════════
# F4a — Random Topic Selection
# ═══════════════════════════════════════════════════════════════════════════════

class OralTopicRequest(BaseModel):
    category: str


_CATEGORY_TOPIC_LABELS: dict[str, str] = {
    "education": "Education",
    "technology": "Technology",
    "environment": "Environment",
    "social_issues": "Social Issues & Culture",
}


@router.post("/oral-topics")
async def oral_topics(req: OralTopicRequest) -> dict[str, Any]:
    """Select a random topic from the given category."""
    if req.category not in _CATEGORY_TOPIC_LABELS:
        return {"error": f"Invalid category: {req.category}"}

    topics = _load_oral_topics()
    candidates = [t for t in topics if t.get("category") == req.category]

    if not candidates:
        return {
            "topic_id": f"fallback_{req.category}",
            "topic": _CATEGORY_TOPIC_LABELS.get(req.category, req.category),
            "article": "",
            "discussion_task": "",
            "guiding_questions": [],
            "part_b_questions": [
                "What are your views on this topic?",
                "Can you share a personal experience?",
            ],
            "category": req.category,
        }

    chosen = random.choice(candidates)
    return {
        "topic_id": chosen.get("id", f"{req.category}_random"),
        "topic": chosen.get("topic", ""),
        "article": chosen.get("prompt", ""),
        "discussion_task": chosen.get("discussion_task", ""),
        "guiding_questions": chosen.get("guiding_questions", []),
        "part_b_questions": chosen.get("part_b_questions", []),
        "category": req.category,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# F4b — Discussion Turns
# ═══════════════════════════════════════════════════════════════════════════════

class OralTurnRequest(BaseModel):
    topic_id: str = ""
    history: list[dict[str, str]] = []
    phase: str = "discussion"  # discussion | individual_response


def _format_topic_for_prompt(topic_id: str) -> str:
    """Look up a topic by ID and format it for the LLM prompt."""
    topics = _load_oral_topics()
    for t in topics:
        if t.get("id") == topic_id:
            parts = [f"Discussion Topic: {t.get('topic', '')}"]
            article = (t.get("prompt") or "").strip()
            if article:
                parts.append(f"\nBackground Article:\n{article}")
            task = (t.get("discussion_task") or "").strip()
            if task:
                parts.append(f"\nDiscussion Task:\n{task}")
            questions = t.get("guiding_questions", [])
            if questions:
                parts.append("\nGuiding Questions:")
                for q in questions:
                    parts.append(f"  - {q}")
            return "\n".join(parts)
    return ""


_PERSONALITY_MAP = {
    "candidate_a": "confident and direct",
    "candidate_b": "thoughtful and analytical",
    "candidate_c": "supportive and agreeable",
}

_USER_TURN_THRESHOLD = 5
_MAX_CONSECUTIVE_AI = 2


def _build_oral_system_prompt() -> str:
    return (
        "You help simulate an HKDSE English Paper 4 group discussion (Speaking).\n\n"
        "IMPORTANT: You will be told which role to play in each turn. "
        "Your output must be ONLY that person's spoken words — "
        "no labels, no headers, no explanations, no formatting.\n\n"
        "RULES:\n"
        "- Speak naturally, 30-70 words, like a real conversation.\n"
        "- Do NOT output anything except the speech itself.\n"
        "- Do NOT say 'Candidate A:', 'I think', or similar framing."
    )


def _build_part_a_prompt(speaker: str, req: OralTurnRequest) -> str:
    """Build prompt for a Part A group discussion turn. Speaker is pre-determined by backend."""
    topic_context = _format_topic_for_prompt(req.topic_id) if req.topic_id else ""
    personality = _PERSONALITY_MAP.get(speaker, "natural")

    parts = []
    if topic_context:
        parts.append(f"CONTEXT:\n{topic_context}")

    if not req.history:
        parts.append(
            f"You are {speaker.replace('_', ' ').title()} — a {personality} student. "
            "This is the very first turn. Open the discussion by introducing the topic "
            "and sharing your first opinion. Speak naturally in 30-70 words."
        )
    else:
        parts.append("CONVERSATION SO FAR:")
        for msg in req.history:
            label = msg["speaker"].replace("_", " ").title()
            parts.append(f"{label}: {msg['content']}")

        last_msg = req.history[-1]
        parts.append(
            f"\nYou are {speaker.replace('_', ' ').title()} — a {personality} student. "
            f"The user just said: \"{last_msg['content']}\"\n\n"
            "Acknowledge what the last person said, then add your own point. "
            "30-70 words, spoken English. Respond naturally to the discussion."
        )

    return "\n\n".join(parts)


def _build_examiner_prompt(req: OralTurnRequest) -> str:
    """Build prompt for Part B — examiner asks the student a follow-up question."""
    topic_context = _format_topic_for_prompt(req.topic_id) if req.topic_id else ""

    parts = []
    if topic_context:
        parts.append(f"CONTEXT:\n{topic_context}")
    parts.append("GROUP DISCUSSION SO FAR:")
    for msg in req.history:
        label = msg["speaker"].replace("_", " ").title()
        parts.append(f"{label}: {msg['content']}")

    parts.append(
        "\nYou are an HKDSE English examiner. Based on the group discussion above, "
        "ask the student ONE follow-up question about the topic. "
        "The question should invite the student to explain their personal views or experiences. "
        "Output ONLY the question text — no labels, no greetings, no commentary."
    )

    return "\n\n".join(parts)


def _build_examiner_feedback_prompt(req: OralTurnRequest) -> str:
    """Build prompt for the examiner's brief wrap-up after user answers Part B."""
    topic_context = _format_topic_for_prompt(req.topic_id) if req.topic_id else ""

    parts = []
    if topic_context:
        parts.append(f"CONTEXT:\n{topic_context}")
    parts.append("CONVERSATION SO FAR:")
    for msg in req.history:
        label = msg["speaker"].replace("_", " ").title()
        parts.append(f"{label}: {msg['content']}")

    last_msg = req.history[-1]
    parts.append(
        f"\nYou are an HKDSE English examiner. "
        f"The student just answered your follow-up question: \"{last_msg['content']}\"\n\n"
        "Briefly acknowledge the student's answer (1-2 sentences). "
        "Then say the discussion is complete. "
        "Output ONLY the spoken words — no labels."
    )

    return "\n\n".join(parts)


def _count_user_turns(history: list[dict]) -> int:
    """Count how many times the user has spoken."""
    return sum(1 for m in history if m.get("speaker") == "candidate_d")


def _get_last_ai_speaker(history: list[dict]) -> str | None:
    """Get the last AI speaker from history end."""
    for msg in reversed(history):
        s = msg.get("speaker", "")
        if s in ("candidate_a", "candidate_b", "candidate_c"):
            return s
    return None


def _count_consecutive_ai(history: list[dict]) -> int:
    """Count consecutive AI turns at the end of history."""
    count = 0
    for msg in reversed(history):
        s = msg.get("speaker", "")
        if s in ("candidate_a", "candidate_b", "candidate_c"):
            count += 1
        else:
            break
    return count


def _pick_next_ai_speaker(history: list[dict]) -> str:
    """Pick next AI speaker via weighted random, favoring less-spoken candidates."""
    counts = {"candidate_a": 0, "candidate_b": 0, "candidate_c": 0}
    for msg in history:
        s = msg.get("speaker", "")
        if s in counts:
            counts[s] += 1

    last_ai = _get_last_ai_speaker(history)

    # Don't repeat the same speaker
    available = {k: v for k, v in counts.items() if k != last_ai}
    if not available:
        available = dict(counts)

    # Weight: higher = less-spoken
    max_count = max(available.values())
    weights = {k: max(1, max_count - v + 1) for k, v in available.items()}

    speakers = list(weights.keys())
    speaker_weights = [weights[k] for k in speakers]
    return random.choices(speakers, weights=speaker_weights, k=1)[0]


def _examiner_has_spoken(history: list[dict]) -> bool:
    """Check if the examiner has asked a Part B question."""
    return any(m.get("speaker") == "examiner" for m in history)


@router.post("/oral-turn")
async def oral_turn(req: OralTurnRequest):
    """Generate the next AI turn.

    Backend determines ALL structural metadata (speaker, continues, phase)
    before calling the LLM. The LLM only outputs spoken text — no headers.
    """

    user_turns = _count_user_turns(req.history)

    # ── Determine phase and speaker BEFORE calling LLM ──────────────
    if user_turns >= _USER_TURN_THRESHOLD and not _examiner_has_spoken(req.history):
        # ── Transition: Part A done → generate Part B examiner question ──
        speaker = "examiner"
        continues = False
        next_phase = "individual_response"
        next_speaker = "candidate_d"  # user answers next
        prompt = _build_examiner_prompt(req)
        system_prompt = _build_oral_system_prompt()

    elif _examiner_has_spoken(req.history):
        # ── Part B completed → brief wrap-up, then feedback ──
        speaker = "examiner"
        continues = False
        next_phase = "feedback"
        next_speaker = "feedback"
        prompt = _build_examiner_feedback_prompt(req)
        system_prompt = _build_oral_system_prompt()

    else:
        # ── Part A normal discussion turn ──
        speaker = _pick_next_ai_speaker(req.history)
        con_ai = _count_consecutive_ai(req.history)
        continues = con_ai < _MAX_CONSECUTIVE_AI - 1  # True until 1 before limit

        # Next phase: stay in discussion unless threshold reached
        next_phase = "discussion"
        next_speaker = "candidate_d"  # user's turn (default)

        if continues:
            # Another AI follows
            if speaker == "candidate_a":
                next_speaker = "candidate_b"
            elif speaker == "candidate_b":
                next_speaker = "candidate_c"
            else:
                next_speaker = "candidate_a"
        else:
            next_speaker = "candidate_d"

        prompt = _build_part_a_prompt(speaker, req)
        system_prompt = _build_oral_system_prompt()

    # ── Stream the LLM output (pure speech, no parsing needed) ──────
    async def _stream():
        try:
            yield json.dumps({"type": "turn_start"}) + "\n"

            content_chunks: list[str] = []
            async for chunk in llm_stream(prompt, system_prompt=system_prompt):
                content_chunks.append(chunk)
                yield json.dumps({"type": "chunk", "content": chunk}) + "\n"

            content = "".join(content_chunks).strip()

            yield json.dumps({
                "type": "turn_end",
                "speaker": speaker,
                "content": content,
                "next_speaker": next_speaker,
                "continues": continues,
                "phase": next_phase,
            }) + "\n"

        except Exception as e:
            logger.error(f"Oral turn error: {e}\n{traceback.format_exc()}")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


# ═══════════════════════════════════════════════════════════════════════════════
# F4c — Feedback
# ═══════════════════════════════════════════════════════════════════════════════

_ORAL_FEEDBACK_SCHEMA = {
    "communication": {"score": 4, "max_score": 7, "comment": ""},
    "language": {"score": 4, "max_score": 7, "comment": ""},
    "ideas_organisation": {"score": 4, "max_score": 7, "comment": ""},
    "pronunciation_delivery": {"score": 0, "max_score": 7},
    "total_score": 12,
    "max_score": 28,
    "percentage": 42.9,
    "strengths": [],
    "improvements": [],
    "overall_comment": "",
    "model_excerpt": "",
}


def _build_oral_feedback_system_prompt() -> str:
    return (
        "You are an HKDSE English Language Paper 4 examiner. "
        "Evaluate the user's performance in a group discussion "
        "according to official HKDSE Speaking marking criteria. "
        "Provide specific references to what the user said. "
        "Output ONLY valid JSON — no markdown fences."
    )


def _build_oral_feedback_user_prompt(history: list[dict[str, str]], topic_id: str) -> str:
    topic_context = _format_topic_for_prompt(topic_id) if topic_id else ""
    conversation = "\n".join(
        f"{m['speaker'].replace('_', ' ').title()}: {m['content']}"
        for m in history
    )
    context_block = f"\nTopic:\n{topic_context}\n\n" if topic_context else "\n"
    return (
        f"Evaluate the user's performance in this HKDSE Paper 4 group discussion.{context_block}"
        f"Full Conversation:\n{conversation}\n\n"
        f"HKDSE Paper 4 Speaking Marking Criteria (max 28):\n\n"
        f"1. Communication Strategies (7 marks):\n"
        f"   - Initiating, maintaining, and closing discussions\n"
        f"   - Turn-taking, negotiating meaning, responding appropriately\n\n"
        f"2. Language (7 marks):\n"
        f"   - Range and accuracy of vocabulary\n"
        f"   - Grammatical accuracy and sentence variety\n\n"
        f"3. Ideas and Organisation (7 marks):\n"
        f"   - Relevance and depth of ideas\n"
        f"   - Logical organisation of arguments\n\n"
        f"4. Pronunciation and Delivery (7 marks) — [Voice feature — mark as 0/7]\n\n"
        f"Return JSON matching this schema:\n"
        f"{json.dumps(_ORAL_FEEDBACK_SCHEMA, ensure_ascii=False, indent=2)}"
    )


@router.post("/oral-feedback")
async def oral_feedback(req: OralTurnRequest) -> dict[str, Any]:
    """Generate overall feedback for the oral practice session."""
    try:
        raw = await llm_complete(
            _build_oral_feedback_user_prompt(req.history, req.topic_id),
            system_prompt=_build_oral_feedback_system_prompt(),
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            raw_lines = cleaned.splitlines()
            cleaned = "\n".join(raw_lines[1:-1] if raw_lines[-1].strip() == "```" else raw_lines[1:])
        result: dict[str, Any] = json.loads(cleaned)
        for dim in ("communication", "language", "ideas_organisation", "pronunciation_delivery"):
            if dim not in result:
                result[dim] = {"score": 0, "max_score": 7, "comment": ""}
        if "total_score" not in result:
            result["total_score"] = sum(result.get(d, {}).get("score", 0)
                                        for d in ("communication", "language", "ideas_organisation", "pronunciation_delivery"))
        result.setdefault("max_score", 28)
        if "percentage" not in result and result.get("max_score", 0) > 0:
            result["percentage"] = round(result["total_score"] / result["max_score"] * 100, 1)
        result.setdefault("strengths", [])
        result.setdefault("improvements", [])
        result.setdefault("overall_comment", "")
        result.setdefault("model_excerpt", "")
        return result
    except Exception as e:
        logger.error(f"Oral feedback error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
