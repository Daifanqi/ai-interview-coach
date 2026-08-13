"""
AI Mock Interview System -- Core Data Structure Definitions

Design notes:
- InterviewSession is the top-level container that aggregates sub-structures
  such as SessionConfig / QAItem / ReviewReport, instead of flattening every
  field into one giant class. This lets each module (triage / dialogue engine
  / scoring / review) read and write only the parts it cares about.
- Follow-ups are not modeled as nested structures: every follow-up is its own
  independent QAItem, linked back to the turn it follows via parent_turn_id.
  So "main question -> follow-up 1 -> follow-up 2" is a flat chain rather than
  a tree, which keeps serialization and traversal simple.
- AudioFeatures as a whole is Optional: voice analysis can fail, or the user
  may choose a text-only interview from the start. Neither case should block
  QAItem construction -- the field is simply None.
- realtime_feedback_score (lightweight real-time scoring, drives follow-up
  decisions) and ScoreDimensions (full post-session scoring) are two
  intentionally separate scoring systems -- kept apart in both naming and
  structure so the "lightweight/live" and "final/authoritative" semantics
  never get mixed up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Optional
import uuid


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ExperienceLevel(str, Enum):
    """Candidate's experience level, used by the triage module to match difficulty and question bank"""

    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class InterviewStage(str, Enum):
    """Interview stage, influences interviewer persona and question style"""

    HR_SCREEN = "hr_screen"
    TECH_ROUND_1 = "tech_round_1"
    TECH_ROUND_2 = "tech_round_2"
    FINAL = "final"


class TurnAction(str, Enum):
    """The next action the dialogue engine takes after each turn, decided by the follow-up policy module"""

    FOLLOW_UP = "follow_up"  # ask a follow-up question
    NEXT_QUESTION = "next_question"  # move on to a new question
    SESSION_END = "session_end"  # end the current session


# ---------------------------------------------------------------------------
# Session config: output of the triage module, input to the dialogue engine / RAG retrieval
# ---------------------------------------------------------------------------


@dataclass
class SessionConfig:
    """Configuration for this interview session, generated once by the triage module at session start and immutable afterward"""

    job_type: str  # job type, e.g. "backend engineer"
    experience_level: ExperienceLevel
    interview_stage: InterviewStage
    target_company: Optional[str]  # target company, may be unknown
    difficulty: int  # difficulty level, scale defined by the triage module (e.g. 1-5)
    interviewer_persona: str  # interviewer persona description, drives the dialogue engine's tone/style
    language: Literal["zh", "en"] = "zh"  # UI + AI interviewer dialogue language (see decision 13 in docs/decision_log.md)
    created_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Audio features: output of the voice analysis module, optional as a whole
# ---------------------------------------------------------------------------


@dataclass
class AudioFeatures:
    """
    Voice features for a single answer turn.

    This field is Optional on QAItem as a whole -- voice analysis can fail
    (poor audio quality / recognition error), or the user may have chosen a
    text-only interview. In either case, the upstream review report
    generation module should detect the missing data and fall back to
    "no voice data captured this time" instead of the field being force-filled.
    """

    speech_rate_wpm: float  # speech rate, words per minute
    pause_count: int  # number of pauses
    pause_total_seconds: float  # total pause duration (seconds)
    filler_word_freq: dict[str, int]  # filler word frequency, e.g. {"um": 5, "like": 3}
    volume_variance: float  # volume variance, used to gauge tone fluctuation / confidence


# ---------------------------------------------------------------------------
# QA turn: the core record unit of the dialogue engine
# ---------------------------------------------------------------------------


@dataclass
class QAItem:
    """
    A single question-answer turn.

    Main questions and follow-ups are peer-level QAItems in the data model,
    not nested: a follow-up points back to the turn_id of the turn it follows
    via parent_turn_id, forming a traceable chain rather than a tree. This way
    both rendering the conversation and counting "how many follow-ups" only
    require a linear scan over qa_items.
    """

    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_turn_id: Optional[str] = None  # non-null means this is a follow-up to another turn
    question_text: str = ""
    question_source_id: Optional[str] = None  # corresponding question ID in the RAG question bank; usually None for follow-ups (generated on the fly)
    answer_text: str = ""
    realtime_feedback_score: Optional[float] = None  # lightweight real-time score, only used to drive follow-up decisions, not part of the final report
    action_taken: Optional[TurnAction] = None  # action the dialogue engine took after this turn
    audio_features: Optional[AudioFeatures] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Score dimensions: full post-session scoring, a system fully independent of real-time scoring
# ---------------------------------------------------------------------------


@dataclass
class ScoreDimensions:
    """
    The four dimensions of full post-session scoring.

    Kept as a system fully independent of QAItem.realtime_feedback_score:
    this is the authoritative score produced by the post-session scoring
    pipeline (potentially involving a fine-tuned model), used for report
    generation and cross-session trend comparison. Real-time scoring is only
    a lightweight, in-the-moment signal for the follow-up decision and should
    never be reused or conflated with this.
    """

    structure_completeness: float  # structural completeness (e.g. adherence to the STAR method)
    keyword_coverage: float  # keyword coverage
    logical_coherence: float  # logical coherence
    specificity: float  # specificity / level of detail


# ---------------------------------------------------------------------------
# Trend point: the smallest unit queried across sessions by the progress tracking module
# ---------------------------------------------------------------------------


@dataclass
class TrendPoint:
    """A single data point on the trend chart, corresponding to one past session"""

    session_id: str
    session_date: datetime
    overall_score: float
    dimension_scores: ScoreDimensions


# ---------------------------------------------------------------------------
# Review report: final output of the review report generation module
# ---------------------------------------------------------------------------


@dataclass
class ReviewReport:
    """
    The review report for a single session.

    - per_answer_scores is keyed by turn_id, giving four-dimension scores per question.
    - voice_summary should hold the agreed fallback copy (e.g. "no voice data
      captured this time") when voice analysis fails or the interview was
      text-only, rather than being left empty or raising an error.
    - history_trend is only non-empty once the user has multiple past
      sessions; on a first-ever session it is an empty list, and the frontend
      falls back to an industry-average baseline when rendering the progress
      chart (see decision 10 in docs/decision_log.md).
    """

    per_answer_scores: dict[str, ScoreDimensions]  # key: QAItem.turn_id
    overall_score: float
    voice_summary: str
    text_correction_suggestions: list[str]
    highlight_turn_id: Optional[str]  # turn_id of the highlighted moment
    highlight_reason: Optional[str] = None  # AI-provided reason for the highlight (decision 9: subjective judgment + rationale)
    history_trend: list[TrendPoint] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Session container: aggregates all of the above sub-structures
# ---------------------------------------------------------------------------


@dataclass
class InterviewSession:
    """
    Top-level container for one complete interview session.

    Purely an aggregate -- it does not duplicate fields already carried by
    its sub-structures: session config lives under config, individual turns
    under qa_items, the report under report. This way each module only needs
    to depend on the sub-structure type it actually cares about, instead of
    taking a deep dependency on the full InterviewSession.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    config: Optional[SessionConfig] = None
    qa_items: list[QAItem] = field(default_factory=list)
    report: Optional[ReviewReport] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
