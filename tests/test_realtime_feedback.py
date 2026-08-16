"""
Unit tests for backend/conversation/realtime_feedback.py (week 16, decision
#45's test-coverage debt item -- decision #39 flagged this week-10 module as
having zero test coverage, same as scoring_judge.py's sibling module
already gets exercised indirectly via the conversation-engine tests).

_call_groq_feedback() (the actual network call) is mocked out the same way
tests/test_session_adapter_report_wiring.py mocks generate_review_report()
-- a real call needs a live Groq API key and network access, covered
instead by scripts/test_conversation_live.py and the manual walkthroughs
this project's decision log entries describe. Everything else here
(_truncate_answer, _parse_json_response, and generate_feedback()'s
success/failure branching) is pure logic and is exercised directly.
"""
from __future__ import annotations

from unittest.mock import patch

from backend.conversation.realtime_feedback import (
    FeedbackResult,
    _HEAD_CHARS,
    _parse_json_response,
    _TAIL_CHARS,
    _TRUNCATION_THRESHOLD_CHARS,
    _truncate_answer,
    generate_feedback,
)

# ---------------------------------------------------------------------------
# _truncate_answer
# ---------------------------------------------------------------------------


def test_truncate_answer_leaves_short_answer_unchanged():
    short = "这是一段简短的回答。"
    assert _truncate_answer(short) == short


def test_truncate_answer_truncates_long_answer_with_head_and_tail():
    long_answer = "字" * (_TRUNCATION_THRESHOLD_CHARS + 100)
    result = _truncate_answer(long_answer)
    assert result != long_answer
    assert result.startswith(long_answer[:_HEAD_CHARS])
    assert result.endswith(long_answer[-_TAIL_CHARS:])
    assert "…" in result


def test_truncate_answer_boundary_length_unchanged():
    # Exactly at the threshold -- the "<=" check means this must NOT truncate.
    boundary = "字" * _TRUNCATION_THRESHOLD_CHARS
    assert _truncate_answer(boundary) == boundary


# ---------------------------------------------------------------------------
# _parse_json_response
# ---------------------------------------------------------------------------


def test_parse_json_response_valid_shape():
    content = '{"content_feedback": "回答内容不够具体。", "expression_suggestions": ["用词更自然一些", "避免口语化表达"]}'
    result = _parse_json_response(content)
    assert result is not None
    assert result.content_feedback == "回答内容不够具体。"
    assert result.expression_suggestions == ["用词更自然一些", "避免口语化表达"]


def test_parse_json_response_invalid_json_returns_none():
    assert _parse_json_response("not json at all") is None


def test_parse_json_response_non_dict_json_returns_none():
    assert _parse_json_response("[1, 2, 3]") is None


def test_parse_json_response_missing_content_feedback_returns_none():
    content = '{"expression_suggestions": ["ok"]}'
    assert _parse_json_response(content) is None


def test_parse_json_response_blank_content_feedback_returns_none():
    content = '{"content_feedback": "   ", "expression_suggestions": ["ok"]}'
    assert _parse_json_response(content) is None


def test_parse_json_response_empty_suggestions_list_returns_none():
    content = '{"content_feedback": "还不错", "expression_suggestions": []}'
    assert _parse_json_response(content) is None


def test_parse_json_response_suggestions_not_a_list_returns_none():
    content = '{"content_feedback": "还不错", "expression_suggestions": "用词更自然"}'
    assert _parse_json_response(content) is None


def test_parse_json_response_caps_suggestions_at_three():
    content = (
        '{"content_feedback": "还不错", '
        '"expression_suggestions": ["建议一", "建议二", "建议三", "建议四", "建议五"]}'
    )
    result = _parse_json_response(content)
    assert result is not None
    assert len(result.expression_suggestions) == 3
    assert result.expression_suggestions == ["建议一", "建议二", "建议三"]


def test_parse_json_response_filters_out_blank_suggestion_entries():
    content = '{"content_feedback": "还不错", "expression_suggestions": ["有效建议", "   ", ""]}'
    result = _parse_json_response(content)
    assert result is not None
    assert result.expression_suggestions == ["有效建议"]


# ---------------------------------------------------------------------------
# generate_feedback() -- success/failure branching, Groq call mocked out
# ---------------------------------------------------------------------------


def test_generate_feedback_returns_parsed_result_on_success():
    raw = '{"content_feedback": "内容点评", "expression_suggestions": ["表达建议一", "表达建议二"]}'
    with patch("backend.conversation.realtime_feedback._call_groq_feedback", return_value=raw):
        result = generate_feedback("为什么选择Kafka？", "因为它吞吐量高。", "zh")
    assert result == FeedbackResult(content_feedback="内容点评", expression_suggestions=["表达建议一", "表达建议二"])


def test_generate_feedback_degrades_to_none_fields_when_call_fails():
    """Module docstring's core promise: any failure (timeout/missing key/malformed JSON/empty
    completion) must degrade to both fields None, never raise and never partially fill."""
    with patch("backend.conversation.realtime_feedback._call_groq_feedback", return_value=None):
        result = generate_feedback("为什么选择Kafka？", "因为它吞吐量高。", "zh")
    assert result == FeedbackResult(content_feedback=None, expression_suggestions=None)


def test_generate_feedback_degrades_to_none_fields_on_unparseable_response():
    with patch("backend.conversation.realtime_feedback._call_groq_feedback", return_value="not valid json"):
        result = generate_feedback("为什么选择Kafka？", "因为它吞吐量高。", "zh")
    assert result == FeedbackResult(content_feedback=None, expression_suggestions=None)
