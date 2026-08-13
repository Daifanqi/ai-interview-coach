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
    ExperienceLevel,
    InterviewSession,
    InterviewStage,
    QAItem,
    ReviewReport,
    ScoreDimensions,
    SessionConfig,
    TrendPoint,
    TurnAction,
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
    if data is None:
        return None
    return AudioFeatures(**data)


def _deserialize_qa_item(data: dict) -> QAItem:
    return QAItem(
        turn_id=data["turn_id"],
        parent_turn_id=data.get("parent_turn_id"),
        question_text=data.get("question_text", ""),
        question_source_id=data.get("question_source_id"),
        answer_text=data.get("answer_text", ""),
        realtime_feedback_score=data.get("realtime_feedback_score"),
        action_taken=TurnAction(data["action_taken"]) if data.get("action_taken") else None,
        audio_features=_deserialize_audio_features(data.get("audio_features")),
        timestamp=_parse_datetime(data.get("timestamp")),
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
