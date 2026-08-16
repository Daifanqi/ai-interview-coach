"""
Week 9 glue layer: wires backend/conversation/engine.py's turn-by-turn
dialogue state onto models/session_schema.py's persisted InterviewSession,
for the "triage -> interview -> end" flow in frontend/app.py.

engine.py deliberately has no concept of turn_id, QAItem, persistence, or
"how many topics before the interview ends" -- those are session-lifecycle
concerns that sit above one topic's follow-up chain, so they live here
instead of being added to engine.py or hand-rolled inside app.py.

Session lifecycle this module drives
-------------------------------------
start() resolves the triage-produced persona label into engine.Persona,
starts the EngineSession, and immediately runs the priming exchange itself
(engine.py's "candidate says 'sure, go ahead'" gap -- see engine.py's module
docstring) so the caller gets back the first *real* question, never the
filler acknowledgement turn. No QAItem is recorded for that priming
exchange -- there is no real question/answer to log yet.

submit_round() is the per-turn entry point after that: it calls
engine.submit_answer(), then realtime_feedback.generate_feedback() for the
week-10 coach-aside (decision #17 item 2 -- content/structure feedback +
expression suggestions, generated synchronously so it can be saved on the
same QAItem as the answer it's about), turns the result into one QAItem
appended to the caller's InterviewSession, saves immediately (decision
#35's lesson: don't buffer up qa_items and lose them on a mid-interview
crash), and tracks whether the interview should now end (MAX_TOPICS
reached).

Turn-id bookkeeping
--------------------
Every follow-up QAItem's parent_turn_id must point back to its topic's main
question turn_id (a star, not a walk-the-previous-turn chain). The only
reliable moment to know "which topic does the answer I'm about to submit
belong to" is *before* calling engine.submit_answer() -- the engine resets
EngineSession.follow_up_state (and its topic_turn_id) internally the instant
it decides to move to a new topic, as part of the very call that returns the
new topic's opening question. InterviewProgress carries that pointer forward
across calls so submit_round() always reads it from the right side of the
reset.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from backend.conversation import engine
from backend.conversation.engine import EngineSession, TurnResult
from backend.conversation.prompts import Language, Persona
from backend.conversation.realtime_feedback import FeedbackResult, generate_feedback
from backend.storage.db import save_session
from models.session_schema import (
    AudioFeatures,
    FillerFeatures,
    InterviewSession,
    PauseFeatures,
    QAItem,
    SpeechRateFeatures,
    TurnAction,
    VolumeFeatures,
)

if TYPE_CHECKING:
    # Only needed for the type hint below -- kept out of the real import list
    # (backend.speech.features transitively pulls in faster-whisper/numpy/
    # soundfile) so callers that never pass speech_analysis (e.g. the
    # text-only scripts/test_conversation_live.py path) don't pay that
    # import cost just for importing this module.
    from backend.speech.features import SpeechAnalysis

# Decision #3: fixed topic-count cap. Once this many topics have been asked,
# submit_round() reports interview_should_end=True the moment the engine
# wraps up the last one, regardless of the manual "end interview" button.
MAX_TOPICS = 3

# Maps backend/diagnosis/difficulty.py's STAGE_CONFIG persona labels (as
# carried into SessionConfig.interviewer_persona by matcher.to_session_config())
# onto engine.Persona. The three triage personas ("亲和型"/"技术挖掘型"/"严格型")
# line up 1:1 with engine.Persona's three values today -- see
# backend/diagnosis/difficulty.py STAGE_CONFIG and PERSONA_LABEL_KEYS in
# frontend/strings.py, whose persona_css values ("friendly"/"technical"/
# "strict") are literally engine.Persona's own enum values. No triage
# persona is currently unmapped, but the lookup still falls back to
# TECHNICAL for any unrecognized label rather than raising, since
# interviewer_persona is a plain str field, not the Persona enum itself, and
# a loaded/older InterviewSession row could in principle carry a stale value.
_PERSONA_LABEL_TO_ENUM: dict[str, Persona] = {
    "亲和型": Persona.FRIENDLY,
    "技术挖掘型": Persona.TECHNICAL,
    "严格型": Persona.STRICT,
}
_PERSONA_FALLBACK = Persona.TECHNICAL

_PRIMING_ACK: dict[Language, str] = {
    "zh": "好的，我准备好了。",
    "en": "Sure, I'm ready -- let's go.",
}

# Maps engine.TurnResult.judged_level (scoring_judge.judge_answer()'s HIGH/LOW
# gate) onto QAItem.realtime_feedback_score's float range -- the same
# follow-up-facing signal that already drives FollowUpState, just also
# persisted onto the QAItem instead of staying engine-internal.
_JUDGED_LEVEL_TO_SCORE: dict[str, float] = {"high": 1.0, "low": 0.0}


def _speech_analysis_to_audio_features(analysis: "SpeechAnalysis") -> AudioFeatures:
    """
    Lossless repackaging of backend/speech/features.py's SpeechAnalysis into
    the QAItem-persistable AudioFeatures shape (decision #39/week 11) -- see
    models/session_schema.py's AudioFeatures docstring for why this is a
    field-for-field twin rather than the same class reused directly.
    """
    speech_rate = None
    if analysis.speech_rate is not None:
        speech_rate = SpeechRateFeatures(
            chinese_char_count=analysis.speech_rate.chinese_char_count,
            english_word_count=analysis.speech_rate.english_word_count,
            duration_seconds=analysis.speech_rate.duration_seconds,
            primary_metric=analysis.speech_rate.primary_metric,
            primary_value=analysis.speech_rate.primary_value,
            syllables_per_minute=analysis.speech_rate.syllables_per_minute,
        )
    volume = None
    if analysis.volume is not None:
        volume = VolumeFeatures(
            volume_std_dbfs=analysis.volume.volume_std_dbfs,
            baseline_dbfs=analysis.volume.baseline_dbfs,
            relative_deviation_dbfs=analysis.volume.relative_deviation_dbfs,
        )
    return AudioFeatures(
        speech_rate=speech_rate,
        pauses=PauseFeatures(
            count=analysis.pauses.count,
            total_seconds=analysis.pauses.total_seconds,
            longest_seconds=analysis.pauses.longest_seconds,
            average_seconds=analysis.pauses.average_seconds,
        ),
        fillers=FillerFeatures(
            counts=dict(analysis.fillers.counts),
            strong_count=analysis.fillers.strong_count,
            weak_count=analysis.fillers.weak_count,
        ),
        volume=volume,
    )


def resolve_persona(interviewer_persona: str) -> Persona:
    """Map SessionConfig.interviewer_persona (triage's Chinese label) to engine.Persona."""
    return _PERSONA_LABEL_TO_ENUM.get(interviewer_persona, _PERSONA_FALLBACK)


@dataclass
class InterviewProgress:
    """
    Week-9 bookkeeping engine.EngineSession doesn't carry on its own.

    topics_started: how many main questions have been asked so far (starts
        at 1 the moment start() returns, since the priming exchange already
        produced the first one).
    current_topic_turn_id: the turn_id of the main-question QAItem the
        *next* submitted answer belongs to -- either directly (if that
        answer responds to the main question itself) or as the parent to
        record on a follow-up QAItem.
    pending_question_is_main: True when the next answer responds to a fresh
        main question rather than a follow-up -- decides whether the next
        QAItem is a new topic root (fresh turn_id, no parent) or a follow-up
        (fresh turn_id, parent_turn_id=current_topic_turn_id).
    """

    topics_started: int
    current_topic_turn_id: str
    pending_question_is_main: bool


def _last_assistant_message(engine_session: EngineSession) -> str:
    """The question/follow-up the candidate's next answer will respond to."""
    for message in reversed(engine_session.messages):
        if message["role"] == "assistant":
            return message["content"]
    return ""


def start(interviewer_persona: str, language: Language) -> tuple[str, str, EngineSession, InterviewProgress]:
    """
    Begin an interview: resolve the persona, start the EngineSession, and
    run the priming exchange so the very first thing the candidate needs to
    respond to is a real question (decision #4).

    Returns (opening_line, first_question, engine_session, progress) -- both
    opening_line and first_question are meant to be shown as interviewer
    chat bubbles before the candidate types anything; the synthetic priming
    answer is engine-internal only and is never surfaced.
    """
    persona = resolve_persona(interviewer_persona)
    opening_line, engine_session = engine.start_interview(persona, language)
    priming_result = engine.submit_answer(_PRIMING_ACK[language], engine_session)
    progress = InterviewProgress(
        topics_started=1,
        current_topic_turn_id=engine_session.follow_up_state.topic_turn_id,
        pending_question_is_main=True,
    )
    return opening_line, priming_result.reply, engine_session, progress


def submit_round(
    answer: str,
    engine_session: EngineSession,
    progress: InterviewProgress,
    interview_session: InterviewSession,
    speech_analysis: Optional["SpeechAnalysis"] = None,
) -> tuple[TurnResult, InterviewProgress, bool, FeedbackResult]:
    """
    Process one candidate answer: run it through the engine, generate this
    round's coach-aside feedback (week 10, decision #17 item 2), record
    both as one QAItem on interview_session, persist immediately, and
    figure out whether the interview should end now.

    `speech_analysis`: pass backend/speech/features.py's analyze_speech()
    result when `answer` came from a transcribed voice recording (week 11);
    left as None for a typed answer. Converted to the persistable
    AudioFeatures shape via _speech_analysis_to_audio_features() and
    attached to the QAItem -- text-only rounds simply carry audio_features
    =None rather than a fabricated one (same "never force-fill" rule
    AudioFeatures' own docstring calls for).

    Returns (turn_result, updated_progress, interview_should_end, feedback).
    When interview_should_end is True, turn_result.reply must NOT be shown
    to the candidate -- decide_next_action() already folded the transition
    into a new (MAX_TOPICS + 1)-th topic's opening question into that reply
    (see engine.py's module docstring), and this interview isn't asking
    that topic. The QAItem for the answer just given is still recorded
    either way -- it's a real, completed answer, feedback included.

    `feedback` is generated for every call to this function -- there is no
    priming-turn special case to handle here, since session_adapter.start()
    runs the priming exchange itself and never calls submit_round() for it.
    On a feedback-generation failure, feedback's fields are simply None
    (see realtime_feedback.py's module docstring); this never blocks or
    delays recording the answer itself.
    """
    topic_turn_id_for_this_answer = progress.current_topic_turn_id
    answered_main_question = progress.pending_question_is_main
    question_text = _last_assistant_message(engine_session)

    result = engine.submit_answer(answer, engine_session)
    feedback = generate_feedback(question_text, answer, engine_session.language)
    audio_features = _speech_analysis_to_audio_features(speech_analysis) if speech_analysis is not None else None

    qa_turn_id = topic_turn_id_for_this_answer if answered_main_question else str(uuid.uuid4())
    qa_parent_turn_id = None if answered_main_question else topic_turn_id_for_this_answer
    interview_session.qa_items.append(
        QAItem(
            turn_id=qa_turn_id,
            parent_turn_id=qa_parent_turn_id,
            question_text=question_text,
            answer_text=answer,
            realtime_feedback_score=_JUDGED_LEVEL_TO_SCORE.get(result.judged_level),
            content_feedback=feedback.content_feedback,
            expression_suggestions=feedback.expression_suggestions,
            action_taken=result.action,
            audio_features=audio_features,
        )
    )
    save_session(interview_session)

    if result.action == TurnAction.NEXT_QUESTION:
        topics_started = progress.topics_started + 1
        if topics_started > MAX_TOPICS:
            # The engine already generated a (MAX_TOPICS + 1)-th topic's
            # opening question inside result.reply -- we're not asking it.
            # Leave topics_started/current_topic_turn_id as-is: there is no
            # next round for either to describe.
            return result, progress, True, feedback
        new_progress = InterviewProgress(
            topics_started=topics_started,
            current_topic_turn_id=engine_session.follow_up_state.topic_turn_id,
            pending_question_is_main=True,
        )
    else:  # FOLLOW_UP
        new_progress = InterviewProgress(
            topics_started=progress.topics_started,
            current_topic_turn_id=progress.current_topic_turn_id,
            pending_question_is_main=False,
        )

    return result, new_progress, False, feedback


def end_interview(interview_session: InterviewSession) -> None:
    """
    Mark the interview as ended and persist it. Both end triggers (decision
    #3's MAX_TOPICS cutoff and the candidate's manual "end interview"
    button) funnel through this single call.
    """
    interview_session.ended_at = datetime.utcnow()
    save_session(interview_session)
