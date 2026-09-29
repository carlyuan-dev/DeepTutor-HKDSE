"""Reading learning-loop contracts with offline LLM/RAG boundaries."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from deeptutor.api.routers import exam_grader, hkdse_chinese
from deeptutor.api.routers.hkdse_english import paper as hkdse_english


QUESTION = {
    "id": "q1", "type": "short_answer", "question": "Why did she leave?",
    "answer": "To help", "explanation": "The final paragraph states her reason.",
    "topic": "Inference", "points": 3,
}


def test_grade_request_accepts_context_and_legacy_defaults():
    legacy = exam_grader.GradeRequest(questions=[QUESTION], student_answers={})
    assert legacy.model_dump() == {
        "questions": [{**QUESTION, "options": None}], "student_answers": {},
        "passage": "", "subject": "", "kb_name": None,
    }
    req = exam_grader.GradeRequest(
        questions=[QUESTION], student_answers={}, passage="Full passage",
        subject="English", kb_name="reading-kb",
    )
    assert req.model_dump()["kb_name"] == "reading-kb"
    assert req.model_dump()["passage"] == "Full passage"
    assert req.model_dump()["subject"] == "English"


@pytest.mark.parametrize("context", [{}, {
    "passage": "Opening paragraph.\n" + "Long passage. " * 400 + "Final evidence.",
    "subject": "English reading", "kb_name": "reading-kb",
}])
def test_grade_prompt_preserves_evidence_and_totals(monkeypatch, context):
    complete = AsyncMock(return_value=json.dumps({"results": [{"score": 2}]}))
    monkeypatch.setattr(exam_grader, "llm_complete", complete)
    req = exam_grader.GradeRequest(
        questions=[QUESTION], student_answers={"q1": "  To help  "}, **context,
    )
    result = asyncio.run(exam_grader.grade_submission(req))
    prompt = complete.call_args.args[0]
    assert QUESTION["explanation"] in prompt
    assert '"student_answer": "To help"' in prompt
    for field in ("passage", "subject"):
        if field in context:
            assert context[field] in prompt
    assert result["total_score"] == 2
    assert result["max_score"] == 3
    assert result["percentage"] == 66.7


@pytest.mark.parametrize("api,passage_type,constraints", [
    (hkdse_chinese, "\u6587\u8a00\u6587", {"language_form": "classical"}),
    (hkdse_english, "narrative", {"genre": "narrative"}),
])
@pytest.mark.parametrize("focus", [None, "Inference and vocabulary in context"])
@pytest.mark.parametrize("kb_name", [None, "reading-kb"])
def test_paper_focus_reaches_prompt_and_query(
    monkeypatch, api, passage_type, constraints, focus, kb_name,
):
    complete = AsyncMock(return_value=json.dumps({
        "title": "Practice", "passage": "Generated text", "questions": [{}],
    }))
    retrieve = AsyncMock(return_value="Retrieved reference material")
    monkeypatch.setattr(api, "llm_complete", complete)
    monkeypatch.setattr(api, "_rag_retrieve", retrieve)
    fields = {} if focus is None else {"topic_focus": focus}
    req = api.GeneratePaperRequest(
        kb_name=kb_name, passage_type=passage_type, title="Practice",
        num_questions=5, difficulty="hard", question_types=["short_answer"], **fields,
    )

    async def consume():
        response = await api.generate_paper(req)
        return [json.loads(chunk) async for chunk in response.body_iterator]

    events = asyncio.run(consume())
    assert events[-1]["type"] == "done"
    assert events[-1]["paper"]["questions"] == [
        {"id": "q1", "points": 2, "topic": "General", "explanation": ""},
    ]
    prompt = complete.call_args.args[0]
    for retained in ("Practice", "hard", "5", "short_answer"):
        assert retained in prompt
    if focus:
        assert focus in prompt
    assert req.model_dump().get("topic_focus") == (focus or "")
    if kb_name:
        assert "Retrieved reference material" in prompt
        assert retrieve.call_args.args[0] == kb_name
        query = retrieve.call_args.args[1]
        assert passage_type in query
        assert retrieve.call_args.kwargs["metadata_constraints"] == constraints
        if focus:
            assert focus in query
        else:
            assert query == passage_type
    else:
        retrieve.assert_not_called()
