"""
Extreme-case handling for the mandatory follow-up (design doc
docs/persona_prompts_design.md section 5).

The Layer 1 follow-up is mandatory -- one must always be asked -- but its
content can't be a fixed template, or a few rounds in it starts to feel
mechanical. Section 5 identifies five recurring situations that need a
different follow-up strategy than the "normal" case, and prescribes how
each should be handled.

classify_answer_pattern() is a lightweight, rule-based pre-filter, not a
real NLU classifier -- this project has no LLM call wired up yet (the
dialogue engine itself is future work), and even once it exists, the model
reading the full conversation will always be a better judge of nuance than
keyword/length heuristics. The role of this classifier is narrower: catch
the clear-cut cases cheaply (an empty answer, an explicit "I don't know
this area") and turn them into an explicit instruction injected into the
system message -- the same "external code decides, model just executes"
approach used for follow-up round state in follow_up_state.py -- rather
than leaving every case to be silently inferred by the model with no
signal at all.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence

from backend.conversation.prompts import Language


class AnswerPattern(str, Enum):
    """Which of the design doc's section-5 extreme cases (if any) the answer looks like."""

    NORMAL = "normal"
    OFF_TOPIC = "off_topic"  # 答非所问
    PERFUNCTORY = "perfunctory"  # 一两个字的敷衍回答
    EMOTIONAL_DEFENSIVE = "emotional_defensive"  # 情绪化或防御姿态
    ADMITS_UNFAMILIARITY = "admits_unfamiliarity"  # 主动坦白"我不熟/没经验"
    PREEMPTED = "preempted"  # 初始回答已经"抢答"了追问会问的内容


# Below this many characters (after stripping whitespace), an answer is
# treated as perfunctory regardless of content -- this threshold is
# intentionally generous (it's meant to catch "还行" / "随便" / "sure",
# not to flag every short-but-complete answer).
_MIN_SUBSTANTIVE_LENGTH = 6

# Doc section 5 explicitly lists "不知道" as a perfunctory brush-off, not
# an honest admission of unfamiliarity -- the distinguishing factor is
# that ADMITS_UNFAMILIARITY phrases are longer, self-aware statements
# ("这块我们当时没有深入接触"), while these are one-line dismissals.
_PERFUNCTORY_PHRASES = {
    "还行", "随便", "不知道", "不清楚", "都可以", "都行",
    "sure", "fine", "whatever", "i don't know", "idk", "not really",
    "no idea", "dunno",
}

_UNFAMILIARITY_PHRASES = {
    "不熟", "没经验", "没做过", "不太了解", "没接触过", "没有深入接触", "没有接触过",
    "not familiar", "no experience with", "haven't done", "haven't worked with",
    "not really familiar with", "don't have much experience",
}

_DEFENSIVE_PHRASES = {
    "凭什么", "这有什么问题", "这个问题没有意义", "随你怎么想", "算了",
    "why does it matter", "i don't see why", "that's not fair", "forget it",
    "whatever you say",
}


def _normalize(text: str) -> str:
    return text.strip()


def _matches_phrase_bank(normalized_lower: str, phrase_bank: set[str]) -> bool:
    return any(phrase in normalized_lower for phrase in phrase_bank)


def classify_answer_pattern(
    answer_text: str,
    *,
    question_keywords: Optional[Sequence[str]] = None,
    planned_follow_up_keywords: Optional[Sequence[str]] = None,
) -> AnswerPattern:
    """
    Classify a candidate's answer against the five extreme cases.

    question_keywords: a few key terms from the question just answered
        (e.g. nouns pulled from the question bank entry). Used only for the
        OFF_TOPIC heuristic -- if omitted, OFF_TOPIC is never returned.
    planned_follow_up_keywords: key terms describing what the *next*
        follow-up was going to ask about (e.g. ["原因", "为什么"] for a
        "why did you choose X" follow-up). Used only for the PREEMPTED
        heuristic -- if omitted, PREEMPTED is never returned.

    Checks run in the order the design doc implies matters: an answer that
    is simply too short to say anything (PERFUNCTORY) should not also be
    flagged as "off-topic" or "defensive" just because it happens to share
    no words with the question.
    """
    normalized = _normalize(answer_text)
    lowered = normalized.lower()

    if not normalized or len(normalized) <= _MIN_SUBSTANTIVE_LENGTH:
        return AnswerPattern.PERFUNCTORY
    if _matches_phrase_bank(lowered, _PERFUNCTORY_PHRASES):
        return AnswerPattern.PERFUNCTORY

    if _matches_phrase_bank(lowered, _DEFENSIVE_PHRASES):
        return AnswerPattern.EMOTIONAL_DEFENSIVE

    if _matches_phrase_bank(lowered, _UNFAMILIARITY_PHRASES):
        return AnswerPattern.ADMITS_UNFAMILIARITY

    if planned_follow_up_keywords and _matches_phrase_bank(lowered, {k.lower() for k in planned_follow_up_keywords}):
        return AnswerPattern.PREEMPTED

    if question_keywords and not _matches_phrase_bank(lowered, {k.lower() for k in question_keywords}):
        return AnswerPattern.OFF_TOPIC

    return AnswerPattern.NORMAL


_STRATEGY_GUIDANCE: dict[tuple[AnswerPattern, Language], str] = {
    (AnswerPattern.OFF_TOPIC, "zh"): (
        "候选人的回答似乎没有正面回应问题。追问时不要重复原问题，先用一句话"
        "简短复述候选人实际说了什么，再把话题委婉地拉回原本问题的核心，同时"
        "给出一个更具体、范围更小的切入角度。"
    ),
    (AnswerPattern.OFF_TOPIC, "en"): (
        "The candidate's answer doesn't seem to directly address the "
        "question. Don't repeat the original question verbatim -- briefly "
        "acknowledge what they actually said, then gently steer back to the "
        "core of the original question with a more specific, narrower angle."
    ),
    (AnswerPattern.PERFUNCTORY, "zh"): (
        "候选人的回答非常简短/信息量很低。不要把追问变成逼问：主动降低回答"
        "门槛，例如给出2-3个具体选项供候选人挑选，或聚焦到一个很小的事实性"
        "问题上，避免再抛出开放式大问题。"
    ),
    (AnswerPattern.PERFUNCTORY, "en"): (
        "The candidate's answer is extremely terse / carries little "
        "information. Don't turn the follow-up into an interrogation -- "
        "lower the bar for answering, e.g. offer 2-3 concrete options to "
        "choose from, or narrow in on one small factual question, rather "
        "than asking another open-ended question."
    ),
    (AnswerPattern.EMOTIONAL_DEFENSIVE, "zh"): (
        "候选人的回答透露出情绪化或防御姿态。追问要更谨慎，语气进一步放缓，"
        "可以先用一句共情或缓冲的话，再决定是否继续这一话题；保持中性、"
        "事实性的追问方式，不必流露不满。"
    ),
    (AnswerPattern.EMOTIONAL_DEFENSIVE, "en"): (
        "The candidate's answer shows emotion or a defensive posture. Slow "
        "down and soften the tone -- lead with a brief empathetic or "
        "buffering remark before deciding whether to continue this topic; "
        "keep the follow-up neutral and fact-focused, and don't let any "
        "impatience show."
    ),
    (AnswerPattern.ADMITS_UNFAMILIARITY, "zh"): (
        "候选人主动坦白对这部分不熟悉/没有经验。不要继续追问其不熟悉的细节，"
        "应把追问转向候选人更熟悉、更相关的部分，例如：'没关系，那你更熟悉"
        "的是哪部分，我们聊聊那个'。"
    ),
    (AnswerPattern.ADMITS_UNFAMILIARITY, "en"): (
        "The candidate has openly admitted they're not familiar with / have "
        "no experience in this area. Don't keep probing the details they "
        "don't know -- redirect the follow-up toward a part they're more "
        "familiar with that's still relevant, e.g. 'No worries -- what part "
        "are you more familiar with? Let's talk about that instead.'"
    ),
    (AnswerPattern.PREEMPTED, "zh"): (
        "候选人在初始回答中已经提前覆盖了追问原本要问的内容。不要生搬硬套"
        "再问一遍同样的问题，追问应转为确认+拓展到一个新维度，例如：'你刚才"
        "其实已经提到了原因，那我更想知道……'。"
    ),
    (AnswerPattern.PREEMPTED, "en"): (
        "The candidate's initial answer already covered what the follow-up "
        "was going to ask. Don't force the same question again -- turn the "
        "follow-up into a brief acknowledgment plus an expansion into a new "
        "angle the candidate hasn't covered yet, e.g. 'You've actually "
        "already touched on the reason -- what I'm more curious about now "
        "is...'."
    ),
}


def get_strategy_guidance(pattern: AnswerPattern, language: Language) -> Optional[str]:
    """
    Return the injectable follow-up strategy instruction for this pattern,
    or None for AnswerPattern.NORMAL (nothing extra to inject -- the
    persona's own follow-up logic in SYSTEM_PROMPT already covers the
    default case).
    """
    if pattern is AnswerPattern.NORMAL:
        return None
    return _STRATEGY_GUIDANCE[(pattern, language)]


def build_extreme_case_context(
    answer_text: str,
    language: Language,
    *,
    question_keywords: Optional[Sequence[str]] = None,
    planned_follow_up_keywords: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """
    Convenience wrapper: classify the answer and return the ready-to-inject
    guidance sentence in one call, or None when nothing extra applies.

    Meant to be concatenated alongside
    follow_up_state.build_state_context() when assembling the system
    message for the next follow-up turn.
    """
    pattern = classify_answer_pattern(
        answer_text,
        question_keywords=question_keywords,
        planned_follow_up_keywords=planned_follow_up_keywords,
    )
    return get_strategy_guidance(pattern, language)
