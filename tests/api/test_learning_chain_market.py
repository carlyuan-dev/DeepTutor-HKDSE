from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_market_diagnostic_uses_shared_service_without_exposing_answer_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from deeptutor.api.routers import market_tools
    from deeptutor.services.learning import LearningChainService

    async def question_generator(**_kwargs: Any) -> dict[str, Any]:
        return {
            "questions": [
                {
                    "id": "q1",
                    "topic": "Algebra",
                    "difficulty": "easy",
                    "question": "What is x if x + 2 = 5?",
                    "options": ["A. 1", "B. 2", "C. 3", "D. 4"],
                    "answer": "C",
                    "explanation": "Subtract 2 from both sides.",
                }
            ],
            "grounded": False,
            "retrieval_status": "not_requested",
            "knowledge_references": [],
        }

    service = LearningChainService(
        db_path=tmp_path / "learning.db",
        user_id="u-alice",
        question_generator=question_generator,
        recommendation_generator=None,
    )
    monkeypatch.setattr("deeptutor.services.learning.get_learning_service", lambda: service)

    async def direct_router_llm_is_forbidden(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("diagnostic REST handlers must use LearningChainService")

    monkeypatch.setattr(market_tools, "llm_complete", direct_router_llm_is_forbidden)

    generated = await market_tools.diagnostic_generate(
        market_tools.DiagnosticRequest(
            subject="Mathematics",
            topics=["Algebra"],
            num_questions=1,
            language="en",
            session_id="market-chat-1",
        )
    )
    assert generated["attempt_id"]
    assert generated["session_id"] == "market-chat-1"
    assert generated["questions"][0]["question"] == "What is x if x + 2 = 5?"
    assert "answer" not in generated["questions"][0]

    graded = await market_tools.diagnostic_grade(
        market_tools.DiagnosticGradeRequest(
            attempt_id=generated["attempt_id"],
            answers={"q1": "C"},
            language="en",
        )
    )
    assert graded["score"] == 1
    assert graded["percentage"] == 100.0

    state = await service.get_state(chat_session_id="market-chat-1")
    assert state["last_result"]["attempt_id"] == generated["attempt_id"]
    assert [event["action"] for event in state["events"]] == [
        "create_diagnostic",
        "submit_answers",
    ]
