"""Shared business service for the agent-native mathematics learning chain.

The chat tools and the Market diagnostic REST endpoints both call this
service.  It owns input validation, the server-side answer key, deterministic
scoring, per-user persistence, state transitions, and submission idempotency.
LLM/RAG work happens behind injectable generation boundaries and is never
trusted to perform scoring or to choose an owner identity.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import hashlib
import logging
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
from uuid import uuid4

from .subjects import ALIASES, DEFAULT_TOPICS, normalise_subject
from .migrations import migrate_subjects

logger = logging.getLogger(__name__)

QuestionGenerator = Callable[..., Awaitable[dict[str, Any]]]
RecommendationGenerator = Callable[..., Awaitable[str]]
ConceptGenerator = Callable[..., Awaitable[dict[str, Any]]]


class LearningChainError(RuntimeError):
    """Base error for a learning-chain business operation."""


class LearningValidationError(LearningChainError):
    """The caller or generated payload violated the learning contract."""


class LearningAccessError(LearningChainError):
    """The active user does not own the requested learning record."""


class LearningGenerationError(LearningChainError):
    """Question or explanation generation failed before state was mutated."""


_DEFAULT = object()
_ACTIVITIES = {"diagnostic", "practice"}
_CHOICES = {"A", "B", "C", "D"}
_TOPIC_ALIASES: dict[str, tuple[str, str]] = {
    "algebra": ("algebra", "Algebra"),
    "代數": ("algebra", "代數"),
    "代数": ("algebra", "代数"),
    "geometry": ("geometry", "Geometry"),
    "幾何": ("geometry", "幾何"),
    "几何": ("geometry", "几何"),
    "trigonometry": ("trigonometry", "Trigonometry"),
    "三角學": ("trigonometry", "三角學"),
    "三角学": ("trigonometry", "三角学"),
    "probability": ("probability", "Probability"),
    "概率": ("probability", "概率"),
    "statistics": ("statistics", "Statistics"),
    "統計": ("statistics", "統計"),
    "统计": ("statistics", "统计"),
    "calculus": ("calculus", "Calculus"),
    "微積分": ("calculus", "微積分"),
    "微积分": ("calculus", "微积分"),
    "number": ("number", "Number"),
    "numbers": ("number", "Number"),
    "數與數系": ("number", "數與數系"),
}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _parse_json_object(raw: str) -> dict[str, Any]:
    cleaned = str(raw or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise LearningGenerationError("Model did not return a JSON object.") from None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LearningGenerationError("Model did not return valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise LearningGenerationError("Model response must be a JSON object.")
    return parsed


def _normalise_choice(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.match(r"^([A-D])(?:$|[\s.:)])", text)
    return match.group(1) if match else ""


def _normalise_topic(raw: Any, subject: str = "Mathematics") -> dict[str, Any]:
    display = re.sub(r"\s+", " ", str(raw or "").strip())
    if not display:
        display = DEFAULT_TOPICS[subject]
    known = (_TOPIC_ALIASES if subject == "Mathematics" else ALIASES[subject]).get(
        display.casefold()
    )
    if known:
        topic_id, canonical_display = known
        return {"topic_id": topic_id, "topic_name": canonical_display, "mapped": True}
    slug = hashlib.sha256(display.casefold().encode("utf-8")).hexdigest()[:20]
    if subject == "Mathematics":
        # Keep IDs already stored by the original mathematics workflow.
        slug = re.sub(r"[^a-z0-9]+", "-", display.casefold()).strip("-") or "unknown"
    return {
        "topic_id": f"unmapped:{slug}",
        "topic_name": display,
        "mapped": False,
    }


class LearningChainService:
    """SQLite-backed learning workflow for one server-resolved user."""

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        user_id: str | None = None,
        question_generator: QuestionGenerator | None = None,
        recommendation_generator: RecommendationGenerator | None | object = _DEFAULT,
        concept_generator: ConceptGenerator | None = None,
    ) -> None:
        if user_id is None:
            from deeptutor.multi_user.context import get_current_user

            user_id = get_current_user().id
        self.user_id = str(user_id or "").strip()
        if not self.user_id:
            raise LearningValidationError("A server-resolved user identity is required.")

        if db_path is None:
            from deeptutor.services.path_service import get_path_service

            db_path = get_path_service().get_user_root() / "learning_chain.db"
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.question_generator = question_generator or _default_question_generator
        self.recommendation_generator = (
            _default_recommendation_generator
            if recommendation_generator is _DEFAULT
            else recommendation_generator
        )
        self.concept_generator = concept_generator or _default_concept_generator
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS learning_sessions (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    chat_session_id TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT 'Mathematics',
                    stage TEXT NOT NULL DEFAULT 'needs_diagnostic',
                    budget_minutes INTEGER NOT NULL DEFAULT 15,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(owner_user_id, chat_session_id)
                );

                CREATE TABLE IF NOT EXISTS learning_attempts (
                    id TEXT PRIMARY KEY,
                    learning_session_id TEXT NOT NULL
                        REFERENCES learning_sessions(id) ON DELETE CASCADE,
                    owner_user_id TEXT NOT NULL,
                    activity TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    status TEXT NOT NULL,
                    questions_json TEXT NOT NULL,
                    answer_key_json TEXT NOT NULL,
                    answers_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    knowledge_references_json TEXT NOT NULL DEFAULT '[]',
                    grounded INTEGER NOT NULL DEFAULT 0,
                    retrieval_status TEXT NOT NULL DEFAULT 'not_requested',
                    created_at REAL NOT NULL,
                    submitted_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_learning_attempt_owner_status
                    ON learning_attempts(owner_user_id, status, created_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_pending_learning_attempt
                    ON learning_attempts(owner_user_id, learning_session_id)
                    WHERE status = 'awaiting_answer';

                CREATE TABLE IF NOT EXISTS learning_topic_scores (
                    owner_user_id TEXT NOT NULL,
                    topic_id TEXT NOT NULL,
                    topic_name TEXT NOT NULL,
                    correct INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    last_percentage REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(owner_user_id, topic_id)
                );

                CREATE TABLE IF NOT EXISTS learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_user_id TEXT NOT NULL,
                    learning_session_id TEXT NOT NULL,
                    attempt_id TEXT,
                    action TEXT NOT NULL,
                    from_stage TEXT NOT NULL,
                    to_stage TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_learning_events_session
                    ON learning_events(owner_user_id, learning_session_id, id DESC);
                """
            )

        migrate_subjects(self.db_path)

    def get_pending_attempt_for_chat(self, attempt_id: str, chat_session_id: str) -> dict[str, Any]:
        """Return only public questions owned by this user and current chat."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT a.* FROM learning_attempts a
                   JOIN learning_sessions s ON s.id = a.learning_session_id
                   WHERE a.id = ? AND a.owner_user_id = ?
                     AND s.chat_session_id = ? AND a.status = 'awaiting_answer'""",
                (attempt_id, self.user_id, chat_session_id),
            ).fetchone()
        if row is None:
            raise LearningValidationError("No pending attempt in the current chat.")
        return self._public_attempt(row, resumed=True)

    async def get_state(
        self, *, chat_session_id: str = "", subject: str = "Mathematics"
    ) -> dict[str, Any]:
        subject = normalise_subject(subject)
        session_key = str(chat_session_id or "").strip()
        with self._connect() as conn:
            session = None
            if session_key:
                session = conn.execute(
                    """
                    SELECT * FROM learning_sessions
                    WHERE owner_user_id = ? AND chat_session_id = ? AND subject = ?
                    """,
                    (self.user_id, session_key, subject),
                ).fetchone()
            else:
                session = conn.execute(
                    """
                    SELECT * FROM learning_sessions
                    WHERE owner_user_id = ? AND subject = ? ORDER BY updated_at DESC LIMIT 1
                    """,
                    (self.user_id, subject),
                ).fetchone()

            pending = None
            last_result = None
            events: list[dict[str, Any]] = []
            if session is not None:
                pending_row = conn.execute(
                    """
                    SELECT * FROM learning_attempts
                    WHERE owner_user_id = ? AND learning_session_id = ?
                      AND status = 'awaiting_answer'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (self.user_id, session["id"]),
                ).fetchone()
                if pending_row is not None:
                    pending = self._public_attempt(pending_row, resumed=True)
                last_row = conn.execute(
                    """
                    SELECT result_json FROM learning_attempts
                    WHERE owner_user_id = ? AND learning_session_id = ?
                      AND status = 'completed'
                    ORDER BY submitted_at DESC LIMIT 1
                    """,
                    (self.user_id, session["id"]),
                ).fetchone()
                if last_row is not None:
                    last_result = _json_loads(last_row["result_json"], {})
                event_rows = conn.execute(
                    """
                    SELECT action, from_stage, to_stage, summary_json, created_at
                    FROM learning_events
                    WHERE owner_user_id = ? AND learning_session_id = ?
                    ORDER BY id DESC LIMIT 12
                    """,
                    (self.user_id, session["id"]),
                ).fetchall()
                events = [
                    {
                        "action": row["action"],
                        "from_stage": row["from_stage"],
                        "to_stage": row["to_stage"],
                        "summary": _json_loads(row["summary_json"], {}),
                        "created_at": row["created_at"],
                    }
                    for row in reversed(event_rows)
                ]

            score_rows = conn.execute(
                """
                SELECT topic_id, topic_name, correct, total, last_percentage, updated_at
                FROM learning_topic_scores
                WHERE owner_user_id = ? AND subject = ?
                ORDER BY last_percentage ASC, updated_at DESC
                """,
                (self.user_id, subject),
            ).fetchall()
            topic_scores = [dict(row) for row in score_rows]
            weak_topics = [
                {
                    "topic_id": row["topic_id"],
                    "topic_name": row["topic_name"],
                    "performance_estimate": row["last_percentage"],
                }
                for row in topic_scores
                if row["last_percentage"] < 60
            ]
            has_history = bool(topic_scores or last_result or pending)
            stage = (
                str(session["stage"])
                if session is not None
                else ("ready" if has_history else "needs_diagnostic")
            )
            return {
                "learning_session_id": None if session is None else session["id"],
                "chat_session_id": session_key
                or ("" if session is None else session["chat_session_id"]),
                "subject": subject,
                "stage": stage,
                "budget_minutes": 15 if session is None else session["budget_minutes"],
                "has_history": has_history,
                "history_status": "available" if has_history else "missing_server_record",
                "weak_topics": weak_topics,
                "topic_scores": topic_scores,
                "pending_attempt": pending,
                "last_result": last_result,
                "events": events,
            }

    async def create_attempt(
        self,
        *,
        chat_session_id: str,
        activity: str = "practice",
        topics: list[str] | None = None,
        num_questions: int = 3,
        kb_name: str | None = None,
        language: str = "en",
        budget_minutes: int = 15,
        subject: str = "Mathematics",
        practice_type: str = "objective",
    ) -> dict[str, Any]:
        subject = normalise_subject(subject)
        if practice_type not in {"objective", "reading"}:
            raise LearningValidationError("practice_type must be objective or reading.")
        if practice_type == "reading" and subject == "Mathematics":
            raise LearningValidationError("Reading practice is for Chinese or English.")
        session_key = str(chat_session_id or "").strip()
        if not session_key:
            raise LearningValidationError("chat_session_id is required.")
        activity_name = str(activity or "").strip().lower()
        if activity_name not in _ACTIVITIES:
            raise LearningValidationError("activity must be diagnostic or practice.")
        try:
            question_count = int(num_questions)
        except (TypeError, ValueError):
            raise LearningValidationError("num_questions must be an integer.") from None
        if question_count < 1 or question_count > 10:
            raise LearningValidationError("num_questions must be between 1 and 10.")
        try:
            budget = int(budget_minutes)
        except (TypeError, ValueError):
            raise LearningValidationError("budget_minutes must be an integer.") from None
        if budget < 1 or budget > 120:
            raise LearningValidationError("budget_minutes must be between 1 and 120.")

        pending = self._find_pending(chat_session_id=session_key, subject=subject)
        if pending is not None:
            return self._public_attempt(pending, resumed=True)

        if not topics and practice_type == "reading":
            topics = ["閱讀理解" if subject == "Chinese" else "Reading comprehension"]
        topic_rows = self._select_topics(topics or [], subject=subject)
        try:
            generated = await self.question_generator(
                activity=activity_name,
                topics=topic_rows,
                num_questions=question_count,
                kb_name=str(kb_name or "").strip() or None,
                language="zh" if str(language).lower().startswith("zh") else "en",
                subject=subject,
                practice_type=practice_type,
            )
        except LearningChainError:
            raise
        except Exception as exc:
            raise LearningGenerationError(f"Question generation failed: {exc}") from exc

        public_questions, answer_key = self._validate_generated_questions(
            generated,
            expected_count=question_count,
            subject=subject,
            require_passage=practice_type == "reading",
        )
        now = time.time()
        learning_session_id = f"learn_{uuid4().hex}"
        attempt_id = f"attempt_{uuid4().hex}"
        grounded = bool(generated.get("grounded", False))
        retrieval_status = str(generated.get("retrieval_status") or "not_requested")
        references = generated.get("knowledge_references") or []
        if not isinstance(references, list):
            references = []

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing_session = conn.execute(
                """
                SELECT * FROM learning_sessions
                WHERE owner_user_id = ? AND chat_session_id = ? AND subject = ?
                """,
                (self.user_id, session_key, subject),
            ).fetchone()
            if existing_session is None:
                conn.execute(
                    """
                    INSERT INTO learning_sessions (
                        id, owner_user_id, chat_session_id, subject, stage,
                        budget_minutes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'needs_diagnostic', ?, ?, ?)
                    """,
                    (learning_session_id, self.user_id, session_key, subject, budget, now, now),
                )
                from_stage = "needs_diagnostic"
            else:
                learning_session_id = str(existing_session["id"])
                from_stage = str(existing_session["stage"])
                raced_pending = conn.execute(
                    """
                    SELECT * FROM learning_attempts
                    WHERE owner_user_id = ? AND learning_session_id = ?
                      AND status = 'awaiting_answer'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (self.user_id, learning_session_id),
                ).fetchone()
                if raced_pending is not None:
                    conn.rollback()
                    return self._public_attempt(raced_pending, resumed=True)

            conn.execute(
                """
                INSERT INTO learning_attempts (
                    id, learning_session_id, owner_user_id, activity, subject,
                    status, questions_json, answer_key_json,
                    knowledge_references_json, grounded, retrieval_status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'awaiting_answer', ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    learning_session_id,
                    self.user_id,
                    activity_name,
                    subject,
                    _json_dumps(public_questions),
                    _json_dumps(answer_key),
                    _json_dumps(references),
                    1 if grounded else 0,
                    retrieval_status,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE learning_sessions
                SET stage = 'awaiting_answer', budget_minutes = ?, updated_at = ?
                WHERE id = ? AND owner_user_id = ?
                """,
                (budget, now, learning_session_id, self.user_id),
            )
            self._record_event(
                conn,
                learning_session_id=learning_session_id,
                attempt_id=attempt_id,
                action=f"create_{activity_name}",
                from_stage=from_stage,
                to_stage="awaiting_answer",
                summary={
                    "question_count": len(public_questions),
                    "topic_ids": [q["topic_id"] for q in public_questions],
                    "grounded": grounded,
                    "retrieval_status": retrieval_status,
                },
                created_at=now,
            )
            row = conn.execute(
                "SELECT * FROM learning_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            conn.commit()
        return self._public_attempt(row, resumed=False)

    async def submit_attempt(
        self,
        *,
        attempt_id: str,
        answers: dict[str, str],
        language: str = "en",
    ) -> dict[str, Any]:
        attempt_key = str(attempt_id or "").strip()
        if not attempt_key:
            raise LearningValidationError("attempt_id is required.")
        if not isinstance(answers, dict):
            raise LearningValidationError("answers must be a question-id mapping.")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM learning_attempts WHERE id = ? AND owner_user_id = ?",
                (attempt_key, self.user_id),
            ).fetchone()
            if row is None:
                exists = conn.execute(
                    "SELECT 1 FROM learning_attempts WHERE id = ?", (attempt_key,)
                ).fetchone()
                conn.rollback()
                if exists is not None:
                    raise LearningAccessError("The attempt belongs to another user.")
                raise LearningValidationError("Learning attempt was not found.")

            if row["status"] == "completed":
                previous = _json_loads(row["answers_json"], {})
                if {key: _normalise_choice(value) for key, value in answers.items()} != previous:
                    raise LearningValidationError(
                        "Completed attempt received different answers (conflict)."
                    )
                existing_result = _json_loads(row["result_json"], {})
                existing_result["duplicate_submission"] = True
                conn.rollback()
                return existing_result

            questions = _json_loads(row["questions_json"], [])
            answer_key = _json_loads(row["answer_key_json"], {})
            question_ids = [str(q.get("id") or "") for q in questions if isinstance(q, dict)]
            if set(answers) != set(question_ids):
                conn.rollback()
                raise LearningValidationError(
                    "answers must contain exactly all questions in this attempt."
                )
            normalised_answers: dict[str, str] = {}
            for question_id in question_ids:
                choice = _normalise_choice(answers.get(question_id))
                if not choice:
                    conn.rollback()
                    raise LearningValidationError(
                        f"Answer for {question_id} must be one of A, B, C, or D."
                    )
                normalised_answers[question_id] = choice

            correct_count = 0
            details: list[dict[str, Any]] = []
            by_topic: dict[str, dict[str, Any]] = {}
            for question in questions:
                question_id = str(question["id"])
                key = answer_key.get(question_id) or {}
                correct_answer = _normalise_choice(key.get("answer"))
                student_answer = normalised_answers[question_id]
                is_correct = student_answer == correct_answer
                correct_count += 1 if is_correct else 0
                topic_id = str(question.get("topic_id") or "unmapped:unknown")
                topic_name = str(question.get("topic_name") or question.get("topic") or "Unknown")
                aggregate = by_topic.setdefault(
                    topic_id,
                    {"topic_id": topic_id, "topic_name": topic_name, "correct": 0, "total": 0},
                )
                aggregate["correct"] += 1 if is_correct else 0
                aggregate["total"] += 1
                details.append(
                    {
                        "question_id": question_id,
                        "topic_id": topic_id,
                        "topic_name": topic_name,
                        "student_answer": student_answer,
                        "correct_answer": correct_answer,
                        "is_correct": is_correct,
                        "explanation": str(key.get("explanation") or ""),
                    }
                )

            profile = []
            now = time.time()
            for aggregate in by_topic.values():
                percentage = round(aggregate["correct"] / aggregate["total"] * 100, 1)
                profile.append({**aggregate, "performance_estimate": percentage})
                conn.execute(
                    """
                    INSERT INTO learning_topic_scores (
                        owner_user_id, subject, topic_id, topic_name, correct, total,
                        last_percentage, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(owner_user_id, subject, topic_id) DO UPDATE SET
                        topic_name = excluded.topic_name,
                        correct = learning_topic_scores.correct + excluded.correct,
                        total = learning_topic_scores.total + excluded.total,
                        last_percentage = excluded.last_percentage,
                        updated_at = excluded.updated_at
                    """,
                    (
                        self.user_id,
                        row["subject"],
                        aggregate["topic_id"],
                        aggregate["topic_name"],
                        aggregate["correct"],
                        aggregate["total"],
                        percentage,
                        now,
                    ),
                )

            total = len(question_ids)
            result = {
                "attempt_id": attempt_key,
                "learning_session_id": row["learning_session_id"],
                "activity": row["activity"],
                "subject": row["subject"],
                "stage": "completed",
                "score": correct_count,
                "total": total,
                "percentage": round(correct_count / total * 100, 1),
                "profile": sorted(profile, key=lambda item: item["performance_estimate"]),
                "weak_topics": [
                    item["topic_name"] for item in profile if item["performance_estimate"] < 60
                ],
                "details": details,
                "recommendation": "",
                "recommendation_status": (
                    "pending" if self.recommendation_generator is not None else "not_requested"
                ),
                "duplicate_submission": False,
            }
            conn.execute(
                """
                UPDATE learning_attempts
                SET status = 'completed', answers_json = ?, result_json = ?, submitted_at = ?
                WHERE id = ? AND owner_user_id = ? AND status = 'awaiting_answer'
                """,
                (
                    _json_dumps(normalised_answers),
                    _json_dumps(result),
                    now,
                    attempt_key,
                    self.user_id,
                ),
            )
            conn.execute(
                """
                UPDATE learning_sessions SET stage = 'completed', updated_at = ?
                WHERE id = ? AND owner_user_id = ?
                """,
                (now, row["learning_session_id"], self.user_id),
            )
            self._record_event(
                conn,
                learning_session_id=str(row["learning_session_id"]),
                attempt_id=attempt_key,
                action="submit_answers",
                from_stage="awaiting_answer",
                to_stage="completed",
                summary={"score": correct_count, "total": total},
                created_at=now,
            )
            conn.commit()

        # Advice is deliberately outside the scoring transaction. A provider
        # failure can remove advice, but can never roll back the authoritative
        # answers, score, topic aggregates, or completed state.
        if self.recommendation_generator is not None:
            try:
                recommendation = await self.recommendation_generator(
                    profile=result["profile"],
                    weak_topics=result["weak_topics"],
                    subject=result["subject"],
                    language="zh" if str(language).lower().startswith("zh") else "en",
                )
                result["recommendation"] = str(recommendation or "").strip()
                result["recommendation_status"] = (
                    "completed" if result["recommendation"] else "empty"
                )
            except Exception as exc:  # noqa: BLE001 - advice is a failure-isolated add-on
                logger.warning("Learning recommendation failed after score commit: %s", exc)
                result["recommendation_status"] = "failed"
            self._update_result(attempt_key, result)
        return result

    async def explain_concept(
        self,
        *,
        chat_session_id: str,
        concept: str,
        kb_name: str | None = None,
        language: str = "en",
        subject: str = "Mathematics",
    ) -> dict[str, Any]:
        subject = normalise_subject(subject)
        session_key = str(chat_session_id or "").strip()
        concept_name = str(concept or "").strip()
        if not session_key:
            raise LearningValidationError("chat_session_id is required.")
        if not concept_name or len(concept_name) > 160:
            raise LearningValidationError("concept must contain 1 to 160 characters.")
        try:
            result = await self.concept_generator(
                concept=concept_name,
                subject=subject,
                kb_name=str(kb_name or "").strip() or None,
                language="zh" if str(language).lower().startswith("zh") else "en",
            )
        except LearningChainError:
            raise
        except Exception as exc:
            raise LearningGenerationError(f"Concept explanation failed: {exc}") from exc
        if not isinstance(result, dict) or not str(result.get("summary") or "").strip():
            raise LearningGenerationError("Concept generator returned an invalid explanation.")

        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = self._ensure_session(
                conn,
                chat_session_id=session_key,
                budget_minutes=15,
                now=now,
                subject=subject,
            )
            from_stage = str(session["stage"])
            conn.execute(
                """
                UPDATE learning_sessions SET stage = 'explaining', updated_at = ?
                WHERE id = ? AND owner_user_id = ?
                """,
                (now, session["id"], self.user_id),
            )
            self._record_event(
                conn,
                learning_session_id=str(session["id"]),
                attempt_id=None,
                action="explain_concept",
                from_stage=from_stage,
                to_stage="explaining",
                summary={
                    "concept": concept_name,
                    "grounded": bool(result.get("grounded", False)),
                    "retrieval_status": result.get("retrieval_status", "not_requested"),
                },
                created_at=now,
            )
            conn.commit()
        return {
            **result,
            "learning_session_id": session["id"],
            "subject": subject,
            "stage": "explaining",
        }

    def _find_pending(
        self, *, chat_session_id: str, subject: str = "Mathematics"
    ) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT a.* FROM learning_attempts a
                JOIN learning_sessions s ON s.id = a.learning_session_id
                WHERE a.owner_user_id = ? AND s.owner_user_id = ?
                  AND s.chat_session_id = ? AND s.subject = ? AND a.status = 'awaiting_answer'
                ORDER BY a.created_at DESC LIMIT 1
                """,
                (self.user_id, self.user_id, chat_session_id, subject),
            ).fetchone()

    def _select_topics(
        self, requested: list[str], *, subject: str = "Mathematics"
    ) -> list[dict[str, Any]]:
        normalised = [
            _normalise_topic(item, subject) for item in requested if str(item or "").strip()
        ]
        if normalised:
            unique: dict[str, dict[str, Any]] = {}
            for row in normalised[:8]:
                unique.setdefault(row["topic_id"], row)
            return list(unique.values())
        with self._connect() as conn:
            weak = conn.execute(
                """
                SELECT topic_id, topic_name FROM learning_topic_scores
                WHERE owner_user_id = ? AND subject = ? AND last_percentage < 60
                ORDER BY last_percentage ASC, updated_at DESC LIMIT 3
                """,
                (self.user_id, subject),
            ).fetchall()
        if weak:
            return [
                {"topic_id": row["topic_id"], "topic_name": row["topic_name"], "mapped": True}
                for row in weak
            ]
        return [_normalise_topic(DEFAULT_TOPICS[subject], subject)]

    @staticmethod
    def _validate_generated_questions(
        generated: dict[str, Any],
        *,
        expected_count: int,
        subject: str = "Mathematics",
        require_passage: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
        if not isinstance(generated, dict):
            raise LearningGenerationError("Question generator must return an object.")
        raw_questions = generated.get("questions")
        if not isinstance(raw_questions, list) or len(raw_questions) < expected_count:
            raise LearningGenerationError(
                f"Question generator returned fewer than {expected_count} valid questions."
            )
        public_questions: list[dict[str, Any]] = []
        answer_key: dict[str, dict[str, str]] = {}
        seen_ids: set[str] = set()
        for index, raw in enumerate(raw_questions[:expected_count], start=1):
            if not isinstance(raw, dict):
                raise LearningGenerationError("Each generated question must be an object.")
            question_id = str(raw.get("id") or f"q{index}").strip()
            if not question_id or question_id in seen_ids:
                raise LearningGenerationError("Generated question ids must be unique.")
            seen_ids.add(question_id)
            question_text = str(raw.get("question") or "").strip()
            options = raw.get("options")
            answer = _normalise_choice(raw.get("answer"))
            if (
                not question_text
                or not isinstance(options, list)
                or len(options) != 4
                or not answer
            ):
                raise LearningGenerationError(
                    f"Question {question_id} must have text, four options, and answer A-D."
                )
            option_texts = [str(option or "").strip() for option in options]
            if any(not option for option in option_texts):
                raise LearningGenerationError(f"Question {question_id} contains an empty option.")
            topic = _normalise_topic(raw.get("topic"), subject)
            passage = raw.get("passage", "")
            if not isinstance(passage, str) or len(passage) > 12000:
                raise LearningGenerationError("passage must be text of at most 12000 characters.")
            if require_passage and not passage.strip():
                raise LearningGenerationError("Reading question requires its source passage.")
            public_questions.append(
                {
                    "id": question_id,
                    "topic": topic["topic_name"],
                    **topic,
                    "difficulty": str(raw.get("difficulty") or "medium").strip().lower(),
                    "question": question_text,
                    "passage": passage.strip(),
                    "options": option_texts,
                }
            )
            answer_key[question_id] = {
                "answer": answer,
                "explanation": str(raw.get("explanation") or "").strip(),
            }
        return public_questions, answer_key

    @staticmethod
    def _public_attempt(row: sqlite3.Row, *, resumed: bool) -> dict[str, Any]:
        return {
            "attempt_id": row["id"],
            "learning_session_id": row["learning_session_id"],
            "activity": row["activity"],
            "subject": row["subject"],
            "status": row["status"],
            "stage": row["status"],
            "questions": _json_loads(row["questions_json"], []),
            "grounded": bool(row["grounded"]),
            "retrieval_status": row["retrieval_status"],
            "knowledge_references": _json_loads(row["knowledge_references_json"], []),
            "resumed": resumed,
            "created_at": row["created_at"],
        }

    def _ensure_session(
        self,
        conn: sqlite3.Connection,
        *,
        chat_session_id: str,
        budget_minutes: int,
        now: float,
        subject: str = "Mathematics",
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT * FROM learning_sessions
            WHERE owner_user_id = ? AND chat_session_id = ? AND subject = ?
            """,
            (self.user_id, chat_session_id, subject),
        ).fetchone()
        if row is not None:
            return row
        session_id = f"learn_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_sessions (
                id, owner_user_id, chat_session_id, subject, stage,
                budget_minutes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'needs_diagnostic', ?, ?, ?)
            """,
            (session_id, self.user_id, chat_session_id, subject, budget_minutes, now, now),
        )
        return conn.execute(
            "SELECT * FROM learning_sessions WHERE id = ?", (session_id,)
        ).fetchone()

    def _record_event(
        self,
        conn: sqlite3.Connection,
        *,
        learning_session_id: str,
        attempt_id: str | None,
        action: str,
        from_stage: str,
        to_stage: str,
        summary: dict[str, Any],
        created_at: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO learning_events (
                owner_user_id, learning_session_id, attempt_id, action,
                from_stage, to_stage, summary_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.user_id,
                learning_session_id,
                attempt_id,
                action,
                from_stage,
                to_stage,
                _json_dumps(summary),
                created_at,
            ),
        )

    def _update_result(self, attempt_id: str, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE learning_attempts SET result_json = ?
                WHERE id = ? AND owner_user_id = ? AND status = 'completed'
                """,
                (_json_dumps(result), attempt_id, self.user_id),
            )


async def _retrieve_context(
    kb_name: str | None, query: str
) -> tuple[str, str, list[dict[str, str]]]:
    if not kb_name:
        return "", "not_requested", []
    try:
        from deeptutor.services.rag.service import RAGService

        result = await RAGService().search(query=query, kb_name=kb_name)
        content = str(result.get("content") or result.get("answer") or "")
        if not content:
            return "", "empty", []
        return content, "completed", [{"type": "knowledge_base", "kb_name": kb_name}]
    except Exception as exc:  # noqa: BLE001 - deliberate LLM-only degradation
        logger.warning("Learning-chain RAG failed; continuing without grounding: %s", exc)
        return "", "failed", []


async def _default_question_generator(
    *,
    activity: str,
    topics: list[dict[str, Any]],
    num_questions: int,
    kb_name: str | None,
    language: str,
    subject: str = "Mathematics",
    practice_type: str = "objective",
) -> dict[str, Any]:
    from deeptutor.services.llm import complete as llm_complete

    topic_names = [str(item["topic_name"]) for item in topics]
    context, retrieval_status, references = await _retrieve_context(
        kb_name, subject + " " + " ".join(topic_names)
    )
    lang_line = "Respond in 繁體中文." if language == "zh" else "Respond in English."
    schema = {
        "questions": [
            {
                "id": "q1",
                "topic": topic_names[0] if topic_names else DEFAULT_TOPICS[subject],
                "difficulty": "easy|medium|hard",
                "question": "question text",
                "passage": "complete short reading passage" if practice_type == "reading" else "",
                "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
                "answer": "A",
                "explanation": "brief worked explanation",
            }
        ]
    }
    prompt = (
        f"{lang_line}\nCreate exactly {num_questions} objective multiple-choice "
        f"{subject} questions for a {activity}.\n"
        + (
            "Write passages, questions and choices in Traditional Chinese.\n"
            if subject == "Chinese"
            else (
                "Write passages, questions and choices in English.\n"
                if subject == "English"
                else ""
            )
        )
        + (
            "This is reading practice. Every question MUST include its complete short passage in the passage field, with enough evidence for its answer.\n"
            if practice_type == "reading"
            else "For any question that refers to a text, include that complete text in passage.\n"
        )
        + f"Topics: {', '.join(topic_names)}.\n"
        "Every question must have exactly four choices and one unambiguous answer A-D. "
        "Use stable ids q1, q2, ... and include a brief correctness explanation.\n"
        + (
            f"Ground questions in this material when relevant:\n{context[:5000]}\n"
            if context
            else ""
        )
        + f"Output only JSON matching: {_json_dumps(schema)}"
    )
    try:
        raw = await llm_complete(
            prompt,
            system_prompt=(
                f"You are a careful HKDSE {subject} objective assessment designer. "
                "Return valid JSON only. Check the answer key before responding."
            ),
        )
        parsed = _parse_json_object(raw)
    except LearningChainError:
        raise
    except Exception as exc:
        raise LearningGenerationError(str(exc)) from exc
    return {
        **parsed,
        "grounded": bool(context),
        "retrieval_status": retrieval_status,
        "knowledge_references": references,
    }


async def _default_recommendation_generator(
    *,
    profile: list[dict[str, Any]],
    weak_topics: list[str],
    language: str,
    subject: str = "Mathematics",
) -> str:
    from deeptutor.services.llm import complete as llm_complete

    lang_line = "Respond in 繁體中文." if language == "zh" else "Respond in English."
    raw = await llm_complete(
        (
            f"{lang_line}\nA learner completed an objective {subject} attempt. "
            f"Performance estimates: {_json_dumps(profile)}. Weak topics: {weak_topics}. "
            "Give two short, concrete next-step sentences. Do not claim this is a "
            "validated mastery measurement."
        ),
        system_prompt="You are a concise learning coach.",
    )
    return str(raw or "").strip()


async def _default_concept_generator(
    *, concept: str, kb_name: str | None, language: str, subject: str = "Mathematics"
) -> dict[str, Any]:
    from deeptutor.services.llm import complete as llm_complete

    context, retrieval_status, references = await _retrieve_context(
        kb_name, subject + " " + concept
    )
    lang_line = "Respond in 繁體中文." if language == "zh" else "Respond in English."
    schema = {
        "concept": concept,
        "summary": "plain-language explanation",
        "analogy": "intuitive analogy",
        "key_points": ["point"],
        "worked_example": "worked subject example",
        "common_mistakes": ["mistake"],
        "check_question": "quick self-check",
    }
    raw = await llm_complete(
        (
            f"{lang_line}\nExplain the {subject} concept {concept!r} for a secondary-school "
            "learner. Include one worked example and a self-check."
            + (f"\nUse this source material:\n{context[:5000]}" if context else "")
            + f"\nOutput only JSON matching: {_json_dumps(schema)}"
        ),
        system_prompt=f"You are a patient {subject} tutor. Return valid JSON only.",
    )
    parsed = _parse_json_object(raw)
    return {
        **parsed,
        "grounded": bool(context),
        "retrieval_status": retrieval_status,
        "knowledge_references": references,
    }


def get_learning_service() -> LearningChainService:
    """Resolve a fresh service for the request-local authenticated user."""

    return LearningChainService()
