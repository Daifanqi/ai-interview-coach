"""
Week 10 real-time feedback: one Groq call per round producing the two
pieces of coaching decision #17 item 2 calls for -- (a) content/structure
feedback and (b) 2-3 expression/wording naturalization suggestions --
meant to be shown as a "coach aside" alongside the interviewer's next
reply, never folded into the in-character dialogue itself.

generate_feedback() is the single entry point. It deliberately mirrors
backend/conversation/scoring_judge.py's call pattern -- same judge-tier
model, same short-timeout/no-retry discipline -- since both calls sit on
the live per-turn path and must never add meaningful latency or ever
block the interview loop. The two modules intentionally do not share a
client: same reasoning as scoring_judge.py's own separation from
llm_client.py -- each real-time call site owns its own timeout/retry
policy rather than being coupled to another call site's.

Failure handling differs from scoring_judge.py on purpose: scoring_judge's
HIGH/LOW gate always needs *some* answer to keep the follow-up state
machine moving, so it falls all the way down to a rule-based heuristic.
Feedback text has no such rule-based substitute -- there is no honest way
to fabricate "here's what was good/bad about your answer" from a keyword
rule, and doing so would mean putting invented words in the coach's mouth.
So the only fallback tier here is: any failure (timeout, missing API key,
malformed JSON, empty completion) -> both fields come back None, and the
caller simply shows no feedback that round.

Not called for the priming exchange (session_adapter.start()'s synthetic
"sure, I'm ready" turn) -- there is no real answer there to give feedback
on. That's enforced by session_adapter.py only ever invoking this from
submit_round(), never from start().
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

from backend.conversation.prompts import Language

logger = logging.getLogger(__name__)

# Same fast/judge-tier model as scoring_judge.py's GROQ_JUDGE_MODEL --
# deliberately not a third model. This call produces more output than the
# judge's 2-field gate (a feedback paragraph + 2-3 suggestions), so it
# gets a larger token budget and timeout than scoring_judge.py, but still
# nowhere near llm_client.py's 10s conversational budget -- this sits on
# the same latency-sensitive per-turn path.
GROQ_FEEDBACK_MODEL = "llama-3.1-8b-instant"

REQUEST_TIMEOUT_SECONDS = 2.5
MAX_OUTPUT_TOKENS = 350

# backend/conversation/realtime_feedback.py -> backend/conversation -> backend -> project root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


@dataclass
class FeedbackResult:
    """generate_feedback()'s return value. Both fields are None together on any failure -- never partially filled."""

    content_feedback: Optional[str]
    expression_suggestions: Optional[list[str]]


# ---------------------------------------------------------------------------
# System prompt (bilingual, not persona-differentiated -- this is coaching
# text shown directly to the candidate, not an in-character judgment, so
# there's no persona voice to match here the way scoring_judge.py's grading
# rubric needs one)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: dict[Language, str] = {
    "zh": """你是候选人身边的面试教练，任务是针对候选人刚给出的这一轮回答，给出简短、有针对性的反馈，
帮助候选人在接下来的作答中做得更好。这段反馈只会展示给候选人自己看，不会出现在面试对话里。

请输出两部分：
1. content_feedback：1-2句话点评这次回答的内容/结构（是否完整回应了问题、逻辑是否清晰、
   有没有具体细节支撑），要具体、有针对性，不要泛泛而谈或简单复述回答内容。
2. expression_suggestions：2-3条关于表达/措辞的自然化建议，每条不超过一句话，聚焦语法、
   用词、说法是否地道；如果这次回答表达上已经比较自然，可以给出更专业/更精炼的替代说法
   作为提升建议，不要为了凑数量硬找问题。

只输出如下 JSON，不要输出任何解释、前缀或多余文字：
{"content_feedback":"...","expression_suggestions":["...","..."]}""",
    "en": """You are the candidate's personal interview coach. Your job is to give short,
specific feedback on the answer the candidate just gave, to help them do better on the
next one. This feedback is shown only to the candidate -- it never appears inside the
interview conversation itself.

Produce two parts:
1. content_feedback: 1-2 sentences on the content/structure of this answer (did it fully
   address the question, was the logic clear, was there concrete detail behind it) --
   be specific and actionable, not generic, and don't just restate the answer.
2. expression_suggestions: 2-3 short wording/grammar naturalization tips, each one
   sentence or less, focused on grammar, word choice, or phrasing that would sound more
   natural/professional. If the answer's phrasing was already solid, offer a more
   polished or idiomatic alternative as a stretch suggestion instead -- don't invent
   problems just to hit a count.

Output only the following JSON, no explanation, prefix, or extra text:
{"content_feedback":"...","expression_suggestions":["...","..."]}""",
}


# ---------------------------------------------------------------------------
# Input truncation -- same head/tail strategy as scoring_judge.py's
# _truncate_answer(), duplicated rather than imported since the two modules
# are intentionally decoupled call sites.
# ---------------------------------------------------------------------------

_TRUNCATION_THRESHOLD_CHARS = 300
_HEAD_CHARS = 200
_TAIL_CHARS = 50


def _truncate_answer(answer: str) -> str:
    if len(answer) <= _TRUNCATION_THRESHOLD_CHARS:
        return answer
    return f"{answer[:_HEAD_CHARS]} …(中间部分省略)… {answer[-_TAIL_CHARS:]}"


# ---------------------------------------------------------------------------
# Groq call
# ---------------------------------------------------------------------------

_client: Optional[Groq] = None
_client_init_attempted = False


def _get_feedback_client() -> Optional[Groq]:
    """
    Lazily construct and cache a Groq client dedicated to feedback calls.

    Kept separate from llm_client._get_client() and scoring_judge's own
    client for the same reason scoring_judge.py gives for its own
    separation: this call site owns its own timeout and has no
    client-level retries. Returns None when GROQ_API_KEY is missing,
    folding "no credentials configured" into the same no-feedback-this-
    round fallback as any other failure.
    """
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True

    load_dotenv(dotenv_path=_ENV_PATH)
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY is not set (expected in %s or the environment); real-time feedback will be skipped", _ENV_PATH)
        return None

    _client = Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
    return _client


def _call_groq_feedback(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Run the single-attempt, short-timeout feedback completion. Returns None on any failure."""
    client = _get_feedback_client()
    if client is None:
        return None

    started = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=GROQ_FEEDBACK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 -- any failure here must degrade, not propagate
        logger.warning("Groq feedback call failed after %.0fms, skipping feedback this round: %r", (time.monotonic() - started) * 1000, exc)
        return None

    content = response.choices[0].message.content
    if not content or not content.strip():
        logger.warning("Groq feedback call returned an empty completion, skipping feedback this round")
        return None
    return content.strip()


_MAX_SUGGESTIONS = 3


def _parse_json_response(content: str) -> Optional[FeedbackResult]:
    """Strict-ish parse of the `{"content_feedback", "expression_suggestions"}` schema; None on any shape mismatch."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    content_feedback = data.get("content_feedback")
    if not isinstance(content_feedback, str) or not content_feedback.strip():
        return None

    raw_suggestions = data.get("expression_suggestions")
    if not isinstance(raw_suggestions, list):
        return None
    suggestions = [s.strip() for s in raw_suggestions if isinstance(s, str) and s.strip()]
    if not suggestions:
        return None

    return FeedbackResult(
        content_feedback=content_feedback.strip(),
        expression_suggestions=suggestions[:_MAX_SUGGESTIONS],
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_feedback(question: str, answer: str, language: Language) -> FeedbackResult:
    """
    Generate this round's coach-aside feedback for `answer` (given the
    `question` it responds to). Always returns a FeedbackResult -- on any
    failure both fields are None (see module docstring for why there is no
    rule-based fallback tier here, unlike scoring_judge.py).
    """
    system_prompt = _SYSTEM_PROMPT[language]
    user_prompt = f"【Question】{question}\n【Answer】{_truncate_answer(answer)}"

    raw_content = _call_groq_feedback(system_prompt, user_prompt)
    if raw_content is not None:
        parsed = _parse_json_response(raw_content)
        if parsed is not None:
            return parsed
        logger.warning("Groq feedback completion had unparseable/invalid shape, skipping feedback this round: %r", raw_content)

    return FeedbackResult(content_feedback=None, expression_suggestions=None)
