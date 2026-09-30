import json
import asyncio
from types import SimpleNamespace

import pytest

from deeptutor.runtime.registry.tool_registry import ToolRegistry
from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
from deeptutor.core.context import UnifiedContext
from deeptutor.services.learning import LearningChainService


@pytest.mark.asyncio
async def test_generic_tool_contract_subject_required_and_legacy_math_fixed(monkeypatch, tmp_path):
    async def generate(**kw):
        return {
            "questions": [
                {
                    "id": "q1",
                    "topic": kw["topics"][0]["topic_name"],
                    "question": "Choose A",
                    "options": ["A. yes", "B. no", "C. maybe", "D. none"],
                    "answer": "A",
                }
            ]
        }

    svc = LearningChainService(
        db_path=tmp_path / "s.db",
        user_id="real-user",
        question_generator=generate,
        recommendation_generator=None,
    )
    monkeypatch.setattr("deeptutor.services.learning.get_learning_service", lambda: svc)
    registry = ToolRegistry()
    registry.load_builtins()
    schemas = {
        s["function"]["name"]: s["function"]["parameters"]
        for s in registry.build_openai_schemas(
            ["create_learning_practice", "explain_learning_concept", "get_learning_state"]
        )
    }
    assert "create_learning_practice" in schemas
    for schema in schemas.values():
        assert "subject" in schema["required"]
        assert schema["properties"]["subject"]["enum"] == ["Mathematics", "Chinese", "English"]
    missing = await registry.execute("create_learning_practice", session_id="chat", num_questions=1)
    assert not missing.success
    created = await registry.execute(
        "create_learning_practice",
        session_id="chat",
        subject="English",
        num_questions=1,
        user_id="forged",
    )
    assert created.success
    assert json.loads(created.content)["subject"] == "English"
    legacy = await registry.execute(
        "create_math_practice", session_id="chat", subject="Chinese", num_questions=1
    )
    assert json.loads(legacy.content)["subject"] == "Mathematics"
    assert (await svc.get_state(chat_session_id="chat", subject="Chinese"))["has_history"] is False


def test_generic_kwargs_use_server_session_and_attached_kb_only():
    pipeline = AgenticChatPipeline(language="en")
    ctx = UnifiedContext(session_id="real-chat", language="en", user_message="English practice")
    args = pipeline._augment_tool_kwargs(
        "create_learning_practice",
        {"session_id": "forged", "subject": "English", "kb_name": "not-attached"},
        ctx,
    )
    assert args["session_id"] == "real-chat"
    assert "kb_name" not in args


def test_legacy_unknown_math_topic_id_is_preserved():
    from deeptutor.services.learning.service import _normalise_topic

    assert _normalise_topic("Special Geometry")["topic_id"] == "unmapped:special-geometry"


@pytest.mark.asyncio
async def test_learning_batch_waits_for_submit_before_reading(monkeypatch):
    from deeptutor.core.stream_bus import StreamBus
    from deeptutor.core.tool_protocol import ToolResult

    complete = False

    class Registry:
        async def execute(self, name, **kwargs):
            nonlocal complete
            if name == "submit_learning_answer":
                await asyncio.sleep(0.01)
                complete = True
            else:
                assert complete, "state read raced with score persistence"
            return ToolResult(content="ok")

    pipeline = AgenticChatPipeline(language="en")
    pipeline.registry = Registry()
    result = await pipeline._dispatch_tool_calls(
        tool_calls=[
            {"id": "submit", "name": "submit_learning_answer", "arguments": "{}"},
            {"id": "state", "name": "get_learning_state", "arguments": "{}"},
        ],
        context=UnifiedContext(session_id="chat"),
        stream=StreamBus(),
        iteration_index=1,
    )
    assert all(m["content"] == "ok" for m in result.tool_messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["Chinese", "English"])
async def test_saved_reading_card_preserves_passage_and_checks_chat(monkeypatch, tmp_path, subject):
    passage = "Reading material 閱讀原文。" * 100

    async def generate(**kw):
        return {
            "questions": [
                {
                    "id": "q1",
                    "topic": "Reading",
                    "passage": passage,
                    "question": "Choose A",
                    "options": ["A. yes", "B. no", "C. maybe", "D. none"],
                    "answer": "A",
                    "explanation": "PRIVATE ANSWER REASON",
                }
            ]
        }

    svc = LearningChainService(
        db_path=tmp_path / "s.db", user_id="real-user", question_generator=generate
    )
    monkeypatch.setattr("deeptutor.services.learning.get_learning_service", lambda: svc)
    attempt = await svc.create_attempt(
        chat_session_id="chat", subject=subject, num_questions=1, practice_type="reading"
    )
    registry = ToolRegistry()
    registry.load_builtins()
    args = dict(learning_attempt_id=attempt["attempt_id"], question_ids=["q1"], session_id="chat")
    result = await registry.execute("ask_user", **args)
    assert result.success
    card = result.pause_for_user
    assert passage in card["questions"][0]["prompt"]
    assert "PRIVATE ANSWER REASON" not in json.dumps(card)
    assert not (await registry.execute("ask_user", **{**args, "session_id": "other"})).success
    assert not (await registry.execute("ask_user", **{**args, "question_ids": ["unknown"]})).success
