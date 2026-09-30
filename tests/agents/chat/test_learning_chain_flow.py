from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType
from deeptutor.core.stream_bus import StreamBus
from deeptutor.runtime.registry.tool_registry import ToolRegistry


def _chunk(
    *, content: str | None = None, tool_calls: list[dict[str, Any]] | None = None
) -> SimpleNamespace:
    calls = None
    if tool_calls is not None:
        calls = [
            SimpleNamespace(
                index=index,
                id=call["id"],
                function=SimpleNamespace(
                    name=call["name"], arguments=json.dumps(call.get("arguments") or {})
                ),
            )
            for index, call in enumerate(tool_calls)
        ]
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=calls))]
    )


async def _stream(*chunks: SimpleNamespace):
    for item in chunks:
        yield item


class _ObservationDrivenClient:
    """Tiny deterministic policy that chooses each action from tool observations."""

    def __init__(self, subject="Mathematics") -> None:
        self.call_count = 0
        self.observed_attempt_id = ""
        self.calls: list[list[dict[str, Any]]] = []

        parent = self

        class _Completions:
            async def create(self, **kwargs: Any):
                parent.call_count += 1
                messages = list(kwargs.get("messages") or [])
                parent.calls.append(messages)
                tool_messages = [m for m in messages if m.get("role") == "tool"]

                if parent.call_count == 1:
                    return _stream(
                        _chunk(content="``TOOL``\nI will inspect saved learning state."),
                        _chunk(
                            tool_calls=[
                                {
                                    "id": "state",
                                    "name": "get_learning_state",
                                    "arguments": {"subject": subject},
                                }
                            ]
                        ),
                    )

                if parent.call_count == 2:
                    state = json.loads(tool_messages[-1]["content"])
                    assert state["stage"] == "needs_diagnostic"
                    return _stream(
                        _chunk(
                            content="``TOOL``\nNo history exists, so I will create a diagnostic."
                        ),
                        _chunk(
                            tool_calls=[
                                {
                                    "id": "create",
                                    "name": "create_learning_practice",
                                    "arguments": {
                                        "subject": subject,
                                        "activity": "diagnostic",
                                        "topics": ["Algebra"],
                                        "num_questions": 1,
                                        "budget_minutes": 15,
                                    },
                                }
                            ]
                        ),
                    )

                if parent.call_count == 3:
                    attempt = json.loads(tool_messages[-1]["content"])
                    parent.observed_attempt_id = attempt["attempt_id"]
                    question = attempt["questions"][0]
                    return _stream(
                        _chunk(content="``TOOL``\nI will pause for the learner's answer."),
                        _chunk(
                            tool_calls=[
                                {
                                    "id": "ask",
                                    "name": "ask_user",
                                    "arguments": {
                                        "learning_attempt_id": attempt["attempt_id"],
                                        "question_ids": [question["id"]],
                                    },
                                }
                            ]
                        ),
                    )

                if parent.call_count == 4:
                    assert "User answered: A" in tool_messages[-1]["content"]
                    assert parent.observed_attempt_id
                    return _stream(
                        _chunk(content="``TOOL``\nI will submit against the server answer key."),
                        _chunk(
                            tool_calls=[
                                {
                                    "id": "submit",
                                    "name": "submit_learning_answer",
                                    "arguments": {
                                        "attempt_id": parent.observed_attempt_id,
                                        "answers": [{"question_id": "q1", "answer": "A"}],
                                    },
                                }
                            ]
                        ),
                    )

                result = json.loads(tool_messages[-1]["content"])
                assert result["score"] == 1
                return _stream(_chunk(content="``FINISH``\nYou scored 1/1; the result was saved."))

        self.chat = SimpleNamespace(completions=_Completions())


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["Mathematics", "Chinese", "English"])
async def test_chat_agent_uses_learning_observations_then_pauses_and_scores(
    monkeypatch: pytest.MonkeyPatch, tmp_path, subject
) -> None:
    from deeptutor.services.learning import LearningChainService

    async def question_generator(**_kwargs: Any) -> dict[str, Any]:
        return {
            "questions": [
                {
                    "id": "q1",
                    "topic": "Algebra",
                    "difficulty": "easy",
                    "question": "What is 3 + 4?",
                    "options": ["A. 7", "B. 6", "C. 8", "D. 9"],
                    "answer": "A",
                    "explanation": "3 + 4 = 7.",
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
    monkeypatch.setattr(
        "deeptutor.agents.chat.agentic_pipeline.get_llm_config",
        lambda: SimpleNamespace(
            binding="openai",
            model="gpt-test",
            api_key="k",
            base_url="u",
            api_version=None,
            extra_headers={},
            reasoning_effort=None,
            context_window=32768,
            max_tokens=4096,
        ),
    )
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.user_has_memory", lambda: False)
    monkeypatch.setattr("deeptutor.agents.chat.agentic_pipeline.user_has_notebooks", lambda: False)

    registry = ToolRegistry()
    registry.load_builtins()
    client = _ObservationDrivenClient(subject)
    pipeline = AgenticChatPipeline(language="en")
    pipeline.registry = registry
    monkeypatch.setattr(pipeline, "_build_openai_client", lambda: client)

    async def wait_for_reply() -> str:
        return "A"

    bus = StreamBus()
    events: list[StreamEvent] = []

    async def consume() -> None:
        async for event in bus.subscribe():
            events.append(event)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await pipeline.run(
        UnifiedContext(
            session_id="chat-1",
            user_message=(
                "Use my last math weaknesses to plan a 15 minute review; explain only if "
                "needed, otherwise practice, then update my learning record."
            ),
            enabled_tools=[],
            language="en",
            metadata={"turn_id": "turn-1", "wait_for_user_reply": wait_for_reply},
        ),
        bus,
    )
    await bus.close()
    await consumer

    assert client.call_count == 5
    assert client.observed_attempt_id
    called_tools = [event.content for event in events if event.type == StreamEventType.TOOL_CALL]
    assert called_tools == [
        "get_learning_state",
        "create_learning_practice",
        "ask_user",
        "submit_learning_answer",
    ]
    result = [event for event in events if event.type == StreamEventType.RESULT][-1]
    assert result.metadata["completed"] is True
    assert result.metadata["response"] == "You scored 1/1; the result was saved."
    state = await service.get_state(chat_session_id="chat-1", subject=subject)
    assert state["stage"] == "completed"
    assert state["last_result"]["score"] == 1
