"""Core grading contracts; only the external LLM boundary is replaced."""
import asyncio
import copy
import json

import pytest

from deeptutor.api.routers.hkdse_english import essay as api


def grade(scores=(3, 4, 5)):
    return {
        **{dim: {"score": score, "max_score": 7, "comment": "Evidence"}
           for dim, score in zip(api._ENGLISH_DIMS, scores)},
        "strengths": ["Clear idea"], "improvements": ["Add detail"],
        "overall_comment": "Original", "annotated_essay": "Essay",
    }


def run(monkeypatch, ratings, reflection=None, mode="review"):
    async def complete(prompt, system_prompt, **kwargs):
        for persona, style in api._EN_AGENT_PERSONAS.items():
            if style in system_prompt:
                value = ratings[persona]
                if isinstance(value, Exception):
                    raise value
                return json.dumps(value)
        if isinstance(reflection, Exception):
            raise reflection
        return json.dumps(reflection or {"reflection_note": "Reviewed", "revised_overall_comment": "Revised"})
    monkeypatch.setattr(api, "llm_complete", complete)
    return asyncio.run(api.grade_essay(api.EssayGradeRequest(essay="Test essay", mode=mode)))


def test_medians_and_disagreement_are_exposed(monkeypatch):
    result = run(monkeypatch, {"strict": grade((0, 1, 2)), "lenient": grade((7, 7, 7)), "balanced": grade((4, 5, 6))})
    assert result["total_score"] == 15
    assert result["content"]["individual_scores"] == [0, 7, 4]
    assert result["ensemble"]["overall_agreement"] == 50
    assert result["ensemble"]["review_recommended"] is True


@pytest.mark.parametrize("invalid", ["missing", "string", "bool", "overflow", "wrong_max", "missing_comment"])
def test_invalid_rater_never_becomes_a_valid_score(monkeypatch, invalid):
    bad = copy.deepcopy(grade())
    if invalid == "missing":
        del bad["content"]
    elif invalid == "missing_comment":
        del bad["content"]["comment"]
    else:
        key, value = {"string": ("score", "5"), "bool": ("score", True), "overflow": ("score", 8), "wrong_max": ("max_score", 0)}[invalid]
        bad["content"][key] = value
    result = run(monkeypatch, {"strict": grade(), "lenient": grade(), "balanced": bad})
    assert "error" in result
    assert "total_score" not in result


def test_reflection_cannot_claim_a_score_change(monkeypatch):
    result = run(monkeypatch, {p: grade() for p in api._EN_AGENT_PERSONAS}, {"score_adjusted": True, "reflection_note": "Reviewed", "revised_overall_comment": "Revised"})
    assert result["total_score"] == 12
    assert result["overall_comment"] == "Revised"
    assert result["reflection"]["score_adjusted"] is False
    assert result["ensemble"]["review_recommended"] is False


def test_reflection_failure_preserves_grade(monkeypatch):
    result = run(monkeypatch, {p: grade() for p in api._EN_AGENT_PERSONAS}, TimeoutError("offline"))
    assert result["total_score"] == 12
    assert result["overall_comment"] == "Original"
    assert result["reflection"]["performed"] is False


def test_one_rater_failure_returns_balanced_without_consensus(monkeypatch):
    result = run(monkeypatch, {"strict": TimeoutError("offline"), "lenient": grade(), "balanced": grade()})
    assert result["total_score"] == 12
    assert result["grading"]["review_status"] == "incomplete"
    assert result["grading"]["strategy_used"] == "balanced"
    assert "ensemble" not in result
    assert "individual_scores" not in result["content"]


def test_balanced_failure_never_uses_other_raters(monkeypatch):
    result = run(monkeypatch, {"strict": grade(), "lenient": grade(), "balanced": TimeoutError("secret")})
    assert "error" in result
    assert "total_score" not in result
    assert result["retryable"] is True
    assert result["grading"]["review_status"] == "failed"
    assert "secret" not in json.dumps(result)


def test_default_runs_only_balanced_grading(monkeypatch):
    calls = []
    async def complete(prompt, system_prompt, **kwargs):
        calls.append(system_prompt)
        return json.dumps(grade() if "grading style" in system_prompt else {})
    monkeypatch.setattr(api, "llm_complete", complete)
    result = asyncio.run(api.grade_essay(api.EssayGradeRequest(essay="Essay")))
    assert len([p for p in calls if "grading style" in p]) == 1
    assert api._EN_AGENT_PERSONAS["balanced"] in calls[0]
    assert result["grading"]["review_status"] == "not_requested"
    assert result["total_score"] == 12
    assert "ensemble" not in result


def test_review_timeout_is_bounded_and_degrades(monkeypatch):
    monkeypatch.setattr(api, "_ESSAY_CALL_TIMEOUT", 0.01, raising=False)
    async def complete(prompt, system_prompt, **kwargs):
        if api._EN_AGENT_PERSONAS["strict"] in system_prompt:
            await asyncio.sleep(10)
        return json.dumps(grade() if "grading style" in system_prompt else {})
    monkeypatch.setattr(api, "llm_complete", complete)
    async def invoke():
        return await asyncio.wait_for(api.grade_essay(api.EssayGradeRequest(essay="Essay", mode="review")), 0.5)
    result = asyncio.run(invoke())
    assert result["total_score"] == 12
    assert result["grading"]["failures"][0]["category"] == "timeout"


def test_provider_diagnostics_exclude_message_and_keep_safe_metadata(monkeypatch, caplog):
    from deeptutor.services.llm.exceptions import LLMAPIError
    error = LLMAPIError("SECRET_KEY and private essay", status_code=429)
    error.request_id = "req-123"
    result = run(monkeypatch, {"strict": error, "lenient": grade(), "balanced": grade()})
    detail = result["grading"]["failures"][0]
    assert detail["status_code"] == 429
    assert detail["provider_request_id"] == "req-123"
    assert detail["category"] == "rate_limit"
    assert "SECRET_KEY" not in json.dumps(result) + caplog.text


def test_real_adapter_metadata_survives_factory_mapping(monkeypatch, caplog):
    from deeptutor.services.llm import factory
    from deeptutor.services.llm.config import LLMConfig
    from deeptutor.services.llm.provider_core.openai_compat_provider import OpenAICompatProvider
    error = RuntimeError("PRIVATE_BODY")
    error.status_code = 429
    error.request_id = "req-provider"
    response = OpenAICompatProvider._handle_error(error)
    class Provider:
        async def chat_with_retry(self, **kwargs):
            return response
    monkeypatch.setattr(factory, "get_runtime_provider", lambda c: Provider())
    monkeypatch.setattr(factory, "_resolve_call_config", lambda **kw: (LLMConfig(model="test", api_key="test"), None))
    monkeypatch.setattr(api, "llm_complete", factory.complete)
    result = asyncio.run(api.grade_essay(api.EssayGradeRequest(essay="Essay")))
    failure = result["grading"]["failures"][0]
    assert failure["status_code"] == 429
    assert failure["provider_request_id"] == "req-provider"
    assert "PRIVATE_BODY" not in json.dumps(result) + caplog.text
