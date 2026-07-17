import json
from pathlib import Path

import deeptutor.api.routers.hkdse_english as hkdse_english
from deeptutor.api.routers.hkdse_english import (
    OralTurnRequest,
    OralStreamingSanitizer,
    _apply_low_participation_feedback_cap,
    _build_agenda_part_a_prompt,
    _build_oral_feedback_user_prompt,
    _build_part_a_prompt,
    _build_pronunciation_delivery_score,
    _load_oral_topics,
    _plan_next_part_a_turn,
    _summarize_oral_voice_metadata,
    sanitize_oral_text,
)


def _stream_clean(chunks: list[str]) -> str:
    sanitizer = OralStreamingSanitizer()
    output = []
    for chunk in chunks:
        emitted = sanitizer.feed(chunk)
        if emitted:
            output.append(emitted)
    tail = sanitizer.flush()
    if tail:
        output.append(tail)
    return "".join(output)


def test_load_oral_topics_uses_packaged_default() -> None:
    hkdse_english._ORAL_TOPICS_CACHE = None

    topics = _load_oral_topics()

    assert topics
    assert any(topic.get("id") == "2019_1.1" for topic in topics)
    sample = next(topic for topic in topics if topic.get("id") == "2019_1.1")
    assert sample["guiding_questions"]
    assert sample["part_b_questions"]


def test_load_oral_topics_prefers_runtime_import(monkeypatch, tmp_path: Path) -> None:
    imported = tmp_path / "hkdse" / "english" / "paper4" / "oral_topics.json"
    imported.parent.mkdir(parents=True)
    imported.write_text(
        json.dumps(
            {
                "topics": [
                    {
                        "id": "runtime_topic",
                        "category": "education",
                        "topic": "Imported topic",
                        "prompt": "Imported prompt",
                        "guiding_questions": ["imported question"],
                        "part_b_questions": ["imported part b"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    hkdse_english._ORAL_TOPICS_CACHE = None
    monkeypatch.setattr(
        hkdse_english,
        "_oral_topic_candidate_paths",
        lambda: [imported, hkdse_english._ORAL_TOPICS_BUILTIN_PATH],
    )

    try:
        topics = _load_oral_topics()

        assert [topic["id"] for topic in topics] == ["runtime_topic"]
    finally:
        hkdse_english._ORAL_TOPICS_CACHE = None


def test_sanitize_oral_text_removes_complete_think_block() -> None:
    raw = "<think>I should plan this response first.</think>Alright, let's start with the main issue."

    assert sanitize_oral_text(raw) == "Alright, let's start with the main issue."


def test_streaming_sanitizer_handles_think_tag_split_across_chunks() -> None:
    cleaned = _stream_clean([
        "<thi",
        "nk>I need to decide the role.</th",
        "ink>Well, I think redevelopment can help a district,",
        " but it can also put pressure on local residents.",
    ])

    assert "<think>" not in cleaned
    assert "I need to decide" not in cleaned
    assert cleaned == (
        "Well, I think redevelopment can help a district, "
        "but it can also put pressure on local residents."
    )


def test_streaming_sanitizer_discards_unclosed_think_block() -> None:
    cleaned = _stream_clean([
        "<think>This hidden reasoning never closes.",
        " It should not be shown to the student.",
    ])

    assert cleaned == ""


def test_sanitize_oral_text_strips_role_label_and_preamble() -> None:
    assert sanitize_oral_text("Candidate A: We should consider both sides.") == (
        "We should consider both sides."
    )
    assert sanitize_oral_text("Sure, here is my response: I agree with that point.") == (
        "I agree with that point."
    )


def test_streaming_sanitizer_preserves_natural_speech() -> None:
    raw = [
        "I agree with your point because students often need more support, ",
        "especially when the topic is unfamiliar.",
    ]

    assert _stream_clean(raw) == "".join(raw)


def test_streaming_sanitizer_releases_short_natural_opening_quickly() -> None:
    sanitizer = OralStreamingSanitizer()

    assert sanitizer.feed("Well, I think ") == "Well, I think "


def test_turn_policy_opens_with_one_ai_then_hands_to_user() -> None:
    plan = _plan_next_part_a_turn([])

    assert plan.speaker == "candidate_a"
    assert plan.intent == "open_discussion"
    assert plan.target_speaker == "group"
    assert plan.handoff_to_user is True
    assert plan.ask_candidate_d is False


def test_opening_prompt_does_not_turn_handoff_into_candidate_d_question() -> None:
    plan = _plan_next_part_a_turn([])
    prompt = _build_part_a_prompt(plan, OralTurnRequest(topic_id="", history=[]))

    assert "Target to respond to: the group." in prompt
    assert "End with one short, natural question to Candidate D." not in prompt
    assert "Do not ask Candidate D directly." in prompt


def test_turn_policy_varies_rhythm_after_user_turns() -> None:
    after_first_user = [{"speaker": "candidate_d", "content": "I think schools should help more."}]
    plan = _plan_next_part_a_turn(after_first_user)

    assert plan.speaker == "candidate_c"
    assert plan.intent == "agree_and_extend"
    assert plan.handoff_to_user is True
    assert plan.ask_candidate_d is False

    after_second_user = [
        *after_first_user,
        {"speaker": "candidate_c", "content": "Yes, support matters."},
        {"speaker": "candidate_d", "content": "But schools also have limited budgets."},
    ]
    plan = _plan_next_part_a_turn(after_second_user)

    assert plan.speaker == "candidate_b"
    assert plan.intent == "challenge_politely"
    assert plan.handoff_to_user is False
    assert plan.ask_candidate_d is False


def test_turn_policy_second_ai_in_burst_hands_back_to_user() -> None:
    history = [
        {"speaker": "candidate_d", "content": "I think schools should help more."},
        {"speaker": "candidate_c", "content": "Yes, support matters."},
        {"speaker": "candidate_d", "content": "But schools also have limited budgets."},
        {"speaker": "candidate_b", "content": "That sounds good, but cost matters."},
    ]
    plan = _plan_next_part_a_turn(history)

    assert plan.speaker == "candidate_a"
    assert plan.intent == "soften_or_add_example"
    assert plan.target_speaker == "candidate_b"
    assert plan.handoff_to_user is True
    assert plan.ask_candidate_d is False


def test_turn_policy_late_discussion_summarizes_and_hands_off() -> None:
    history = [
        {"speaker": "candidate_d", "content": "First user turn."},
        {"speaker": "candidate_c", "content": "AI reply."},
        {"speaker": "candidate_d", "content": "Second user turn."},
        {"speaker": "candidate_b", "content": "AI challenge."},
        {"speaker": "candidate_a", "content": "AI follow-up."},
        {"speaker": "candidate_d", "content": "Third user turn."},
        {"speaker": "candidate_c", "content": "AI question."},
        {"speaker": "candidate_d", "content": "Fourth user turn."},
    ]
    plan = _plan_next_part_a_turn(history)

    assert plan.speaker == "candidate_b"
    assert plan.intent == "summarize_and_handoff"
    assert plan.target_speaker == "group"
    assert plan.handoff_to_user is True
    assert plan.ask_candidate_d is False


def test_turn_policy_only_explicit_ask_user_targets_candidate_d_question() -> None:
    history = [
        {"speaker": "candidate_d", "content": "First user turn."},
        {"speaker": "candidate_c", "content": "AI reply."},
        {"speaker": "candidate_d", "content": "Second user turn."},
        {"speaker": "candidate_b", "content": "AI challenge."},
        {"speaker": "candidate_a", "content": "AI follow-up."},
        {"speaker": "candidate_d", "content": "Third user turn."},
    ]
    plan = _plan_next_part_a_turn(history)

    assert plan.intent == "ask_user"
    assert plan.target_speaker == "candidate_d"
    assert plan.ask_candidate_d is True


def test_voice_metadata_summary_counts_only_user_voice_turns() -> None:
    history = [
        {"speaker": "candidate_a", "content": "Let's begin.", "voice": {"duration_ms": 1200}},
        {
            "speaker": "candidate_d",
            "content": "I think students should learn how to protect themselves online.",
            "voice": {
                "duration_ms": 4200,
                "word_count": 10,
                "interrupted_ai": True,
                "asr_confidence": 0.91,
            },
        },
        {
            "speaker": "candidate_d",
            "content": "For example, schools can teach us to check suspicious links.",
            "voice": {
                "duration_ms": 5800,
                "word_count": 10,
                "interrupted_ai": False,
                "asr_confidence": 0.83,
            },
        },
    ]

    summary = _summarize_oral_voice_metadata(history)

    assert summary["has_voice_evidence"] is True
    assert summary["user_voice_turns"] == 2
    assert summary["total_duration_ms"] == 10000
    assert summary["total_words"] == 20
    assert summary["words_per_minute"] == 120
    assert summary["interruptions"] == 1
    assert summary["average_asr_confidence"] == 0.87


def test_pronunciation_delivery_score_stays_locked_with_voice_evidence() -> None:
    summary = {
        "has_voice_evidence": True,
        "user_voice_turns": 2,
        "total_duration_ms": 10000,
        "total_words": 20,
        "words_per_minute": 120,
        "interruptions": 1,
        "average_asr_confidence": 0.87,
    }

    score = _build_pronunciation_delivery_score(summary)

    assert score["locked"] is True
    assert score["score"] == 0
    assert score["max_score"] == 7
    assert "120 wpm" in score["comment"]
    assert "not scored yet" in score["comment"]
    assert score["evidence"]["user_voice_turns"] == 2


def test_pronunciation_delivery_score_stays_locked_without_voice_evidence() -> None:
    score = _build_pronunciation_delivery_score({
        "has_voice_evidence": False,
        "user_voice_turns": 0,
        "total_duration_ms": 0,
        "total_words": 0,
        "words_per_minute": 0,
        "interruptions": 0,
        "average_asr_confidence": None,
    })

    assert score["locked"] is True
    assert score["score"] == 0
    assert score["comment"] == "Pronunciation & Delivery is not scored yet because audio-level pronunciation analysis is not available."


def test_agenda_prompt_uses_forced_speaker_and_current_agenda() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[
            {"speaker": "candidate_d", "content": "Redevelopment can make transport more convenient."}
        ],
        speaker="candidate_b",
        agenda_index=1,
        agenda_item="what problems redevelopment cause",
        previous_agenda_item="why old districts are redeveloped",
        agenda_intent="open_agenda_item",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "You are Candidate B" in prompt
    assert "Current agenda item 2: what problems redevelopment cause" in prompt
    assert "Previous agenda item: why old districts are redeveloped" in prompt
    assert "Candidate D: Redevelopment can make transport more convenient." in prompt
    assert "[Candidate" not in prompt
    assert "[Next:" not in prompt


def test_agenda_close_prompt_does_not_move_to_next_topic() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[],
        speaker="candidate_c",
        agenda_index=1,
        agenda_item="how common cheating is",
        previous_agenda_item="why students cheat",
        agenda_intent="close_agenda_item",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "You are Candidate C" in prompt
    assert "briefly close the current agenda item" in prompt
    assert "Do not introduce a new agenda item" in prompt


def test_agenda_open_prompt_bridges_only_at_next_topic_start() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[],
        speaker="candidate_b",
        agenda_index=1,
        agenda_item="how common cheating is",
        previous_agenda_item="why students cheat",
        agenda_intent="open_agenda_item",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "bridge from the previous agenda item" in prompt
    assert "explicitly name or paraphrase the current agenda question" in prompt
    assert "give your own view on the new agenda item" in prompt


def test_agenda_prompt_targets_longer_voice_turns() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[],
        speaker="candidate_a",
        agenda_index=0,
        agenda_item="why old districts are redeveloped",
        agenda_intent="open_agenda_item",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "Use about 60-75 words" in prompt


def test_agenda_prompt_frames_topic_before_answering() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[],
        speaker="candidate_a",
        agenda_index=0,
        agenda_item="why old districts are redeveloped",
        agenda_intent="open_agenda_item",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "briefly introduce what the group should discuss" in prompt
    assert "then give your own view" in prompt


def test_agenda_prompt_bridges_previous_topic_then_gives_new_view() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[],
        speaker="candidate_b",
        agenda_index=1,
        agenda_item="what problems redevelopment cause",
        previous_agenda_item="why old districts are redeveloped",
        agenda_intent="open_agenda_item",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "bridge from the previous agenda item" in prompt
    assert "give your own view on the new agenda item" in prompt


def test_agenda_prompt_includes_polite_stance_instruction() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[{"speaker": "candidate_d", "content": "Sport is important for teenagers."}],
        speaker="candidate_c",
        agenda_index=1,
        agenda_item="whether sport is important to Hong Kong people",
        agenda_intent="respond_and_add",
        agenda_stance="soft_challenge",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "Response stance: soft_challenge" in prompt
    assert "Politely question or qualify one earlier point" in prompt
    assert "Do not sound aggressive" in prompt


def test_agenda_prompt_responds_when_user_opened_agenda() -> None:
    req = OralTurnRequest(
        topic_id="",
        history=[
            {
                "speaker": "candidate_d",
                "content": "Maybe we should move on to how common cheating is. I think it is more common online.",
            }
        ],
        speaker="candidate_a",
        agenda_index=1,
        agenda_item="how common cheating is",
        previous_agenda_item="why students cheat",
        agenda_intent="respond_to_user_opened_agenda",
    )

    prompt = _build_agenda_part_a_prompt(req)

    assert "Agenda intent: respond_to_user_opened_agenda" in prompt
    assert "The user has already opened or shifted to this agenda item" in prompt
    assert "Do not re-introduce the agenda as if nobody has mentioned it" in prompt


def test_oral_feedback_prompt_is_asr_tolerant_for_language_scoring() -> None:
    prompt = _build_oral_feedback_user_prompt(
        [
            {
                "speaker": "candidate_d",
                "content": "why student she first many students are homework because they cannot catch out",
                "voice": {"transcript_source": "web_speech"},
            }
        ],
        "",
    )

    assert "ASR transcript" in prompt
    assert "Do not treat obvious speech-recognition noise as grammatical errors" in prompt
    assert "Do not quote garbled ASR fragments as language evidence" in prompt


def test_oral_feedback_prompt_rewards_user_agenda_control() -> None:
    prompt = _build_oral_feedback_user_prompt(
        [
            {"speaker": "candidate_d", "content": "Let's move on to the next question about solutions."}
        ],
        "",
    )

    assert "Credit the user for useful agenda control" in prompt
    assert "opening a topic" in prompt
    assert "moving the group to the next guiding question" in prompt


def test_oral_feedback_prompt_scores_candidate_d_only() -> None:
    prompt = _build_oral_feedback_user_prompt(
        [
            {"speaker": "candidate_d", "content": "Testing."},
            {
                "speaker": "candidate_a",
                "content": "The main driver is shortage of space and the cultural gap is a major hurdle.",
            },
        ],
        "",
    )

    assert "Score Candidate D only" in prompt
    assert "Do not credit Candidate D for ideas, vocabulary, transitions, or acknowledgements spoken by Candidate A, Candidate B, Candidate C, or the Examiner" in prompt
    assert "Every quoted example or evidence phrase in your feedback must appear in Candidate D turns only" in prompt
    assert "Candidate D turns only:" in prompt


def test_low_participation_feedback_cap_prevents_high_scores_for_testing_only() -> None:
    history = [
        {"speaker": "candidate_d", "content": "Testing."},
        {"speaker": "candidate_d", "content": "This is a software testing."},
        {
            "speaker": "candidate_a",
            "content": "The main driver is shortage of space and the cultural gap is a major hurdle.",
        },
    ]
    result = {
        "communication": {"score": 5, "max_score": 7, "comment": "Strong agenda control."},
        "language": {"score": 6, "max_score": 7, "comment": "Good range of vocabulary."},
        "ideas_organisation": {"score": 5, "max_score": 7, "comment": "Relevant ideas."},
        "strengths": ["Initiated discussion."],
        "improvements": [],
        "overall_comment": "Strong performance.",
    }

    capped = _apply_low_participation_feedback_cap(result, history)

    assert capped["communication"]["score"] <= 1
    assert capped["language"]["score"] <= 1
    assert capped["ideas_organisation"]["score"] <= 1
    assert "Too little relevant Candidate D speech" in capped["overall_comment"]
