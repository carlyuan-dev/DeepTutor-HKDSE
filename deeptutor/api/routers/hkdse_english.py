"""HKDSE English Language — 英文科 API (Paper Generator + Essay Coach)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import random
import re
import statistics
import traceback
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deeptutor.services.path_service import get_path_service
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
_ORAL_TOPICS_RELATIVE_PATH = Path("hkdse") / "english" / "paper4" / "oral_topics.json"
_ORAL_TOPICS_BUILTIN_PATH = (
    Path(__file__).resolve().parents[2] / "data" / _ORAL_TOPICS_RELATIVE_PATH
)


def _oral_topic_candidate_paths() -> list[Path]:
    """Return user-imported topics first, then the packaged sample paper topics."""
    return [
        get_path_service().workspace_root / _ORAL_TOPICS_RELATIVE_PATH,
        _ORAL_TOPICS_BUILTIN_PATH,
    ]


def _load_oral_topics() -> list[dict[str, Any]]:
    """Load DSE Paper 4 topics from JSON. Caches after first load."""
    global _ORAL_TOPICS_CACHE
    if _ORAL_TOPICS_CACHE is not None:
        return _ORAL_TOPICS_CACHE

    for path in _oral_topic_candidate_paths():
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as e:
            logger.warning("Failed to decode oral topics from %s: %s", path, e)
            continue

        topics = data.get("topics", [])
        _ORAL_TOPICS_CACHE = topics if isinstance(topics, list) else []
        logger.info("Loaded %d oral topics from %s", len(_ORAL_TOPICS_CACHE), path)
        return _ORAL_TOPICS_CACHE

    logger.warning("No oral topic files found. Using fallback.")
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
    history: list[dict[str, Any]] = []
    phase: str = "discussion"  # discussion | individual_response
    mode: str = "text"  # text | voice
    speaker: str | None = None
    agenda_index: int | None = None
    agenda_item: str | None = None
    previous_agenda_item: str | None = None
    agenda_intent: str | None = None
    agenda_stance: str | None = None
    part_b_question: str | None = None


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


_CANDIDATE_PERSONAS = {
    "candidate_a": {
        "label": "Candidate A",
        "style": "confident and direct",
        "voice": "make clear claims, start or sharpen the discussion, but avoid sounding like an essay",
    },
    "candidate_b": {
        "label": "Candidate B",
        "style": "cautious and practical",
        "voice": "raise limits, costs, feasibility, or a polite counterpoint",
    },
    "candidate_c": {
        "label": "Candidate C",
        "style": "supportive and synthesizing",
        "voice": "connect other students' ideas, soften disagreement, and invite participation",
    },
}

_USER_TURN_THRESHOLD = 5
_ORAL_HIDDEN_TAGS = ("think", "thinking", "analysis", "reasoning")
_STREAM_TAG_TAIL = 24
_PREFIX_BUFFER_LIMIT = 64


@dataclass(frozen=True)
class OralTurnPlan:
    speaker: str
    intent: str
    target_speaker: str = "group"
    handoff_to_user: bool = True
    ask_candidate_d: bool = False
    max_words: int = 45


def _strip_oral_hidden_blocks(text: str) -> str:
    """Remove model reasoning blocks, including malformed trailing starts."""
    cleaned = text
    for tag in _ORAL_HIDDEN_TAGS:
        cleaned = re.sub(
            rf"<\s*{tag}\s*>.*?<\s*/\s*{tag}\s*>",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = re.sub(
            rf"<\s*{tag}\s*>.*$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return cleaned


def _strip_oral_prefix(text: str) -> str:
    """Remove common non-speech headers and preambles at the start."""
    cleaned = text.lstrip()
    cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    prefix_patterns = [
        r"^(?:#+\s*)?(?:Candidate\s+[ABC]|Candidate\s+[A-C]|Examiner|Assistant|AI)\s*[:：\-–—]\s*",
        r"^Here(?:'s| is)\s+(?:my|the)\s+(?:response|answer|speech)\s*[:：\-–—]\s*",
        r"^Sure[,.]?\s+here(?:'s| is)\s+(?:my|the)\s+(?:response|answer|speech)\s*[:：\-–—]\s*",
        r"^My\s+(?:response|answer|speech)\s+(?:would\s+be|is)\s*[:：\-–—]\s*",
        r"^As\s+(?:Candidate\s+[ABC]|the\s+examiner)\s*,?\s+",
        r"^I\s+would\s+(?:say|respond)\s*[:：,]?\s*",
    ]

    changed = True
    while changed:
        changed = False
        for pattern in prefix_patterns:
            new_cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
            if new_cleaned != cleaned:
                cleaned = new_cleaned.lstrip()
                changed = True

    return cleaned


def sanitize_oral_text(text: str) -> str:
    """Return the final display-safe oral utterance."""
    cleaned = _strip_oral_hidden_blocks(text)
    cleaned = _strip_oral_prefix(cleaned)
    cleaned = re.sub(r"<\s*/?\s*(?:think|thinking|analysis|reasoning)\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class OralStreamingSanitizer:
    """Stateful sanitizer for streamed oral-practice LLM output.

    It removes reasoning tags even when tag boundaries are split across chunks,
    then buffers the opening text briefly so role labels and assistant preambles
    do not leak before the stream looks like natural speech.
    """

    def __init__(self) -> None:
        self._tag_buffer = ""
        self._hidden_tag: str | None = None
        self._prefix_buffer = ""
        self._prefix_released = False

    def feed(self, chunk: str) -> str:
        visible = self._strip_hidden_stream(chunk, final=False)
        if not visible:
            return ""
        return self._release_prefix(visible, final=False)

    def flush(self) -> str:
        visible = self._strip_hidden_stream("", final=True)
        return self._release_prefix(visible, final=True)

    def _strip_hidden_stream(self, chunk: str, *, final: bool) -> str:
        self._tag_buffer += chunk
        output: list[str] = []

        while self._tag_buffer:
            if self._hidden_tag:
                close_re = re.compile(rf"<\s*/\s*{re.escape(self._hidden_tag)}\s*>", re.IGNORECASE)
                match = close_re.search(self._tag_buffer)
                if not match:
                    if final:
                        self._tag_buffer = ""
                    else:
                        self._tag_buffer = self._tag_buffer[-_STREAM_TAG_TAIL:]
                    break
                self._tag_buffer = self._tag_buffer[match.end():]
                self._hidden_tag = None
                continue

            open_match: re.Match[str] | None = None
            open_tag: str | None = None
            for tag in _ORAL_HIDDEN_TAGS:
                match = re.search(rf"<\s*{re.escape(tag)}\s*>", self._tag_buffer, re.IGNORECASE)
                if match and (open_match is None or match.start() < open_match.start()):
                    open_match = match
                    open_tag = tag

            if open_match and open_tag:
                output.append(self._tag_buffer[:open_match.start()])
                self._tag_buffer = self._tag_buffer[open_match.end():]
                self._hidden_tag = open_tag
                continue

            if final:
                output.append(self._tag_buffer)
                self._tag_buffer = ""
                break

            if "<" not in self._tag_buffer and len(self._tag_buffer) >= 12:
                output.append(self._tag_buffer)
                self._tag_buffer = ""
                break

            emit_len = max(0, len(self._tag_buffer) - _STREAM_TAG_TAIL)
            if emit_len == 0:
                break
            output.append(self._tag_buffer[:emit_len])
            self._tag_buffer = self._tag_buffer[emit_len:]

        return "".join(output)

    def _release_prefix(self, text: str, *, final: bool) -> str:
        if self._prefix_released:
            return text

        self._prefix_buffer += text
        cleaned = _strip_oral_prefix(self._prefix_buffer)
        should_release = final or len(self._prefix_buffer) >= _PREFIX_BUFFER_LIMIT or len(cleaned) >= 12
        if not should_release:
            return ""

        self._prefix_released = True
        self._prefix_buffer = ""
        return cleaned


def _build_oral_system_prompt() -> str:
    return (
        "You help simulate an HKDSE English Paper 4 group discussion (Speaking).\n\n"
        "IMPORTANT: You will be told which role to play in each turn. "
        "Your output must be ONLY that person's spoken words — "
        "no labels, no headers, no explanations, no formatting.\n\n"
        "RULES:\n"
        "- Speak naturally like a Hong Kong secondary school student in a group discussion.\n"
        "- Use 1-3 spoken sentences. Do not sound like an essay or formal report.\n"
        "- Do NOT output anything except the speech itself.\n"
        "- Start directly with the first spoken word.\n"
        "- Do NOT include role names, analysis, XML tags, markdown, or explanations."
    )


_INTENT_INSTRUCTIONS = {
    "open_discussion": (
        "Open the discussion with a clear first opinion and one simple reason. "
        "Speak to the whole group. Do not ask Candidate D directly."
    ),
    "agree_and_extend": (
        "Briefly agree with the target's point, then add one new supporting angle or example."
    ),
    "challenge_politely": (
        "Politely challenge or qualify the target's point. Keep it balanced, not aggressive."
    ),
    "ask_user": (
        "Respond briefly, then ask Candidate D one natural follow-up question."
    ),
    "bring_new_angle": (
        "Bring in one new angle that has not been discussed much yet."
    ),
    "soften_or_add_example": (
        "React to the previous AI speaker, soften or balance their point, and add a concrete example."
    ),
    "summarize_and_handoff": (
        "Briefly summarize the group's direction, then leave the floor open for the next speaker."
    ),
}


def _speaker_label(speaker: str) -> str:
    if speaker == "group":
        return "the group"
    if speaker == "candidate_d":
        return "Candidate D"
    if speaker == "examiner":
        return "Examiner"
    return _CANDIDATE_PERSONAS.get(speaker, {}).get("label", speaker.replace("_", " ").title())


def _build_part_a_prompt(plan: OralTurnPlan, req: OralTurnRequest) -> str:
    """Build prompt for a Part A group discussion turn from a backend turn plan."""
    topic_context = _format_topic_for_prompt(req.topic_id) if req.topic_id else ""
    persona = _CANDIDATE_PERSONAS.get(plan.speaker, {})
    speaker_label = _speaker_label(plan.speaker)
    target_label = _speaker_label(plan.target_speaker)
    intent_instruction = _INTENT_INSTRUCTIONS.get(plan.intent, "Continue the discussion naturally.")
    closing_instruction = (
        "End with one short, natural question to Candidate D."
        if plan.ask_candidate_d
        else (
            "Do not address Candidate D by name. If you want to invite responses, address the group generally."
            if plan.handoff_to_user
            else "Do not end with a question; leave room for another candidate to add something."
        )
    )

    parts = []
    if topic_context:
        parts.append(f"CONTEXT:\n{topic_context}")

    if req.history:
        parts.append("CONVERSATION SO FAR:")
        for msg in req.history:
            label = _speaker_label(msg["speaker"])
            parts.append(f"{label}: {msg['content']}")

    parts.append(
        f"\nYou are {speaker_label}, a {persona.get('style', 'natural')} student. "
        f"Your speaking tendency: {persona.get('voice', 'speak naturally')}.\n"
        f"Conversation intent: {plan.intent}. {intent_instruction}\n"
        f"Target to respond to: {target_label}.\n"
        f"Use about 20-{plan.max_words} words, 1-3 short spoken sentences. "
        "Sound like a real student, not a polished essay. "
        "Small spoken markers like 'Well,' or 'I guess' are okay if natural. "
        f"{closing_instruction}"
    )

    return "\n\n".join(parts)


_AGENDA_INTENT_INSTRUCTIONS = {
    "open_agenda_item": (
        "If a previous agenda item is provided, bridge from the previous agenda item "
        "in one natural phrase. Then explicitly name or paraphrase the current agenda question, "
        "briefly introduce what the group should discuss, then give your own view on the new agenda item."
    ),
    "respond_to_user_opened_agenda": (
        "The user has already opened or shifted to this agenda item. "
        "Respond directly to the user's point first, then add your own view on the same agenda item. "
        "Do not re-introduce the agenda as if nobody has mentioned it."
    ),
    "respond_and_add": (
        "Respond briefly to the recent discussion, then add one new point about "
        "the current agenda item."
    ),
    "close_agenda_item": (
        "Give your view and briefly close the current agenda item. "
        "Do not introduce a new agenda item, and do not say 'move on' or ask the group "
        "to discuss another point."
    ),
    "free_extension": (
        "Keep the discussion going with a relevant extra angle while staying close "
        "to the original task."
    ),
}

_AGENDA_STANCE_INSTRUCTIONS = {
    "support_extend": (
        "Briefly agree with one earlier point, then extend it with a concrete reason or example."
    ),
    "soft_challenge": (
        "Politely question or qualify one earlier point. Use a gentle phrase like "
        "\"I see your point, but...\" or \"That may be true, but...\". Do not sound aggressive."
    ),
    "balance_both_sides": (
        "Acknowledge one valid point, then explain a limitation or opposite consideration."
    ),
    "new_angle": (
        "Do not simply repeat or agree. Bring in a fresh angle that has not been discussed much."
    ),
    "summarize_transition": (
        "Briefly summarize the current discussion direction, then move naturally toward the agenda point."
    ),
}


def _build_agenda_part_a_prompt(req: OralTurnRequest) -> str:
    """Build a forced-speaker prompt for agenda-queue Part A turns."""
    speaker = req.speaker or "candidate_a"
    topic_context = _format_topic_for_prompt(req.topic_id) if req.topic_id else ""
    persona = _CANDIDATE_PERSONAS.get(speaker, {})
    speaker_label = _speaker_label(speaker)
    agenda_number = (req.agenda_index + 1) if req.agenda_index is not None else 1
    agenda_item = (req.agenda_item or "the current discussion point").strip()
    previous_agenda = (req.previous_agenda_item or "").strip()
    intent = req.agenda_intent or "respond_and_add"
    intent_instruction = _AGENDA_INTENT_INSTRUCTIONS.get(intent, _AGENDA_INTENT_INSTRUCTIONS["respond_and_add"])
    stance = req.agenda_stance or "new_angle"
    stance_instruction = _AGENDA_STANCE_INSTRUCTIONS.get(stance, _AGENDA_STANCE_INSTRUCTIONS["new_angle"])

    parts = []
    if topic_context:
        parts.append(f"CONTEXT:\n{topic_context}")

    parts.append("AGENDA STATE:")
    parts.append(f"- Current agenda item {agenda_number}: {agenda_item}")
    if previous_agenda:
        parts.append(f"- Previous agenda item: {previous_agenda}")
    parts.append(f"- Agenda intent: {intent}")
    parts.append(f"- Response stance: {stance}")

    if req.history:
        parts.append("CONVERSATION SO FAR:")
        for msg in req.history:
            label = _speaker_label(msg["speaker"])
            parts.append(f"{label}: {msg['content']}")

    parts.append(
        f"\nYou are {speaker_label}, a {persona.get('style', 'natural')} student. "
        f"Your speaking tendency: {persona.get('voice', 'speak naturally')}.\n"
        f"{intent_instruction}\n"
        f"{stance_instruction}\n"
        "Use about 60-75 words, with 3-5 natural spoken sentences. "
        "Sound like a real HKDSE group discussion participant. "
        "Output only the spoken words; do not include role labels, next-speaker tags, "
        "markdown, analysis, or control metadata."
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
        "first say exactly: \"That is the end of the group discussion. "
        "Now we will move on to the individual response section.\" "
        "Then ask the student ONE follow-up question about the topic. "
        "The question should invite the student to explain their personal views or experiences. "
        "Output ONLY the examiner's spoken words — no labels, no greetings, no commentary."
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


def _last_speaker(history: list[dict]) -> str | None:
    return history[-1].get("speaker") if history else None


def _plan_next_part_a_turn(history: list[dict]) -> OralTurnPlan:
    """Choose the next AI speaker and conversational intent with backend rules."""
    user_turns = _count_user_turns(history)
    consecutive_ai = _count_consecutive_ai(history)
    last_speaker = _last_speaker(history)

    if not history:
        return OralTurnPlan(
            speaker="candidate_a",
            intent="open_discussion",
            target_speaker="group",
            handoff_to_user=True,
            ask_candidate_d=False,
            max_words=42,
        )

    # Keep AI bursts short. If an AI has just spoken, allow only one more AI
    # to react, then hand the floor back to the student.
    if last_speaker in ("candidate_a", "candidate_b", "candidate_c"):
        if consecutive_ai >= 1:
            followup_speaker = {
                "candidate_a": "candidate_c",
                "candidate_b": "candidate_a",
                "candidate_c": "candidate_b",
            }.get(last_speaker, "candidate_a")
            return OralTurnPlan(
                speaker=followup_speaker,
                intent="soften_or_add_example",
                target_speaker=last_speaker,
                handoff_to_user=True,
                ask_candidate_d=False,
                max_words=38,
            )

    # After a user turn, vary the rhythm by discussion stage. Only one point in
    # the middle deliberately creates a two-AI exchange before returning to D.
    if user_turns <= 1:
        return OralTurnPlan(
            speaker="candidate_c",
            intent="agree_and_extend",
            target_speaker="candidate_d",
            handoff_to_user=True,
            ask_candidate_d=False,
            max_words=38,
        )
    if user_turns == 2:
        return OralTurnPlan(
            speaker="candidate_b",
            intent="challenge_politely",
            target_speaker="candidate_d",
            handoff_to_user=False,
            ask_candidate_d=False,
            max_words=38,
        )
    if user_turns == 3:
        return OralTurnPlan(
            speaker="candidate_c",
            intent="ask_user",
            target_speaker="candidate_d",
            handoff_to_user=True,
            ask_candidate_d=True,
            max_words=35,
        )
    if user_turns == 4:
        return OralTurnPlan(
            speaker="candidate_b",
            intent="summarize_and_handoff",
            target_speaker="group",
            handoff_to_user=True,
            ask_candidate_d=False,
            max_words=42,
        )

    return OralTurnPlan(
        speaker="candidate_a",
        intent="summarize_and_handoff",
        target_speaker="group",
        handoff_to_user=True,
        ask_candidate_d=False,
        max_words=42,
    )


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
    if req.speaker in _CANDIDATE_PERSONAS and req.agenda_item:
        speaker = req.speaker
        continues = False
        next_phase = "discussion"
        next_speaker = "candidate_d"
        prompt = _build_agenda_part_a_prompt(req)
        system_prompt = _build_oral_system_prompt()

    elif user_turns >= _USER_TURN_THRESHOLD and not _examiner_has_spoken(req.history):
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
        turn_plan = _plan_next_part_a_turn(req.history)
        speaker = turn_plan.speaker
        continues = not turn_plan.handoff_to_user
        next_phase = "discussion"
        next_speaker = "candidate_d" if turn_plan.handoff_to_user else "ai"

        prompt = _build_part_a_prompt(turn_plan, req)
        system_prompt = _build_oral_system_prompt()

    # ── Stream the LLM output (pure speech, no parsing needed) ──────
    async def _stream():
        try:
            yield json.dumps({"type": "turn_start"}) + "\n"

            raw_chunks: list[str] = []
            clean_chunks: list[str] = []
            sanitizer = OralStreamingSanitizer()
            async for chunk in llm_stream(prompt, system_prompt=system_prompt):
                raw_chunks.append(chunk)
                cleaned_chunk = sanitizer.feed(chunk)
                if cleaned_chunk:
                    clean_chunks.append(cleaned_chunk)
                    yield json.dumps({"type": "chunk", "content": cleaned_chunk}) + "\n"

            tail = sanitizer.flush()
            if tail:
                clean_chunks.append(tail)
                yield json.dumps({"type": "chunk", "content": tail}) + "\n"

            raw_content = "".join(raw_chunks)
            content = sanitize_oral_text(raw_content) or sanitize_oral_text("".join(clean_chunks))

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
    "pronunciation_delivery": {"score": 0, "max_score": 7, "locked": True, "comment": ""},
    "total_score": 12,
    "max_score": 28,
    "percentage": 42.9,
    "strengths": [],
    "improvements": [],
    "overall_comment": "",
    "model_excerpt": "",
}


def _count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text))


def _summarize_oral_voice_metadata(history: list[dict]) -> dict[str, Any]:
    """Aggregate browser-captured voice evidence for Candidate D turns."""
    user_voice_turns = 0
    total_duration_ms = 0
    total_words = 0
    interruptions = 0
    confidences: list[float] = []

    for msg in history:
        if msg.get("speaker") != "candidate_d":
            continue
        voice = msg.get("voice")
        if not isinstance(voice, dict):
            continue

        duration_ms = int(voice.get("duration_ms") or 0)
        if duration_ms <= 0:
            continue

        user_voice_turns += 1
        total_duration_ms += duration_ms
        total_words += int(voice.get("word_count") or _count_words(str(msg.get("content", ""))))
        if voice.get("interrupted_ai"):
            interruptions += 1
        confidence = voice.get("asr_confidence")
        if isinstance(confidence, int | float):
            confidences.append(float(confidence))

    words_per_minute = (
        round(total_words / (total_duration_ms / 60000))
        if total_duration_ms > 0 and total_words > 0
        else 0
    )
    average_asr_confidence = round(statistics.mean(confidences), 2) if confidences else None

    return {
        "has_voice_evidence": user_voice_turns > 0,
        "user_voice_turns": user_voice_turns,
        "total_duration_ms": total_duration_ms,
        "total_words": total_words,
        "words_per_minute": words_per_minute,
        "interruptions": interruptions,
        "average_asr_confidence": average_asr_confidence,
    }


def _build_pronunciation_delivery_score(summary: dict[str, Any]) -> dict[str, Any]:
    """Return unscored pronunciation metadata until audio-level analysis exists."""
    if not summary.get("has_voice_evidence"):
        return {
            "score": 0,
            "max_score": 7,
            "locked": True,
            "comment": "Pronunciation & Delivery is not scored yet because audio-level pronunciation analysis is not available.",
            "evidence": summary,
        }

    wpm = int(summary.get("words_per_minute") or 0)
    confidence = summary.get("average_asr_confidence")
    confidence_text = (
        f", ASR confidence {round(confidence * 100)}%"
        if isinstance(confidence, int | float)
        else ""
    )
    return {
        "score": 0,
        "max_score": 7,
        "locked": True,
        "comment": (
            f"Voice mode captured {summary.get('user_voice_turns', 0)} spoken turns "
            f"at about {wpm} wpm{confidence_text}. Pronunciation & Delivery is not scored yet; "
            "these are delivery signals only, not audio-level pronunciation analysis."
        ),
        "evidence": summary,
    }


def _build_oral_feedback_system_prompt() -> str:
    return (
        "You are an HKDSE English Language Paper 4 examiner. "
        "Evaluate the user's performance in a group discussion "
        "according to official HKDSE Speaking marking criteria. "
        "Provide specific references to what the user said. "
        "Output ONLY valid JSON — no markdown fences."
    )


def _build_oral_feedback_user_prompt(history: list[dict[str, Any]], topic_id: str) -> str:
    topic_context = _format_topic_for_prompt(topic_id) if topic_id else ""
    conversation = "\n".join(
        f"{m['speaker'].replace('_', ' ').title()}: {m['content']}"
        for m in history
    )
    candidate_d_turns = "\n".join(
        f"- {m.get('content', '')}"
        for m in history
        if m.get("speaker") == "candidate_d"
    ) or "- No Candidate D speech was captured."
    context_block = f"\nTopic:\n{topic_context}\n\n" if topic_context else "\n"
    return (
        f"Evaluate the user's performance in this HKDSE Paper 4 group discussion.{context_block}"
        f"Score Candidate D only. Candidate D is the user. "
        f"Do not credit Candidate D for ideas, vocabulary, transitions, or acknowledgements spoken by Candidate A, Candidate B, Candidate C, or the Examiner. "
        f"Every quoted example or evidence phrase in your feedback must appear in Candidate D turns only. "
        f"If a phrase appears only in the Full Conversation but not in Candidate D turns, do not use it as evidence for Candidate D. "
        f"If Candidate D only says testing phrases or gives little topic-relevant content, assign very low scores even if the AI candidates perform well.\n\n"
        f"Candidate D turns only:\n{candidate_d_turns}\n\n"
        f"Full Conversation:\n{conversation}\n\n"
        f"HKDSE Paper 4 Speaking Marking Criteria (max 28):\n\n"
        f"1. Communication Strategies (7 marks):\n"
        f"   - Initiating, maintaining, and closing discussions\n"
        f"   - Turn-taking, negotiating meaning, responding appropriately\n"
        f"   - Credit the user for useful agenda control, including opening a topic, "
        f"moving the group to the next guiding question, and keeping the discussion on task.\n"
        f"   - Do not penalise a reasonable topic transition merely because it does not explicitly echo every AI candidate first.\n\n"
        f"2. Language (7 marks):\n"
        f"   - Range and accuracy of vocabulary\n"
        f"   - Grammatical accuracy and sentence variety\n"
        f"   - IMPORTANT: voice turns are ASR transcript text, not a polished written script. "
        f"Do not treat obvious speech-recognition noise as grammatical errors. "
        f"Do not quote garbled ASR fragments as language evidence unless the user's intended meaning is genuinely unclear. "
        f"Assess whether the overall spoken meaning can be understood despite minor oral slips or ASR artifacts.\n\n"
        f"3. Ideas and Organisation (7 marks):\n"
        f"   - Relevance and depth of ideas\n"
        f"   - Logical organisation of arguments\n\n"
        f"4. Pronunciation and Delivery (7 marks) — not scored in this V1 voice mode because "
        f"audio-level pronunciation analysis is not available. The backend may attach delivery evidence only.\n\n"
        f"Return JSON matching this schema:\n"
        f"{json.dumps(_ORAL_FEEDBACK_SCHEMA, ensure_ascii=False, indent=2)}"
    )


def _candidate_d_relevant_word_count(history: list[dict[str, Any]]) -> int:
    testing_words = {"test", "testing", "software"}
    words: list[str] = []
    for msg in history:
        if msg.get("speaker") != "candidate_d":
            continue
        words.extend(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", str(msg.get("content", "")).lower()))
    return sum(1 for word in words if word not in testing_words)


def _apply_low_participation_feedback_cap(result: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    """Prevent AI-candidate content from inflating scores when Candidate D barely speaks."""
    relevant_words = _candidate_d_relevant_word_count(history)
    if relevant_words >= 20:
        return result

    comments = {
        "communication": "Too little relevant Candidate D speech was captured to show meaningful interaction or agenda control.",
        "language": "Too little relevant Candidate D speech was captured to assess language range or accuracy.",
        "ideas_organisation": "Too little relevant Candidate D speech was captured to assess topic development or organisation.",
    }
    for dim, comment in comments.items():
        current = result.get(dim)
        if not isinstance(current, dict):
            current = {"score": 0, "max_score": 7}
        current["score"] = min(int(current.get("score", 0) or 0), 1)
        current.setdefault("max_score", 7)
        current["comment"] = comment
        result[dim] = current

    result["strengths"] = []
    result["improvements"] = [
        "Give topic-relevant answers instead of testing phrases.",
        "Contribute enough spoken content for the system to assess your performance.",
    ]
    result["overall_comment"] = (
        "Too little relevant Candidate D speech was captured. The score is capped because "
        "the system must assess only the user's own spoken turns, not the AI candidates' responses."
    )
    result["model_excerpt"] = ""
    return result


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
        result = _apply_low_participation_feedback_cap(result, req.history)
        voice_summary = _summarize_oral_voice_metadata(req.history)
        result["pronunciation_delivery"] = _build_pronunciation_delivery_score(voice_summary)
        result["total_score"] = sum(result.get(d, {}).get("score", 0)
                                    for d in ("communication", "language", "ideas_organisation", "pronunciation_delivery"))
        result.setdefault("max_score", 28)
        if result.get("max_score", 0) > 0:
            result["percentage"] = round(result["total_score"] / result["max_score"] * 100, 1)
        result.setdefault("strengths", [])
        result.setdefault("improvements", [])
        result.setdefault("overall_comment", "")
        result.setdefault("model_excerpt", "")
        return result
    except Exception as e:
        logger.error(f"Oral feedback error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
