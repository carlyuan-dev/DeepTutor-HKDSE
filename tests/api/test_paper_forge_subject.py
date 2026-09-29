"""PaperForge subject propagation through real HTTP requests, offline."""

import json
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import paper_forge


@pytest.mark.parametrize("subject_fields", [{}, {"subject": ""}, {"subject": "Physics"}])
@pytest.mark.parametrize("focus", ["", "Energy conservation"])
@pytest.mark.parametrize("kb_name", [None, "science-kb"])
def test_subject_reaches_generation_without_changing_retrieval(
    monkeypatch, subject_fields, focus, kb_name,
):
    complete = AsyncMock(return_value=json.dumps({
        "title": "Practice", "questions": [{"question": "Explain energy."}],
    }))
    retrieve = AsyncMock(return_value="Reference evidence")
    monkeypatch.setattr(paper_forge, "llm_complete", complete)
    monkeypatch.setattr(paper_forge, "_rag_retrieve", retrieve)
    app = FastAPI()
    app.include_router(paper_forge.router, prefix="/api/v1/paper-forge")
    with TestClient(app) as client:
        response = client.post("/api/v1/paper-forge/generate", json={
            "title": "Practice", "kb_name": kb_name, "topic_focus": focus,
            "num_questions": 1, "question_types": ["short_answer"],
            **subject_fields,
        })
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1] == {"type": "done", "paper": {
        "title": "Practice", "questions": [{
            "question": "Explain energy.", "id": "q1", "points": 2,
            "topic": "General", "explanation": "",
        }],
    }}
    prompt = complete.call_args.args[0]
    if subject_fields.get("subject"):
        assert "Subject: Physics" in prompt
    else:
        assert "Subject:" not in prompt
    assert "Total questions: 1" in prompt
    assert "short_answer = Short Answer" in prompt
    if focus:
        assert "Focus on the topic: Energy conservation" in prompt
    if kb_name:
        retrieve.assert_awaited_once_with("science-kb", focus or "Practice")
        assert "Reference evidence" in prompt
    else:
        retrieve.assert_not_called()


def test_subject_defaults_to_empty_string():
    assert paper_forge.GenerateRequest().model_dump().get("subject") == ""
