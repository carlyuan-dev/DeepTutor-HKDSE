from __future__ import annotations

from typing import Any

import pytest


def _question_payload() -> dict[str, Any]:
    return {
        "questions": [
            {
                "id": "q1",
                "topic": "Algebra",
                "difficulty": "easy",
                "question": "Solve 2x + 1 = 5.",
                "options": ["A. x = 1", "B. x = 2", "C. x = 3", "D. x = 4"],
                "answer": "B",
                "explanation": "Subtract 1, then divide by 2.",
            },
            {
                "id": "q2",
                "topic": "Probability",
                "difficulty": "medium",
                "question": "A fair coin is tossed once. What is P(heads)?",
                "options": ["A. 0", "B. 1/4", "C. 1/2", "D. 1"],
                "answer": "C",
                "explanation": "There is one favourable outcome out of two.",
            },
        ],
        "grounded": False,
        "retrieval_status": "not_requested",
        "knowledge_references": [],
    }


@pytest.mark.asyncio
async def test_learning_attempt_recovers_and_duplicate_submit_does_not_rescore(tmp_path) -> None:
    from deeptutor.services.learning import LearningChainService

    generated = 0

    async def question_generator(**_kwargs: Any) -> dict[str, Any]:
        nonlocal generated
        generated += 1
        return _question_payload()

    db_path = tmp_path / "learning.db"
    service = LearningChainService(
        db_path=db_path,
        user_id="u-alice",
        question_generator=question_generator,
        recommendation_generator=None,
    )

    empty = await service.get_state(chat_session_id="chat-1")
    assert empty["stage"] == "needs_diagnostic"
    assert empty["has_history"] is False

    created = await service.create_attempt(
        chat_session_id="chat-1",
        activity="diagnostic",
        topics=["algebra", "Probability"],
        num_questions=2,
        language="en",
    )
    assert created["stage"] == "awaiting_answer"
    assert created["resumed"] is False
    assert generated == 1
    assert all("answer" not in question for question in created["questions"])

    # A new service object simulates refresh/reconnect. The pending attempt
    # comes from SQLite and no second generation call is made.
    reloaded = LearningChainService(
        db_path=db_path,
        user_id="u-alice",
        question_generator=question_generator,
        recommendation_generator=None,
    )
    state = await reloaded.get_state(chat_session_id="chat-1")
    assert state["pending_attempt"]["attempt_id"] == created["attempt_id"]
    resumed = await reloaded.create_attempt(
        chat_session_id="chat-1",
        activity="practice",
        topics=["Geometry"],
        num_questions=1,
    )
    assert resumed["attempt_id"] == created["attempt_id"]
    assert resumed["resumed"] is True
    assert generated == 1

    result = await reloaded.submit_attempt(
        attempt_id=created["attempt_id"],
        answers={"q1": "B", "q2": "A"},
    )
    assert result["score"] == 1
    assert result["total"] == 2
    assert result["percentage"] == 50.0
    assert result["duplicate_submission"] is False
    assert result["details"][0]["correct_answer"] == "B"

    duplicate = await reloaded.submit_attempt(
        attempt_id=created["attempt_id"],
        answers={"q1": "A", "q2": "C"},
    )
    assert duplicate["duplicate_submission"] is True
    assert duplicate["score"] == 1

    final_state = await reloaded.get_state(chat_session_id="chat-1")
    algebra = next(row for row in final_state["topic_scores"] if row["topic_id"] == "algebra")
    probability = next(
        row for row in final_state["topic_scores"] if row["topic_id"] == "probability"
    )
    assert (algebra["correct"], algebra["total"]) == (1, 1)
    assert (probability["correct"], probability["total"]) == (0, 1)


@pytest.mark.asyncio
async def test_invalid_or_cross_user_submission_is_rejected_and_failure_preserves_results(
    tmp_path,
) -> None:
    from deeptutor.services.learning import (
        LearningAccessError,
        LearningChainService,
        LearningGenerationError,
        LearningValidationError,
    )

    async def question_generator(**_kwargs: Any) -> dict[str, Any]:
        return _question_payload()

    db_path = tmp_path / "learning.db"
    alice = LearningChainService(
        db_path=db_path,
        user_id="u-alice",
        question_generator=question_generator,
        recommendation_generator=None,
    )
    created = await alice.create_attempt(
        chat_session_id="chat-1",
        activity="diagnostic",
        topics=["algebra"],
        num_questions=2,
    )

    with pytest.raises(LearningValidationError, match="all questions"):
        await alice.submit_attempt(attempt_id=created["attempt_id"], answers={"q1": "B"})

    with pytest.raises(LearningValidationError, match="q1"):
        await alice.submit_attempt(
            attempt_id=created["attempt_id"],
            answers={"q1": "Definitely B", "q2": "C"},
        )

    bob = LearningChainService(db_path=db_path, user_id="u-bob")
    with pytest.raises(LearningAccessError):
        await bob.submit_attempt(
            attempt_id=created["attempt_id"],
            answers={"q1": "B", "q2": "C"},
        )

    await alice.submit_attempt(
        attempt_id=created["attempt_id"],
        answers={"q1": "B", "q2": "C"},
    )

    async def broken_generator(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("provider unavailable")

    failing = LearningChainService(
        db_path=db_path,
        user_id="u-alice",
        question_generator=broken_generator,
        recommendation_generator=None,
    )
    with pytest.raises(LearningGenerationError, match="provider unavailable"):
        await failing.create_attempt(
            chat_session_id="chat-2",
            activity="practice",
            topics=["geometry"],
            num_questions=1,
        )

    preserved = await failing.get_state(chat_session_id="chat-1")
    assert preserved["last_result"]["score"] == 2
    assert preserved["topic_scores"]


@pytest.mark.asyncio
async def test_recommendation_failure_does_not_roll_back_deterministic_score(tmp_path) -> None:
    from deeptutor.services.learning import LearningChainService

    async def question_generator(**_kwargs: Any) -> dict[str, Any]:
        return _question_payload()

    async def broken_recommendation(**_kwargs: Any) -> str:
        raise RuntimeError("coach model unavailable")

    service = LearningChainService(
        db_path=tmp_path / "learning.db",
        user_id="u-alice",
        question_generator=question_generator,
        recommendation_generator=broken_recommendation,
    )
    attempt = await service.create_attempt(
        chat_session_id="chat-1",
        activity="diagnostic",
        topics=["algebra", "probability"],
        num_questions=2,
    )
    result = await service.submit_attempt(
        attempt_id=attempt["attempt_id"],
        answers={"q1": "B", "q2": "C"},
    )

    assert result["score"] == 2
    assert result["recommendation"] == ""
    assert result["recommendation_status"] == "failed"
    state = await service.get_state(chat_session_id="chat-1")
    assert state["last_result"]["score"] == 2
