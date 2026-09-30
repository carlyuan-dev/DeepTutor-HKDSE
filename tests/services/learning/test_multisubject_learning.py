import asyncio
import sqlite3
import json

import pytest

from deeptutor.services.learning import (
    LearningChainService,
    LearningValidationError,
    LearningGenerationError,
)


async def generate(**kwargs):
    return {
        "questions": [
            {
                "id": "q1",
                "topic": kwargs["topics"][0]["topic_name"],
                "question": "Choose A",
                "options": ["A. yes", "B. no", "C. maybe", "D. none"],
                "answer": "A",
                "explanation": "A is correct",
            }
        ]
    }


def service(tmp_path, **kwargs):
    return LearningChainService(
        db_path=tmp_path / "learning.db",
        user_id="alice",
        question_generator=generate,
        recommendation_generator=None,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_subject_isolation_pending_resume_scores_and_conflicting_submit(tmp_path):
    s = service(tmp_path)
    attempts = {}
    for subject in ["Mathematics", "Chinese", "English"]:
        attempts[subject] = await s.create_attempt(
            chat_session_id="same", subject=subject, topics=["shared-topic"], num_questions=1
        )
    assert len({a["attempt_id"] for a in attempts.values()}) == 3
    english = attempts["English"]
    await s.submit_attempt(attempt_id=english["attempt_id"], answers={"q1": "B"})
    again = await s.submit_attempt(attempt_id=english["attempt_id"], answers={"q1": "B"})
    assert again["duplicate_submission"]
    with pytest.raises(LearningValidationError, match="different|conflict"):
        await s.submit_attempt(attempt_id=english["attempt_id"], answers={"q1": "A"})
    s = service(tmp_path)
    for subject in ["Mathematics", "Chinese"]:
        state = await s.get_state(chat_session_id="same", subject=subject)
        assert state["pending_attempt"]["attempt_id"] == attempts[subject]["attempt_id"]
        assert state["topic_scores"] == []
        resumed = await s.create_attempt(chat_session_id="same", subject=subject, num_questions=1)
        assert resumed["attempt_id"] == attempts[subject]["attempt_id"]
    state = await s.get_state(chat_session_id="same", subject="English")
    assert state["topic_scores"][0]["total"] == 1
    assert state["last_result"]["score"] == 0
    assert state["pending_attempt"] is None


@pytest.mark.asyncio
async def test_unknown_chinese_topics_are_distinct_and_invalid_subject_rejected(tmp_path):
    s = service(tmp_path)
    ids = []
    for topic in ["倒敘技巧", "環境描寫"]:
        a = await s.create_attempt(
            chat_session_id=topic, subject="Chinese", topics=[topic], num_questions=1
        )
        ids.append(a["questions"][0]["topic_id"])
    assert len(set(ids)) == 2
    for subject in ["Physics", "", None]:
        with pytest.raises(LearningValidationError):
            await s.get_state(subject=subject)


@pytest.mark.asyncio
async def test_parallel_creation_keeps_one_pending_per_subject(tmp_path):
    s = service(tmp_path)

    async def delayed(**kw):
        await asyncio.sleep(0)
        return await generate(**kw)

    s.question_generator = delayed
    a, b = await asyncio.gather(
        *[
            s.create_attempt(chat_session_id="same", subject="Chinese", num_questions=1)
            for _ in range(2)
        ]
    )
    assert a["attempt_id"] == b["attempt_id"]


def legacy_db(tmp_path, broken_reference=False):
    path = tmp_path / "learning.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
        CREATE TABLE learning_sessions (
            id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, chat_session_id TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT 'Mathematics', stage TEXT NOT NULL,
            budget_minutes INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(owner_user_id, chat_session_id));
        CREATE TABLE learning_topic_scores (
            owner_user_id TEXT NOT NULL, topic_id TEXT NOT NULL, topic_name TEXT NOT NULL,
            correct INTEGER NOT NULL, total INTEGER NOT NULL, last_percentage REAL NOT NULL,
            updated_at REAL NOT NULL, PRIMARY KEY(owner_user_id, topic_id));
        CREATE TABLE learning_attempts (
            id TEXT PRIMARY KEY, learning_session_id TEXT NOT NULL REFERENCES learning_sessions(id),
            owner_user_id TEXT NOT NULL, activity TEXT NOT NULL, subject TEXT NOT NULL,
            status TEXT NOT NULL, questions_json TEXT NOT NULL, answer_key_json TEXT NOT NULL,
            answers_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
            knowledge_references_json TEXT NOT NULL DEFAULT '[]', grounded INTEGER NOT NULL DEFAULT 0,
            retrieval_status TEXT NOT NULL DEFAULT 'not_requested', created_at REAL NOT NULL,
            submitted_at REAL);
        INSERT INTO learning_sessions VALUES ('old-session', 'alice', 'same', 'Mathematics',
            'awaiting_answer', 15, 1, 1);
        INSERT INTO learning_topic_scores VALUES ('alice', 'algebra', 'Algebra', 2, 3, 66.7, 1);
        """
        )
        conn.execute(
            """INSERT INTO learning_attempts (id, learning_session_id, owner_user_id,
            activity, subject, status, questions_json, answer_key_json, created_at)
            VALUES ('old-attempt', ?, 'alice', 'practice', 'Mathematics', 'awaiting_answer', ?, ?, 1)""",
            (
                "missing" if broken_reference else "old-session",
                json.dumps(
                    [
                        {
                            "id": "q1",
                            "question": "2+2?",
                            "options": ["A. 4", "B. 3", "C. 2", "D. 1"],
                            "topic_id": "algebra",
                            "topic_name": "Algebra",
                        }
                    ]
                ),
                json.dumps({"q1": {"answer": "A", "explanation": "2+2=4"}}),
            ),
        )
    return path


@pytest.mark.asyncio
async def test_legacy_migration_preserves_pending_and_scores_on_repeated_initialization(tmp_path):
    legacy_db(tmp_path)
    for _ in range(2):
        s = service(tmp_path)
        state = await s.get_state(chat_session_id="same")
        assert state["learning_session_id"] == "old-session"
        assert state["pending_attempt"]["attempt_id"] == "old-attempt"
        assert state["topic_scores"][0]["correct"] == 2
        assert (await s.get_state(subject="Chinese"))["topic_scores"] == []
    result = await s.submit_attempt(attempt_id="old-attempt", answers={"q1": "A"})
    assert result["score"] == 1
    state = await s.get_state(chat_session_id="same")
    assert state["topic_scores"][0]["total"] == 4
    await s.create_attempt(chat_session_id="same", subject="Chinese", num_questions=1)
    with sqlite3.connect(tmp_path / "learning.db") as conn:
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_failed_migration_rolls_back_old_tables(tmp_path):
    path = legacy_db(tmp_path, broken_reference=True)
    with pytest.raises(sqlite3.IntegrityError, match="foreign-key"):
        service(tmp_path)
    with sqlite3.connect(path) as conn:
        assert "subject" not in {
            row[1] for row in conn.execute("PRAGMA table_info(learning_topic_scores)")
        }
        assert conn.execute("SELECT total FROM learning_topic_scores").fetchone()[0] == 3
        assert conn.execute("SELECT id FROM learning_sessions").fetchone()[0] == "old-session"
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_new'").fetchall()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "subject,passage",
    [("Chinese", "小明每天步行上學。"), ("English", "Mia walks to school every day.")],
)
async def test_reading_requires_and_persists_passage_without_answer_leak(
    tmp_path, subject, passage
):
    s = service(tmp_path)
    with pytest.raises(LearningGenerationError, match="passage"):
        await s.create_attempt(
            chat_session_id="read", subject=subject, practice_type="reading", num_questions=1
        )
    assert (await s.get_state(chat_session_id="read", subject=subject))["pending_attempt"] is None

    async def reading(**kw):
        result = await generate(**kw)
        result["questions"][0]["passage"] = passage
        return result

    s.question_generator = reading
    a = await s.create_attempt(
        chat_session_id="read", subject=subject, practice_type="reading", num_questions=1
    )
    restored = (await service(tmp_path).get_state(chat_session_id="read", subject=subject))[
        "pending_attempt"
    ]
    assert restored["attempt_id"] == a["attempt_id"]
    q = restored["questions"][0]
    assert q["passage"] == passage
    assert "answer" not in q and "explanation" not in q


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["Chinese", "English", "Mathematics"])
async def test_default_generators_receive_correct_subject(monkeypatch, subject):
    from deeptutor.services.learning.service import (
        _default_question_generator,
        _default_concept_generator,
        _default_recommendation_generator,
    )

    prompts = []

    async def fake_llm(prompt, **kw):
        prompts.append((prompt, kw.get("system_prompt", "")))
        return '{"questions": [], "summary": "ok"}'

    monkeypatch.setattr("deeptutor.services.llm.complete", fake_llm)
    await _default_question_generator(
        subject=subject,
        activity="practice",
        topics=[],
        num_questions=1,
        kb_name=None,
        language="en",
    )
    await _default_concept_generator(subject=subject, concept="test", kb_name=None, language="en")
    await _default_recommendation_generator(
        subject=subject, profile=[], weak_topics=[], language="en"
    )
    for prompt, _ in prompts:
        assert subject in prompt
        if subject != "Mathematics":
            assert "Mathematics" not in prompt
