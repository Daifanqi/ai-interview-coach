"""
Unit tests for session_adapter.end_interview_async() -- the non-blocking
twin of end_interview() added for the post-roadmap "报告生成异步化"
backlog item (decision #47).

Same mocking pattern as tests/test_session_adapter_report_wiring.py
(generate_review_report()/save_session() mocked out, since a real call
needs the embedding model, chromadb, and a live Groq call) -- the only new
behavior under test here is the background-thread handoff itself: that
ended_at is set synchronously (before the worker even runs), that the
worker eventually attaches the report and saves, that a failure inside the
worker still degrades gracefully (same promise as decision #44's sync
version) rather than leaving the session unsaved, and that done_event
starts unset so a caller polling it right after end_interview_async()
returns doesn't get a false "already done".
"""
from __future__ import annotations

import threading
from datetime import datetime
from unittest.mock import patch

from backend.conversation import session_adapter
from models.session_schema import InterviewSession, ReviewReport

# Generous ceiling for waiting on a mocked (near-instant) worker thread --
# a real hang in the worker fails the test with a clear assertion instead
# of blocking the test run indefinitely.
_JOIN_TIMEOUT_SECONDS = 5.0


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


def test_end_interview_async_sets_ended_at_synchronously():
    """ended_at must already be set by the time end_interview_async() returns, on the calling thread --
    callers (frontend/app.py) rely on this to switch to the "interview ended" page immediately, without
    waiting for the background report-generation worker to even start."""
    session = _make_session()
    assert session.ended_at is None
    with patch("backend.conversation.session_adapter.generate_review_report", return_value=_make_report()), patch(
        "backend.conversation.session_adapter.save_session"
    ):
        handle = session_adapter.end_interview_async(session)
        assert isinstance(session.ended_at, datetime)
    assert handle.done_event.wait(timeout=_JOIN_TIMEOUT_SECONDS), "worker thread did not finish in time"


def test_end_interview_async_attaches_report_on_success():
    session = _make_session()
    report = _make_report()
    with patch("backend.conversation.session_adapter.generate_review_report", return_value=report), patch(
        "backend.conversation.session_adapter.save_session"
    ):
        handle = session_adapter.end_interview_async(session)
        assert handle.done_event.wait(timeout=_JOIN_TIMEOUT_SECONDS), "worker thread did not finish in time"
    assert session.report is report


def test_end_interview_async_calls_save_session_with_the_session():
    session = _make_session()
    with patch("backend.conversation.session_adapter.generate_review_report", return_value=_make_report()), patch(
        "backend.conversation.session_adapter.save_session"
    ) as mock_save:
        handle = session_adapter.end_interview_async(session)
        assert handle.done_event.wait(timeout=_JOIN_TIMEOUT_SECONDS), "worker thread did not finish in time"
    mock_save.assert_called_once_with(session)


def test_end_interview_async_degrades_to_no_report_on_generation_failure():
    """Same degrade-gracefully promise as the sync end_interview() (decision #44), carried over to the
    async path (decision #47): a scoring/highlight-pick exception on the background thread must not
    leave the session unsaved -- save_session() must still run, and report simply stays None."""
    session = _make_session()
    with patch(
        "backend.conversation.session_adapter.generate_review_report", side_effect=RuntimeError("boom")
    ), patch("backend.conversation.session_adapter.save_session") as mock_save:
        handle = session_adapter.end_interview_async(session)
        assert handle.done_event.wait(timeout=_JOIN_TIMEOUT_SECONDS), "worker thread did not finish in time"
    assert session.report is None
    assert isinstance(session.ended_at, datetime)
    mock_save.assert_called_once_with(session)


def test_end_interview_async_done_event_starts_unset():
    """Sanity check on the handle contract itself (see ReportGenerationHandle's docstring): a caller
    checking done_event immediately after end_interview_async() returns, before the worker has had a
    chance to run, must see 'still generating' -- not a false-positive 'done'. Uses a
    generate_review_report() that blocks on a test-controlled Event so the worker is deterministically
    caught mid-flight; real thread scheduling is otherwise too fast to reliably observe this window."""
    release_worker = threading.Event()

    def _blocking_generate(session):
        release_worker.wait(timeout=_JOIN_TIMEOUT_SECONDS)
        return _make_report()

    session = _make_session()
    with patch(
        "backend.conversation.session_adapter.generate_review_report", side_effect=_blocking_generate
    ), patch("backend.conversation.session_adapter.save_session"):
        handle = session_adapter.end_interview_async(session)
        assert not handle.done_event.is_set()
        release_worker.set()
        assert handle.done_event.wait(timeout=_JOIN_TIMEOUT_SECONDS), "worker thread did not finish in time"
