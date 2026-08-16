"""
Unit tests for backend/report/generator.py -- week 13 review-report backend.

These use the real score_answer_report() (real embedding model, no mocking,
same as tests/test_baseline_scoring.py) against data/sample_questions.json,
and monkeypatch generator.get_question_by_id / generator.list_sessions_by_user
/ generator.pick_highlight so this file never depends on data/question_bank.json's
real ids, a real sessions.db, or a real Groq call -- pick_highlight() itself is
covered independently, with its own mocking, in tests/test_highlight_picker.py.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from backend.report import generator
from models.question_schema import load_questions_from_json
from models.session_schema import (
    ExperienceLevel,
    InterviewSession,
    InterviewStage,
    QAItem,
    SessionConfig,
)

SAMPLE_QUESTIONS_PATH = "data/sample_questions.json"


@pytest.fixture(scope="module")
def questions() -> dict:
    return {q.question_id: q for q in load_questions_from_json(SAMPLE_QUESTIONS_PATH)}


@pytest.fixture(autouse=True)
def _patch_question_lookup(monkeypatch, questions):
    """Every test in this file scores against data/sample_questions.json, not the real
    data/question_bank.json get_question_by_id() defaults to -- see module docstring."""
    monkeypatch.setattr(generator, "get_question_by_id", lambda qid: questions.get(qid))


def _make_session(qa_items: list[QAItem]) -> InterviewSession:
    return InterviewSession(
        user_id="test-user-week13",
        config=SessionConfig(
            job_type="backend engineer",
            experience_level=ExperienceLevel.MID,
            interview_stage=InterviewStage.TECH_ROUND_1,
            target_company=None,
            difficulty=3,
            interviewer_persona="technical",
            language="zh",
        ),
        qa_items=qa_items,
        created_at=datetime.utcnow(),
    )


def _stub_pick_highlight(session, detailed_scores, language):
    """Deterministic stand-in for the real (Groq-backed) pick_highlight -- see module docstring."""
    if not detailed_scores:
        return None, None
    return next(iter(detailed_scores)), "stub reason"


# ---------------------------------------------------------------------------
# _score_topic
# ---------------------------------------------------------------------------


def test_score_topic_returns_none_without_question_source_id():
    item = QAItem(question_text="追问", answer_text="因为当时时间紧张，我们优先保证了核心功能。", question_source_id=None)
    assert generator._score_topic(item) is None


def test_score_topic_returns_none_when_question_id_unknown(monkeypatch):
    monkeypatch.setattr(generator, "get_question_by_id", lambda qid: None)
    item = QAItem(question_text="主问题", answer_text="回答内容", question_source_id="does_not_exist")
    assert generator._score_topic(item) is None


def test_score_topic_scores_main_question(questions):
    item = QAItem(
        question_text=questions["behavioral_01"].question_text,
        answer_text="去年我带一个4人小组在4周内上线了一个优惠券模块，最终提前2天完成，核销率提升了18%。",
        question_source_id="behavioral_01",
    )
    detail = generator._score_topic(item)
    assert detail is not None
    assert detail.question_id == "behavioral_01"
    assert 0.0 <= detail.overall_score <= 10.0
    for dim in (detail.structure_completeness, detail.keyword_coverage, detail.logical_coherence, detail.specificity):
        assert isinstance(dim.highlights, list)


# ---------------------------------------------------------------------------
# generate_review_report
# ---------------------------------------------------------------------------


def test_generate_review_report_shape(monkeypatch, questions):
    monkeypatch.setattr(generator, "list_sessions_by_user", lambda *a, **k: [])
    monkeypatch.setattr(generator, "pick_highlight", _stub_pick_highlight)

    main_item = QAItem(
        question_text=questions["technical_01"].question_text,
        answer_text="用发号器生成自增ID再做Base62编码，读多写少的场景加一层Redis缓存，数据库分库分表。",
        question_source_id="technical_01",
    )
    follow_up_item = QAItem(
        question_text="能展开讲讲缓存怎么设计的吗？",
        answer_text="缓存用了LRU策略，设置了合理的过期时间。",
        question_source_id=None,
        parent_turn_id=main_item.turn_id,
    )
    session = _make_session([main_item, follow_up_item])

    report = generator.generate_review_report(session)

    assert set(report.per_answer_scores.keys()) == {main_item.turn_id}
    assert set(report.detailed_scores.keys()) == {main_item.turn_id}
    assert 0.0 <= report.overall_score <= 10.0
    assert report.highlight_turn_id == main_item.turn_id
    assert report.highlight_reason == "stub reason"
    assert report.history_trend == []
    assert isinstance(report.text_correction_suggestions, list)
    assert isinstance(report.voice_summary, str) and report.voice_summary


def test_generate_review_report_empty_session_has_no_highlight(monkeypatch):
    monkeypatch.setattr(generator, "list_sessions_by_user", lambda *a, **k: [])
    monkeypatch.setattr(generator, "pick_highlight", _stub_pick_highlight)

    session = _make_session([])
    report = generator.generate_review_report(session)

    assert report.detailed_scores == {}
    assert report.per_answer_scores == {}
    assert report.overall_score == 0.0
    assert report.highlight_turn_id is None
    assert report.highlight_reason is None


def test_generate_review_report_skips_unscoreable_turns_but_keeps_others(monkeypatch, questions):
    """A stale question_source_id (not in the bank) must not crash report generation --
    that turn is just dropped from detailed_scores/per_answer_scores (see _score_topic)."""
    monkeypatch.setattr(generator, "list_sessions_by_user", lambda *a, **k: [])
    monkeypatch.setattr(generator, "pick_highlight", _stub_pick_highlight)

    good_item = QAItem(
        question_text=questions["behavioral_01"].question_text,
        answer_text="去年我带一个4人小组在4周内上线了一个优惠券模块，最终提前2天完成，核销率提升了18%。",
        question_source_id="behavioral_01",
    )
    stale_item = QAItem(
        question_text="某个已经从题库中移除的题目",
        answer_text="随便写点什么",
        question_source_id="this_id_is_stale",
    )
    session = _make_session([good_item, stale_item])

    report = generator.generate_review_report(session)

    assert set(report.detailed_scores.keys()) == {good_item.turn_id}
    assert set(report.per_answer_scores.keys()) == {good_item.turn_id}


# ---------------------------------------------------------------------------
# _build_text_correction_suggestions
# ---------------------------------------------------------------------------


def test_text_correction_suggestions_dedupes_and_caps():
    items = [
        QAItem(answer_text="a", expression_suggestions=["用词A更自然", "用词B更专业"]),
        QAItem(answer_text="b", expression_suggestions=["用词A更自然", "用词C更精炼"]),
    ]
    session = _make_session(items)
    suggestions = generator._build_text_correction_suggestions(session)
    assert suggestions == ["用词A更自然", "用词B更专业", "用词C更精炼"]


def test_text_correction_suggestions_handles_no_suggestions():
    session = _make_session([QAItem(answer_text="a")])
    assert generator._build_text_correction_suggestions(session) == []


# ---------------------------------------------------------------------------
# _build_voice_summary
# ---------------------------------------------------------------------------


def test_voice_summary_falls_back_when_no_audio_data():
    session = _make_session([QAItem(answer_text="a")])
    summary = generator._build_voice_summary(session, "zh")
    assert "未采集到语音数据" in summary


def test_voice_summary_falls_back_in_english():
    session = _make_session([QAItem(answer_text="a")])
    summary = generator._build_voice_summary(session, "en")
    assert "No voice data" in summary
