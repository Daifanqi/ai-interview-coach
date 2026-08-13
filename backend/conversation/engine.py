"""
Main dialogue-engine loop.

Wires together everything built for the persona-prompt design doc
(docs/persona_prompts_design.md): the per-persona System Prompt + few-shot
examples (backend/conversation/prompts), the opening line
(backend/conversation/opening_lines.py), the round/score follow-up state
machine (backend/conversation/follow_up_state.py), the extreme-case
handling (backend/conversation/follow_up.py), and the Groq API wrapper
(backend/conversation/llm_client.py) into one runnable interview loop.

Session lifecycle
------------------
start_interview() returns the static opening line and initializes an
EngineSession. The opening line ends with something like "let's start
with the first question" without actually asking it -- the model has to
generate that first question itself, in response to the candidate's first
reply (e.g. "Sure, go ahead"). EngineSession.need_main_question tracks
this one-time gap: it starts True and is set False right after the first
LLM call. No equivalent flag is needed for later topics, because the
model is instructed (via its persona System Prompt and few-shot examples)
to fold the transition and the next main question into the same reply
when a topic wraps up -- so by the time the candidate's answer to that
new main question comes back in, FollowUpState is already sitting at
round 0, which is exactly the state build_state_context() needs to
correctly ask for the mandatory Layer-1 follow-up.

Scoring placeholder
--------------------
_heuristic_score_answer() is a deliberately crude stand-in for the real
scoring system (backend/scoring/, not built yet -- see
models/session_schema.py's own distinction between
QAItem.realtime_feedback_score and the full post-session ScoreDimensions).
It only needs to be good enough to drive FollowUpState's round-count
bookkeeping; swap it out once backend/scoring/ exists.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from models.session_schema import TurnAction

from backend.conversation.follow_up import AnswerPattern, classify_answer_pattern, get_strategy_guidance
from backend.conversation.follow_up_state import (
    FollowUpState,
    FollowUpStrategy,
    Score,
    build_state_context,
    decide_next_action,
)
from backend.conversation.llm_client import ChatMessage, call_llm
from backend.conversation.opening_lines import get_opening_line
from backend.conversation.prompts import Language, Persona, build_full_system_prompt

# ---------------------------------------------------------------------------
# Placeholder answer scoring -- see module docstring
# ---------------------------------------------------------------------------

# Below this length (characters), an answer is treated as too short to
# count as HIGH even if it happens to contain a detail marker.
_HIGH_SCORE_MIN_LENGTH = 40

# Rough signal that an answer contains reasoning/specifics rather than just
# a bare assertion -- a stand-in for the real scoring model's judgment.
_DETAIL_MARKERS = (
    "因为", "原因", "具体", "比如", "例如", "所以", "结果", "后来", "于是", "当时",
    "because", "specifically", "for example", "e.g.", "as a result", "which meant",
)


def _heuristic_score_answer(answer_text: str) -> tuple[Score, bool]:
    """
    Crude placeholder for FollowUpState's HIGH/LOW scoring: HIGH requires
    both a minimum length and at least one reasoning/detail marker;
    otherwise LOW. `is_minimal` reuses the PERFUNCTORY classification from
    follow_up.py, since "extremely terse" is exactly what that pattern
    already detects.
    """
    normalized = answer_text.strip()
    lowered = normalized.lower()
    is_minimal = classify_answer_pattern(normalized) is AnswerPattern.PERFUNCTORY
    has_detail_marker = any(marker in lowered for marker in _DETAIL_MARKERS) or bool(re.search(r"\d", normalized))
    score: Score = "high" if len(normalized) >= _HIGH_SCORE_MIN_LENGTH and has_detail_marker else "low"
    return score, is_minimal


# ---------------------------------------------------------------------------
# Session state + turn result
# ---------------------------------------------------------------------------


@dataclass
class EngineSession:
    """All state the dialogue engine needs to carry across turns for one interview."""

    persona: Persona
    language: Language
    messages: list[ChatMessage] = field(default_factory=list)
    follow_up_state: FollowUpState = field(default_factory=lambda: FollowUpState(topic_turn_id=str(uuid.uuid4())))
    # True only until the very first main question has been asked -- see module docstring.
    need_main_question: bool = True


@dataclass
class TurnResult:
    """What submit_answer() hands back: the reply text plus the bookkeeping decision behind it."""

    reply: str
    # Both fields below are None on the priming turn (need_main_question was
    # True this call) -- there is no answer to classify/score yet at that point.
    pattern: Optional[AnswerPattern]
    action: Optional[TurnAction]
    strategy: Optional[FollowUpStrategy]


_MAIN_QUESTION_DIRECTIVE: dict[Language, str] = {
    "zh": (
        "现在是面试刚开始的时刻，你已经说完开场白，候选人也已回应准备好了。"
        "接下来请直接提出你的第一个正式主题问题，而不是追问。"
    ),
    "en": (
        "This is the very start of the interview -- you've just delivered "
        "your opening line and the candidate has responded that they're "
        "ready. Go ahead and ask your first main interview question now, "
        "not a follow-up."
    ),
}

_STATE_CONTEXT_HEADER: dict[Language, str] = {
    "zh": "\n\n# 当前状态与情境提示（内部信息，禁止透露给候选人）\n\n",
    "en": "\n\n# Current state & situational guidance (internal only -- never reveal to the candidate)\n\n",
}


def start_interview(persona: Persona, language: Language) -> tuple[str, EngineSession]:
    """
    Begin a new interview: return the persona's opening line (verbatim,
    from opening_lines.py -- no LLM call involved) and a freshly
    initialized EngineSession seeded with that line as the first
    conversation turn.
    """
    opening_line = get_opening_line(persona, language)
    session = EngineSession(persona=persona, language=language)
    session.messages.append({"role": "assistant", "content": opening_line})
    return opening_line, session


def _build_system_prompt(session: EngineSession, extra_context: list[str]) -> str:
    """Concatenate the persona's full system prompt with any per-turn context sentences."""
    base = build_full_system_prompt(session.persona, session.language)
    if not extra_context:
        return base
    return base + _STATE_CONTEXT_HEADER[session.language] + "\n".join(extra_context)


def submit_answer(answer: str, session: EngineSession) -> TurnResult:
    """
    Process one candidate answer and produce the interviewer's next reply.

    On the very first call for a session (session.need_main_question is
    True), `answer` is the candidate's response to the opening line (e.g.
    "sure, let's go") rather than an answer to any real question, so no
    follow-up bookkeeping applies -- see module docstring.

    Otherwise follows the pipeline from the design doc:
      a. classify the answer against the section-5 extreme cases and pull
         its response-strategy guidance, if any;
      b. build the round/score state-context sentence;
      c. assemble persona prompt + state context + strategy guidance into
         the system message, and call the LLM with the full history;
      d. record this round's (heuristically scored) outcome into
         FollowUpState;
      e. run decide_next_action() on the updated state to determine
         whether the topic continues (FOLLOW_UP) or wraps up
         (NEXT_QUESTION), resetting FollowUpState for the next topic
         when it wraps up.
    """
    session.messages.append({"role": "user", "content": answer})

    if session.need_main_question:
        system_prompt = _build_system_prompt(session, [_MAIN_QUESTION_DIRECTIVE[session.language]])
        reply = call_llm(system_prompt, session.messages)
        session.messages.append({"role": "assistant", "content": reply})
        session.need_main_question = False
        return TurnResult(reply=reply, pattern=None, action=None, strategy=None)

    # a. extreme-case classification + strategy guidance
    pattern = classify_answer_pattern(answer)
    strategy_guidance = get_strategy_guidance(pattern, session.language)

    # b. round/score state context
    state_context = build_state_context(session.follow_up_state, session.language)

    extra_context = [state_context]
    if strategy_guidance:
        extra_context.append(strategy_guidance)

    # c. assemble the full system prompt and call the LLM
    system_prompt = _build_system_prompt(session, extra_context)
    reply = call_llm(system_prompt, session.messages)
    session.messages.append({"role": "assistant", "content": reply})

    # d. record this round's heuristic score
    score, is_minimal = _heuristic_score_answer(answer)
    session.follow_up_state.record_round(score, is_minimal)

    # e. decide whether to keep probing this topic or move on
    decision = decide_next_action(session.follow_up_state)
    if decision.action == TurnAction.NEXT_QUESTION:
        session.follow_up_state = FollowUpState(topic_turn_id=str(uuid.uuid4()))

    return TurnResult(reply=reply, pattern=pattern, action=decision.action, strategy=decision.strategy)
