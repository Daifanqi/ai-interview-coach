"""
Follow-up state machine for a single topic (main question).

Implements the "round count + score" state described in
docs/persona_prompts_design.md sections 1.2 and 6.4: this state must be
maintained by external code and injected into the system message as a
short natural-language sentence, rather than asking the model to count
follow-up rounds on its own across a long conversation -- LLMs are not a
reliable multi-turn counter (design doc 6.4).

One FollowUpState instance covers exactly one topic (one main QAItem and
its chain of follow-ups). When the dialogue engine moves to a new main
question, it creates a fresh FollowUpState rather than reusing/resetting
this one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from models.session_schema import TurnAction

from backend.conversation.prompts import Language

Score = Literal["high", "low"]

# Safety valve 1 (upper bound): never ask more than this many total
# follow-up rounds (including the mandatory Layer 1 round) on one topic.
MAX_FOLLOW_UP_ROUNDS = 4

# Safety valve 2 (lower bound / early exit): end the topic early once this
# many consecutive rounds come back minimal/uninformative, even if the
# upper-bound cap hasn't been reached yet (design doc section 1.2 & 5).
MINIMAL_STREAK_LIMIT = 2


@dataclass
class FollowUpRound:
    """The internally-assessed outcome of one follow-up answer."""

    score: Score
    # True when the answer was extremely terse / carried no real information
    # (e.g. "还行" / "不知道") -- see design doc section 5. This is tracked
    # separately from `score` because the lower-bound early-exit rule keys
    # specifically on this signal, not on LOW scores in general.
    is_minimal: bool = False


@dataclass
class FollowUpState:
    """Round count + score history for the follow-up chain on one topic."""

    topic_turn_id: str  # turn_id of the main QAItem this follow-up chain belongs to
    round: int = 0  # number of follow-up rounds completed (asked AND answered) so far
    history: list[FollowUpRound] = field(default_factory=list)

    def record_round(self, score: Score, is_minimal: bool = False) -> None:
        """Record the internal assessment of the answer to the most recent follow-up."""
        self.history.append(FollowUpRound(score=score, is_minimal=is_minimal))
        self.round = len(self.history)

    def _consecutive_minimal_streak(self) -> int:
        streak = 0
        for r in reversed(self.history):
            if not r.is_minimal:
                break
            streak += 1
        return streak


class FollowUpStrategy(str, Enum):
    """
    The reason decide_next_action() chose its action -- lets the prompt-
    building layer phrase the next follow-up appropriately (e.g. switch to
    an easier angle vs. stay at the same depth) without re-deriving why.
    """

    MANDATORY_FIRST = "mandatory_first"  # Layer 1: unconditional first follow-up, no score history yet
    MAINTAIN_DEPTH = "maintain_depth"  # exactly one round of history so far, or a HIGH/LOW split
    DEEPEN_EASIER_ANGLE = "deepen_easier_angle"  # two consecutive LOW scores
    STOP_HIGH_SCORES = "stop_high_scores"  # two consecutive HIGH scores
    STOP_SAFETY_CAP = "stop_safety_cap"  # hit the MAX_FOLLOW_UP_ROUNDS upper bound
    STOP_MINIMAL_STREAK = "stop_minimal_streak"  # MINIMAL_STREAK_LIMIT consecutive minimal/uninformative answers


@dataclass
class FollowUpDecision:
    action: TurnAction
    strategy: FollowUpStrategy


def decide_next_action(state: FollowUpState) -> FollowUpDecision:
    """
    Apply the rules from design doc section 1.2 to decide whether to keep
    following up on this topic or move on.

    Check order matters:
    1. The minimal-response early exit is checked first -- design doc
       section 1.2 explicitly allows it to fire "even before the [4-round]
       cap", and section 5 treats it as a distinct signal worth recording,
       not just a byproduct of two LOW scores.
    2. The score-pattern rules (two LOW / two HIGH / mixed) are evaluated
       next. A "stop" outcome here (two HIGHs) is returned as-is.
    3. Only when the pattern rules would otherwise continue probing does
       the MAX_FOLLOW_UP_ROUNDS safety cap get a chance to override them --
       the cap must never be shadowed by "two consecutive HIGHs", but it
       must always win over "keep probing" once the round limit is hit.
    """
    if state.round > 0 and state._consecutive_minimal_streak() >= MINIMAL_STREAK_LIMIT:
        return FollowUpDecision(TurnAction.NEXT_QUESTION, FollowUpStrategy.STOP_MINIMAL_STREAK)

    if state.round == 0:
        return FollowUpDecision(TurnAction.FOLLOW_UP, FollowUpStrategy.MANDATORY_FIRST)

    if len(state.history) >= 2:
        last_two = [r.score for r in state.history[-2:]]
        if last_two == ["low", "low"]:
            pattern = FollowUpDecision(TurnAction.FOLLOW_UP, FollowUpStrategy.DEEPEN_EASIER_ANGLE)
        elif last_two == ["high", "high"]:
            pattern = FollowUpDecision(TurnAction.NEXT_QUESTION, FollowUpStrategy.STOP_HIGH_SCORES)
        else:
            pattern = FollowUpDecision(TurnAction.FOLLOW_UP, FollowUpStrategy.MAINTAIN_DEPTH)
    else:
        # Exactly one round of history: "刚完成第一轮追问" -- stay at the
        # current depth for one more round before the pattern rules apply.
        pattern = FollowUpDecision(TurnAction.FOLLOW_UP, FollowUpStrategy.MAINTAIN_DEPTH)

    if pattern.action == TurnAction.FOLLOW_UP and state.round >= MAX_FOLLOW_UP_ROUNDS:
        return FollowUpDecision(TurnAction.NEXT_QUESTION, FollowUpStrategy.STOP_SAFETY_CAP)

    return pattern


def build_state_context(state: FollowUpState, language: Language = "zh") -> str:
    """
    Render the current follow-up state as one plain-language sentence to
    inject into the system message before generating the next follow-up
    (design doc section 1.2's engineering suggestion / section 6.4), e.g.
    "当前是第2轮追问，上一轮评分：低". This is internal instruction text
    for the model, never something shown to the candidate.

    Describes the round about to be asked (state.round + 1) together with
    the score of the round that was just completed, if any.
    """
    next_round = state.round + 1
    if not state.history:
        if language == "zh":
            return f"当前是第{next_round}轮追问（第一层固定追问，尚无评分历史）。"
        return (
            f"This is follow-up round {next_round} for the current topic "
            "(the mandatory Layer 1 follow-up; no score history yet)."
        )

    last_score = state.history[-1].score
    if language == "zh":
        score_word = "高" if last_score == "high" else "低"
        return f"当前是第{next_round}轮追问，上一轮评分：{score_word}。"

    return (
        f"This is follow-up round {next_round} for the current topic. "
        f"Previous round's score: {last_score.upper()}."
    )
