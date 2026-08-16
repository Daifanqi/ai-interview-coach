"""
Unit tests for backend/report/highlight_picker.py -- exercised entirely
through mocking (unittest.mock.patch), same pattern as
tests/test_session_adapter_rag.py's retrieval-failure tests, so these never
make a real network call regardless of whether GROQ_API_KEY happens to be
configured in the local environment. scripts/smoke_test_week13.py is where
this module's real Groq call path gets exercised end to end.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.report import highlight_picker
from models.session_schema import DimensionScoreDetail, InterviewSession, TopicScoreDetail


def _make_detail(question_id: str, overall_score: float) -> TopicScoreDetail:
    dim = DimensionScoreDetail(score=overall_score, explanation="占位说明")
    return TopicScoreDetail(
        question_id=question_id,
        question_text=f"题目 {question_id}",
        structure_completeness=dim,
        keyword_coverage=dim,
        logical_coherence=dim,
        specificity=dim,
        overall_score=overall_score,
    )


def _make_session() -> InterviewSession:
    return InterviewSession(user_id="test-user")


def test_pick_highlight_returns_none_for_empty_scores():
    session = _make_session()
    assert highlight_picker.pick_highlight(session, {}, "zh") == (None, None)


def test_pick_highlight_falls_back_to_highest_score_without_client():
    session = _make_session()
    detailed_scores = {
        "turn-a": _make_detail("q_a", 6.0),
        "turn-b": _make_detail("q_b", 8.5),
    }
    with patch.object(highlight_picker, "_get_highlight_client", return_value=None):
        turn_id, reason = highlight_picker.pick_highlight(session, detailed_scores, "zh")
    assert turn_id == "turn-b"
    assert reason


def test_pick_highlight_uses_llm_response_when_valid():
    session = _make_session()
    detailed_scores = {
        "turn-a": _make_detail("q_a", 6.0),
        "turn-b": _make_detail("q_b", 8.5),
    }
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"turn_id":"turn-a","reason":"这一轮回答最能体现候选人的思考过程"}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(highlight_picker, "_get_highlight_client", return_value=mock_client):
        turn_id, reason = highlight_picker.pick_highlight(session, detailed_scores, "zh")
    assert turn_id == "turn-a"
    assert "思考过程" in reason


def test_pick_highlight_falls_back_when_llm_returns_unknown_turn_id():
    session = _make_session()
    detailed_scores = {
        "turn-a": _make_detail("q_a", 6.0),
        "turn-b": _make_detail("q_b", 8.5),
    }
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"turn_id":"turn-does-not-exist","reason":"..."}'))]
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(highlight_picker, "_get_highlight_client", return_value=mock_client):
        turn_id, reason = highlight_picker.pick_highlight(session, detailed_scores, "zh")
    assert turn_id == "turn-b"  # heuristic fallback: highest overall_score
    assert reason


def test_pick_highlight_salvages_turn_id_via_regex_on_malformed_json():
    session = _make_session()
    detailed_scores = {
        "turn-a": _make_detail("q_a", 6.0),
        "turn-b": _make_detail("q_b", 8.5),
    }
    mock_client = MagicMock()
    mock_response = MagicMock()
    # Deliberately malformed JSON (trailing garbage) that strict json.loads will reject,
    # but the "turn_id" field is still regex-extractable.
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"turn_id":"turn-a","reason":"不错的回答"} extra tokens'))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(highlight_picker, "_get_highlight_client", return_value=mock_client):
        turn_id, reason = highlight_picker.pick_highlight(session, detailed_scores, "zh")
    assert turn_id == "turn-a"
    assert reason


def test_pick_highlight_falls_back_on_call_exception():
    session = _make_session()
    detailed_scores = {
        "turn-a": _make_detail("q_a", 6.0),
        "turn-b": _make_detail("q_b", 8.5),
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = TimeoutError("simulated timeout")

    with patch.object(highlight_picker, "_get_highlight_client", return_value=mock_client):
        turn_id, reason = highlight_picker.pick_highlight(session, detailed_scores, "zh")
    assert turn_id == "turn-b"
    assert reason
