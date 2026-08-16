"""
Unit tests for session_adapter.end_interview()'s week-15 report wiring
(decision #44) -- generate_review_report() is now called from here (see
module docstring's "Week 15" note), guarded by try/except so a scoring/
highlight-pick failure degrades to interview_session.report staying None
rather than blocking the interview from ending and saving.

generate_review_report() and save_session() are mocked out (same pattern as
tests/test_session_adapter_rag.py's retrieval-failure tests) since a real
call would need the embedding model, chromadb, and a live Groq call --
covered instead by scripts/smoke_test_week13.py and the manual walkthrough
this week's decision log entry describes.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from backend.conversation import session_adapter
from models.session_schema import InterviewSession, ReviewReport


def _make_session() -> InterviewSession:
    return InterviewSession(user_id="test-user")


def _make_report() -> ReviewReport:
    return ReviewReport(
        per_answer_scores={},
        overall_score=7.5,
        voice_summary="test voice summary",
        text_correction_suggestions=[],
        highlight_turn_id=None,
        highlight_reason=None,
    )


def test_end_interview_sets_ended_at():
    session = _make_session()
    assert session.ended_at is None
    with patch("backend.conversation.session_adapter.generate_review_report", return_value=_make_report()), patch(
        "backend.conversation.session_adapter.save_session"
    ):
        session_adapter.end_interview(session)
    assert isinstance(session.ended_at, datetime)


def test_end_interview_attaches_report_on_success():
    session = _make_session()
    report = _make_report()
    with patch("backend.conversation.session_adapter.generate_review_report", return_value=report), patch(
        "backend.conversation.session_adapter.save_session"
    ):
        session_adapter.end_interview(session)
    assert session.report is report


def test_end_interview_calls_save_session_with_the_session():
    session = _make_session()
    with patch("backend.conversation.session_adapter.generate_review_report", return_value=_make_report()), patch(
        "backend.conversation.session_adapter.save_session"
    ) as mock_save:
        session_adapter.end_interview(session)
    mock_save.assert_called_once_with(session)


def test_end_interview_degrades_to_no_report_on_generation_failure():
    """The core promise of decision #44's try/except: a scoring/highlight-pick
    exception must not prevent the interview from ending and saving."""
    session = _make_session()
    with patch(
        "backend.conversation.session_adapter.generate_review_report", side_effect=RuntimeError("boom")
    ), patch("backend.conversation.session_adapter.save_session") as mock_save:
        session_adapter.end_interview(session)
    assert session.report is None
    assert isinstance(session.ended_at, datetime)
    mock_save.assert_called_once_with(session)
