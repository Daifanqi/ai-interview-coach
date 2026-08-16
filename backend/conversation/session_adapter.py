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

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from backend.conversation import engine
from backend.conversation.engine import EngineSession, TurnResult
from backend.conversation.prompts import Language, Persona
from backend.conversation.realtime_feedback import FeedbackResult, generate_feedback
from backend.rag.retriever import retrieve_questions
from backend.report.generator import generate_review_report
from backend.storage.db import save_session
from models.question_schema import Question, QuestionType
from models.session_schema import (
    AudioFeatures,
    FillerFeatures,
    InterviewSession,
    InterviewStage,
    PauseFeatures,
    QAItem,
    SpeechRateFeatures,
    TurnAction,
    VolumeFeatures,
)

logger = logging.getLogger(__name__)

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

# Rotation of question_type across an interview's main topics (decision
# #39/week 12). With MAX_TOPICS=3 this asks exactly one behavioral, one
# technical, and one case_analysis question per interview -- a deliberately
# well-rounded shape rather than 3 random draws that could land all on one
# type. Indexed by (topic_number - 1) % len(...), so it still cycles
# sensibly if MAX_TOPICS is ever raised.
_TOPIC_QUESTION_TYPE_ROTATION: list[QuestionType] = ["behavioral", "technical", "case_analysis"]

# How many top candidates to draw from before picking one at random (see
# _pick_next_question()) -- keeps repeated interviews for the same job_type
# from asking the identical 3 questions every time.
_CANDIDATE_POOL_SIZE = 5


def _pick_next_question(job_type: str, topic_number: int) -> Optional[Question]:
    """
    Best-effort retrieval of the question that should ground the upcoming
    `topic_number`-th main topic (1-indexed), rotating through the bank's
    three question types per _TOPIC_QUESTION_TYPE_ROTATION.

    retriever.py's own docstring notes "most relevant" is computed against
    a synthetic per-(job_type, question_type) query, not real per-question
    differentiation -- so among the several equally-plausible top matches,
    picking uniformly at random (rather than always the #1 result) is what
    keeps repeat interviews for the same job_type from being identical,
    without contradicting how "relevance" was ever meant to work here.

    Returns None on any retrieval failure (Chroma index not buildable,
    embedding-model hiccup, or genuinely no bank match for this
    job_type/question_type) -- callers must treat that as "fall back to
    free generation for this topic" rather than an error, the same
    "optional enhancement degrades silently" rule this project already
    applies to TTS (backend/speech/tts.py) and realtime feedback
    (realtime_feedback.py).
    """
    question_type = _TOPIC_QUESTION_TYPE_ROTATION[(topic_number - 1) % len(_TOPIC_QUESTION_TYPE_ROTATION)]
    try:
        candidates = retrieve_questions(job_type, question_type=question_type, k=_CANDIDATE_POOL_SIZE)
    except Exception:
        logger.warning(
            "RAG question retrieval failed for job_type=%r, question_type=%r; falling back to free generation.",
            job_type,
            question_type,
            exc_info=True,
        )
        return None
    if not candidates:
        return None
    return random.choice(candidates)


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
    current_topic_question_id: the RAG question bank id (decision #39/week
        12) that grounded the current topic's main question, or None if no
        bank match was found and the topic was freely generated instead.
        Mirrors current_topic_turn_id's lifecycle exactly -- set once when
        the topic starts, carried forward through that topic's follow-ups,
        and only used (as QAItem.question_source_id) on the main-question
        QAItem itself, never on a follow-up.
    pending_question_is_main: True when the next answer responds to a fresh
        main question rather than a follow-up -- decides whether the next
        QAItem is a new topic root (fresh turn_id, no parent) or a follow-up
        (fresh turn_id, parent_turn_id=current_topic_turn_id).
    """

    topics_started: int
    current_topic_turn_id: str
    current_topic_question_id: Optional[str]
    pending_question_is_main: bool


def _last_assistant_message(engine_session: EngineSession) -> str:
    """The question/follow-up the candidate's next answer will respond to."""
    for message in reversed(engine_session.messages):
        if message["role"] == "assistant":
            return message["content"]
    return ""


def start(
    interviewer_persona: str,
    language: Language,
    job_type: str,
    interview_stage: InterviewStage,
) -> tuple[str, str, EngineSession, InterviewProgress]:
    """
    Begin an interview: resolve the persona, start the EngineSession, and
    run the priming exchange so the very first thing the candidate needs to
    respond to is a real question (decision #4).

    `job_type`/`interview_stage` (decision #39/week 12, both previously
    missing from this call entirely -- see engine.EngineSession's
    interview_stage field and this module's _pick_next_question()): the
    first topic's question is retrieved from the RAG bank for `job_type`
    before the priming call, same as every later topic in submit_round().

    Returns (opening_line, first_question, engine_session, progress) -- both
    opening_line and first_question are meant to be shown as interviewer
    chat bubbles before the candidate types anything; the synthetic priming
    answer is engine-internal only and is never surfaced.
    """
    persona = resolve_persona(interviewer_persona)
    opening_line, engine_session = engine.start_interview(persona, language, interview_stage)
    first_question = _pick_next_question(job_type, topic_number=1)
    priming_result = engine.submit_answer(
        _PRIMING_ACK[language],
        engine_session,
        next_question_hint=first_question.question_text if first_question else None,
    )
    progress = InterviewProgress(
        topics_started=1,
        current_topic_turn_id=engine_session.follow_up_state.topic_turn_id,
        current_topic_question_id=first_question.question_id if first_question else None,
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

    RAG question bank grounding (decision #39/week 12): before calling the
    engine, this pre-fetches a candidate question for the *next* topic in
    case this round's answer is the one that wraps up the current topic --
    see engine.submit_answer()'s next_question_hint param for why that has
    to happen speculatively, before we know this round's outcome. When this
    round does turn out to end the topic (result.action ==
    NEXT_QUESTION), that candidate's question_id becomes the new
    current_topic_question_id, which the *following* submit_round() call
    will attach to the new topic's QAItem as question_source_id. No
    candidate is fetched once topics_started already reached MAX_TOPICS,
    since any further topic the engine free-generates from here is the
    (MAX_TOPICS + 1)-th bleed-through question this function discards below
    anyway (see that branch) -- fetching one would just be wasted retrieval.

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
    topic_question_id_for_this_answer = progress.current_topic_question_id
    answered_main_question = progress.pending_question_is_main
    question_text = _last_assistant_message(engine_session)

    next_question = None
    if interview_session.config is not None and progress.topics_started < MAX_TOPICS:
        next_question = _pick_next_question(interview_session.config.job_type, progress.topics_started + 1)
    next_question_hint = next_question.question_text if next_question else None

    result = engine.submit_answer(answer, engine_session, next_question_hint=next_question_hint)
    feedback = generate_feedback(question_text, answer, engine_session.language)
    audio_features = _speech_analysis_to_audio_features(speech_analysis) if speech_analysis is not None else None

    qa_turn_id = topic_turn_id_for_this_answer if answered_main_question else str(uuid.uuid4())
    qa_parent_turn_id = None if answered_main_question else topic_turn_id_for_this_answer
    qa_question_source_id = topic_question_id_for_this_answer if answered_main_question else None
    interview_session.qa_items.append(
        QAItem(
            turn_id=qa_turn_id,
            parent_turn_id=qa_parent_turn_id,
            question_text=question_text,
            question_source_id=qa_question_source_id,
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
            current_topic_question_id=next_question.question_id if next_question else None,
            pending_question_is_main=True,
        )
    else:  # FOLLOW_UP
        new_progress = InterviewProgress(
            topics_started=progress.topics_started,
            current_topic_turn_id=progress.current_topic_turn_id,
            current_topic_question_id=progress.current_topic_question_id,
            pending_question_is_main=False,
        )

    return result, new_progress, False, feedback


def end_interview(interview_session: InterviewSession) -> None:
    """
    Mark the interview as ended, generate its review report, and persist
    both. Both end triggers (decision #3's MAX_TOPICS cutoff and the
    candidate's manual "end interview" button) funnel through this single
    call.

    Week 15 (decision #44): generate_review_report() (week 13, decision
    #42) is wired in here -- decision #42 deliberately deferred that wiring
    until there was a report page to consume it; frontend/app.py's
    render_interview_ended_page() is that page now. Wrapped in try/except
    so a scoring/highlight-pick failure degrades to interview_session.report
    staying None (the interview itself still ends and saves correctly) --
    the same "optional enhancement never takes down the core flow" rule
    this project already applies to TTS/ASR/realtime feedback, extended
    here even though report generation isn't really "optional" from the
    candidate's point of view, because by the time this runs the interview
    is already over and there is nothing left to protect except this save.
    """
    interview_session.ended_at = datetime.utcnow()
    try:
        interview_session.report = generate_review_report(interview_session)
    except Exception:
        logger.exception(
            "generate_review_report() failed while ending session %s; ending without a report",
            interview_session.session_id,
        )
        interview_session.report = None
    save_session(interview_session)
