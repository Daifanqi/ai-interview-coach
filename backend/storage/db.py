"""
AI Interview System - Storage Module: SQLite persistence for InterviewSession

Design: InterviewSession is a deep dataclass tree (SessionConfig / QAItem /
AudioFeatures / ReviewReport / ScoreDimensions / TrendPoint). Rather than
mapping every nested dataclass to its own SQL table -- premature while
nothing outside this module needs to query into the tree by field -- each
full session is serialized to a single JSON blob per row. session_id,
user_id and created_at are pulled out into their own columns purely so
simple lookups (list a user's past sessions, sort by date) don't require
deserializing every blob first.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from models.session_schema import (
    AudioFeatures,
    DimensionHighlight,
    DimensionScoreDetail,
    ExperienceLevel,
    FillerFeatures,
    InterviewSession,
    InterviewStage,
    PauseFeatures,
    QAItem,
    ReviewReport,
    ScoreDimensions,
    SessionConfig,
    SpeechRateFeatures,
    TopicScoreDetail,
    TrendPoint,
    TurnAction,
    VolumeFeatures,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sessions.db"


def _json_default(obj):
    """json.dumps default= hook: teach it about the two non-primitive types InterviewSession uses."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    return conn


def save_session(session: InterviewSession, db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Insert a new session, or overwrite the existing row if session_id already exists."""
    payload = json.dumps(asdict(session), default=_json_default, ensure_ascii=False)
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO sessions (session_id, user_id, created_at, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                user_id = excluded.user_id,
                created_at = excluded.created_at,
                data = excluded.data
            """,
            (session.session_id, session.user_id, session.created_at.isoformat(), payload),
        )
        conn.commit()
    finally:
        conn.close()


def load_session(session_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[InterviewSession]:
    """Load one InterviewSession by id. Returns None if no row matches."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None
    return _deserialize_session(json.loads(row[0]))


def list_sessions_by_user(
    user_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    *,
    exclude_session_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[InterviewSession]:
    """
    Load a user's past sessions, most-recent-first as they come out of SQL,
    reordered to chronological (oldest-first) before returning -- the
    natural order for backend/report/generator.py's history_trend list
    (decision #10/#39, week 13).

    `exclude_session_id` lets a caller building a report for session X ask
    for "this user's OTHER past sessions" in one query, without first
    loading every session and filtering in Python. `limit` is applied in
    SQL (most-recent N), mirroring the user_id/created_at columns' own
    stated purpose (see this module's docstring): cheap lookups without
    deserializing every row.

    Sessions with no report at all (e.g. abandoned mid-interview, or ended
    before week 13's report generation ever ran) are still returned here --
    filtering to "only sessions with a finished report" is the caller's
    job (see generator.py's history-trend builder), since not every
    list_sessions_by_user caller necessarily wants that filter.

    Note (decision #39/#43): week 14 landed the login system (see
    backend/storage/user_db.py, frontend/app.py's auth gate) and every new
    session now carries a real user_id. Any session saved *before* week 14
    still has user_id="" persisted from back then -- calling this with
    user_id="" still buckets together every one of those old rows, not one
    person's history, since there was never a real "" user. That's expected
    for pre-week-14 data, not a bug in this function.
    """
    query = "SELECT data FROM sessions WHERE user_id = ?"
    params: list = [user_id]
    if exclude_session_id is not None:
        query += " AND session_id != ?"
        params.append(exclude_session_id)
    query += " ORDER BY created_at DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    conn = _get_connection(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    sessions = [_deserialize_session(json.loads(row[0])) for row in rows]
    sessions.reverse()  # DESC (most-recent-first) -> chronological (oldest-first)
    return sessions


# ---------------------------------------------------------------------------
# Deserialization helpers: JSON dict -> dataclass tree, mirroring
# models/session_schema.py field-for-field. Every dataclass gets its own
# helper (rather than one recursive walker) because each one needs
# type-specific handling -- Enum(...) for enum fields, fromisoformat for
# datetimes -- that a generic walker would have to special-case anyway.
# ---------------------------------------------------------------------------


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _deserialize_audio_features(data: Optional[dict]) -> Optional[AudioFeatures]:
    """
    Nested dataclass tree, mirroring AudioFeatures' four sub-structures
    (decision #39/week 11) -- can't use a flat AudioFeatures(**data) here
    the way the old 5-flat-field version could, since speech_rate/pauses/
    fillers/volume are themselves dataclasses, not JSON-native values.
    """
    if data is None:
        return None
    speech_rate_data = data.get("speech_rate")
    volume_data = data.get("volume")
    return AudioFeatures(
        speech_rate=SpeechRateFeatures(**speech_rate_data) if speech_rate_data is not None else None,
        pauses=PauseFeatures(**data["pauses"]),
        fillers=FillerFeatures(**data["fillers"]),
        volume=VolumeFeatures(**volume_data) if volume_data is not None else None,
    )


def _deserialize_qa_item(data: dict) -> QAItem:
    return QAItem(
        turn_id=data["turn_id"],
        parent_turn_id=data.get("parent_turn_id"),
        question_text=data.get("question_text", ""),
        question_source_id=data.get("question_source_id"),
        answer_text=data.get("answer_text", ""),
        realtime_feedback_score=data.get("realtime_feedback_score"),
        content_feedback=data.get("content_feedback"),
        expression_suggestions=data.get("expression_suggestions"),
        action_taken=TurnAction(data["action_taken"]) if data.get("action_taken") else None,
        audio_features=_deserialize_audio_features(data.get("audio_features")),
        timestamp=_parse_datetime(data.get("timestamp")),
    )


def _deserialize_dimension_highlight(data: dict) -> DimensionHighlight:
    return DimensionHighlight(
        sentence_index=data["sentence_index"],
        sentence_text=data["sentence_text"],
        polarity=data["polarity"],
        reason=data["reason"],
    )


def _deserialize_dimension_score_detail(data: dict) -> DimensionScoreDetail:
    return DimensionScoreDetail(
        score=data["score"],
        explanation=data["explanation"],
        highlights=[_deserialize_dimension_highlight(h) for h in data.get("highlights", [])],
    )


def _deserialize_topic_score_detail(data: dict) -> TopicScoreDetail:
    return TopicScoreDetail(
        question_id=data["question_id"],
        question_text=data["question_text"],
        structure_completeness=_deserialize_dimension_score_detail(data["structure_completeness"]),
        keyword_coverage=_deserialize_dimension_score_detail(data["keyword_coverage"]),
        logical_coherence=_deserialize_dimension_score_detail(data["logical_coherence"]),
        specificity=_deserialize_dimension_score_detail(data["specificity"]),
        overall_score=data["overall_score"],
    )


def _deserialize_review_report(data: Optional[dict]) -> Optional[ReviewReport]:
    if data is None:
        return None
    return ReviewReport(
        per_answer_scores={
            turn_id: ScoreDimensions(**scores)
            for turn_id, scores in data.get("per_answer_scores", {}).items()
        },
        overall_score=data["overall_score"],
        voice_summary=data["voice_summary"],
        text_correction_suggestions=data.get("text_correction_suggestions", []),
        highlight_turn_id=data.get("highlight_turn_id"),
        highlight_reason=data.get("highlight_reason"),
        history_trend=[
            TrendPoint(
                session_id=tp["session_id"],
                session_date=_parse_datetime(tp["session_date"]),
                overall_score=tp["overall_score"],
                dimension_scores=ScoreDimensions(**tp["dimension_scores"]),
            )
            for tp in data.get("history_trend", [])
        ],
        detailed_scores={
            turn_id: _deserialize_topic_score_detail(detail)
            for turn_id, detail in data.get("detailed_scores", {}).items()
        },
        generated_at=_parse_datetime(data.get("generated_at")),
    )


def _deserialize_session_config(data: Optional[dict]) -> Optional[SessionConfig]:
    if data is None:
        return None
    return SessionConfig(
        job_type=data["job_type"],
        experience_level=ExperienceLevel(data["experience_level"]),
        interview_stage=InterviewStage(data["interview_stage"]),
        target_company=data.get("target_company"),
        difficulty=data["difficulty"],
        interviewer_persona=data["interviewer_persona"],
        language=data.get("language", "zh"),
        created_at=_parse_datetime(data.get("created_at")),
    )


def _deserialize_session(data: dict) -> InterviewSession:
    return InterviewSession(
        session_id=data["session_id"],
        user_id=data.get("user_id", ""),
        config=_deserialize_session_config(data.get("config")),
        qa_items=[_deserialize_qa_item(item) for item in data.get("qa_items", [])],
        report=_deserialize_review_report(data.get("report")),
        created_at=_parse_datetime(data.get("created_at")),
        ended_at=_parse_datetime(data.get("ended_at")),
    )
