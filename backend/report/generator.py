"""
Week 13 review-report backend (docs/decision_log.md decision #39, "复盘报告后端").

generate_review_report() assembles a finished InterviewSession's per-topic
scores, sentence-level highlights, an AI-picked "highlight moment", a
template voice summary, aggregated wording-correction suggestions, and the
user's cross-session score trend into one ReviewReport.

Deliberately backend-and-tests-only this week (decision #42): there is no
frontend page reading this yet, and session_adapter.end_interview() does not
call this yet either -- wiring it into the live end-of-interview flow is
deferred to week 15's report page, so a bug here cannot affect the running
interview flow this week.

Scope choices made this week (decision #42):
- Only main-topic QAItems (question_source_id is not None, see
  session_adapter.py's week-12 RAG wiring) get scored. Follow-ups don't
  carry a question_source_id -- they're generated on the fly by the
  dialogue engine, not drawn from the question bank -- so there is no
  Question object to score them against with score_answer_report().
- voice_summary and text_correction_suggestions are template/aggregation-
  based here, not new LLM calls. decision #41 found this project's Groq TPM
  quota already saturates during ordinary interview flow; report generation
  isn't on the interview's latency-sensitive path, but the token volume a
  whole-transcript prose-generation call would add is still real, shared
  quota this project doesn't have to spend until there's a concrete need
  for prose the templates below can't produce.
- highlight_turn_id/highlight_reason IS a real LLM call (see
  backend/report/highlight_picker.py), because "which moment stood out" is
  exactly the deliberately subjective judgment call decision #9 asks for --
  a template or rule can't honestly produce that, only pick a proxy for it.
"""
from __future__ import annotations

import logging
from typing import Optional

from backend.report.highlight_picker import pick_highlight
from backend.scoring.baseline import score_answer_report
from backend.scoring.report import DimensionScore as BaselineDimensionScore
from backend.storage.db import list_sessions_by_user
from models.question_schema import get_question_by_id
from models.session_schema import (
    DimensionHighlight,
    DimensionScoreDetail,
    InterviewSession,
    QAItem,
    ReviewReport,
    ScoreDimensions,
    TopicScoreDetail,
    TrendPoint,
)

logger = logging.getLogger(__name__)

_NO_VOICE_DATA_SUMMARY: dict[str, str] = {
    "zh": "本次面试未采集到语音数据（纯文字作答，或语音分析未成功），本报告不包含语音表现分析。",
    "en": (
        "No voice data was captured for this session (text-only answers, or voice analysis "
        "did not succeed) -- this report has no voice-performance analysis."
    ),
}

_MAX_TEXT_CORRECTION_SUGGESTIONS = 5


# ---------------------------------------------------------------------------
# Per-topic scoring
# ---------------------------------------------------------------------------


def _convert_dimension_score(score: BaselineDimensionScore) -> DimensionScoreDetail:
    """backend/scoring/report.py's DimensionScore -> models/session_schema.py's persisted twin
    DimensionScoreDetail (see that module's docstring for why this conversion has to be explicit
    rather than a shared type -- same pattern as session_adapter.py's AudioFeatures conversion)."""
    return DimensionScoreDetail(
        score=score.score,
        explanation=score.explanation,
        highlights=[
            DimensionHighlight(
                sentence_index=h.sentence_index,
                sentence_text=h.sentence_text,
                polarity=h.polarity,
                reason=h.reason,
            )
            for h in score.highlights
        ],
    )


def _score_topic(item: QAItem) -> Optional[TopicScoreDetail]:
    """
    Score one main-topic QAItem, or None if it can't be scored -- either
    it's a follow-up (question_source_id is None, see module docstring), or
    its question_source_id no longer resolves in the question bank (a live
    session is not proof the bank hasn't changed since the session ran; see
    get_question_by_id()'s own docstring). Callers must treat None as
    "skip this turn", not an error.
    """
    if not item.question_source_id:
        return None
    question = get_question_by_id(item.question_source_id)
    if question is None:
        logger.warning(
            "question_source_id %r (turn %r) not found in the question bank, skipping scoring for this turn",
            item.question_source_id,
            item.turn_id,
        )
        return None

    report = score_answer_report(item.answer_text, question)
    return TopicScoreDetail(
        question_id=question.question_id,
        question_text=item.question_text or question.question_text,
        structure_completeness=_convert_dimension_score(report.structure_completeness),
        keyword_coverage=_convert_dimension_score(report.keyword_coverage),
        logical_coherence=_convert_dimension_score(report.logical_coherence),
        specificity=_convert_dimension_score(report.specificity),
        overall_score=report.overall_score,
    )


# ---------------------------------------------------------------------------
# Voice summary (template, not an LLM call -- see module docstring)
# ---------------------------------------------------------------------------


def _build_voice_summary(session: InterviewSession, language: str) -> str:
    """Template voice-performance summary aggregated across every turn that has AudioFeatures."""
    turns_with_audio = [item for item in session.qa_items if item.audio_features is not None]
    if not turns_with_audio:
        return _NO_VOICE_DATA_SUMMARY.get(language, _NO_VOICE_DATA_SUMMARY["zh"])

    total_fillers = sum(
        item.audio_features.fillers.strong_count + item.audio_features.fillers.weak_count
        for item in turns_with_audio
    )
    total_pauses = sum(item.audio_features.pauses.count for item in turns_with_audio)
    avg_longest_pause = sum(item.audio_features.pauses.longest_seconds for item in turns_with_audio) / len(
        turns_with_audio
    )

    if language == "en":
        return (
            f"Across {len(turns_with_audio)} answered turn(s) with voice data: "
            f"{total_fillers} filler word(s) in total, {total_pauses} pause(s) in total "
            f"(the longest pause averaged {avg_longest_pause:.1f}s per turn)."
        )
    return (
        f"共 {len(turns_with_audio)} 轮作答有语音数据：累计填充词 {total_fillers} 次，"
        f"累计停顿 {total_pauses} 次（平均每轮最长停顿 {avg_longest_pause:.1f} 秒）。"
    )


# ---------------------------------------------------------------------------
# Wording-correction suggestions (aggregation of existing LLM output, not a
# new LLM call -- see module docstring)
# ---------------------------------------------------------------------------


def _build_text_correction_suggestions(session: InterviewSession) -> list[str]:
    """
    Deduplicated, order-preserving aggregation of every QAItem's
    expression_suggestions across the session, capped at
    _MAX_TEXT_CORRECTION_SUGGESTIONS. These are week 10's per-round
    realtime_feedback.py suggestions -- already real LLM output generated
    live during the interview -- so this function only collects and dedupes
    what already exists; it makes no new LLM call.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for item in session.qa_items:
        for suggestion in item.expression_suggestions or []:
            if suggestion not in seen:
                seen.add(suggestion)
                ordered.append(suggestion)

    if len(ordered) > _MAX_TEXT_CORRECTION_SUGGESTIONS:
        logger.info(
            "Truncating %d text_correction_suggestions to %d for the report", len(ordered), _MAX_TEXT_CORRECTION_SUGGESTIONS
        )
    return ordered[:_MAX_TEXT_CORRECTION_SUGGESTIONS]


# ---------------------------------------------------------------------------
# Cross-session score trend (decision #10)
# ---------------------------------------------------------------------------


def _average_dimensions(report: ReviewReport) -> ScoreDimensions:
    """Average a past session's per_answer_scores across its topics, for one TrendPoint.
    Zeroed out (rather than raising) on a report with no scored topics -- an edge case that
    shouldn't happen for a report that made it into history_trend, but shouldn't crash if it does."""
    scores = list(report.per_answer_scores.values())
    if not scores:
        return ScoreDimensions(structure_completeness=0.0, keyword_coverage=0.0, logical_coherence=0.0, specificity=0.0)
    n = len(scores)
    return ScoreDimensions(
        structure_completeness=sum(s.structure_completeness for s in scores) / n,
        keyword_coverage=sum(s.keyword_coverage for s in scores) / n,
        logical_coherence=sum(s.logical_coherence for s in scores) / n,
        specificity=sum(s.specificity for s in scores) / n,
    )


def _build_history_trend(session: InterviewSession) -> list[TrendPoint]:
    """
    This user's score trend from their OTHER past sessions (decision #10),
    chronological oldest-first (list_sessions_by_user()'s own ordering),
    skipping any past session that has no report yet -- see that function's
    docstring for why it still returns those rows rather than filtering
    them itself. Naturally empty for a first-ever session (empty
    list_sessions_by_user result) or when GROQ/RAG-backed scoring never ran
    on any past session (every past .report is None) -- the frontend's
    industry-average fallback for an empty history_trend (decision #10) is
    explicitly out of scope for this week's backend-only work.
    """
    past_sessions = list_sessions_by_user(session.user_id, exclude_session_id=session.session_id)
    trend: list[TrendPoint] = []
    for past in past_sessions:
        if past.report is None:
            continue
        trend.append(
            TrendPoint(
                session_id=past.session_id,
                session_date=past.ended_at or past.created_at,
                overall_score=past.report.overall_score,
                dimension_scores=_average_dimensions(past.report),
            )
        )
    return trend


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_review_report(session: InterviewSession) -> ReviewReport:
    """
    Build a finished ReviewReport for `session` (see module docstring for
    this week's scope, and note this is NOT wired into
    session_adapter.end_interview() yet).
    """
    language = session.config.language if session.config else "zh"

    detailed_scores: dict[str, TopicScoreDetail] = {}
    per_answer_scores: dict[str, ScoreDimensions] = {}
    for item in session.qa_items:
        detail = _score_topic(item)
        if detail is None:
            continue
        detailed_scores[item.turn_id] = detail
        per_answer_scores[item.turn_id] = ScoreDimensions(
            structure_completeness=detail.structure_completeness.score,
            keyword_coverage=detail.keyword_coverage.score,
            logical_coherence=detail.logical_coherence.score,
            specificity=detail.specificity.score,
        )

    overall_score = (
        round(sum(d.overall_score for d in detailed_scores.values()) / len(detailed_scores), 2)
        if detailed_scores
        else 0.0
    )

    highlight_turn_id, highlight_reason = pick_highlight(session, detailed_scores, language)

    return ReviewReport(
        per_answer_scores=per_answer_scores,
        overall_score=overall_score,
        voice_summary=_build_voice_summary(session, language),
        text_correction_suggestions=_build_text_correction_suggestions(session),
        highlight_turn_id=highlight_turn_id,
        highlight_reason=highlight_reason,
        history_trend=_build_history_trend(session),
        detailed_scores=detailed_scores,
    )
