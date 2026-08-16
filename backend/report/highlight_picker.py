"""
Week 13 AI-picked "highlight moment" (docs/decision_log.md decision 9): given
a finished session's scored main-topic answers, ask an LLM which one turn
stands out most -- and why -- as a genuinely subjective editorial judgment
call, not another rubric score.

pick_highlight() is the single entry point. It mirrors backend/conversation/
scoring_judge.py's call pattern (small/fast judge-tier model, strict
timeout, no client-level retries, JSON response_format, regex salvage tier)
even though this call sits on backend/report/generator.py's offline
report-generation path rather than scoring_judge.py's live per-turn path --
report generation still shouldn't hang indefinitely waiting on a slow
completion, and there's no reason to invent a different call pattern for a
call site facing the same Groq API.

Unlike scoring_judge.py, this always has something *honest* to fall back to:
scoring_judge's rule-based tier is a genuine substitute heuristic for a
missing LLM opinion, but there's no rule that can fabricate "why this turn
stood out". So the fallback tier here instead picks the highest-overall-
score topic and pairs it with a plainly factual (not fabricated) reason --
"the highest-scoring answer in this session" is true whether or not the LLM
call succeeded. That means highlight_turn_id is populated whenever there is
at least one scored topic, and pick_highlight() only ever returns
(None, None) when detailed_scores itself is empty.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

from models.session_schema import InterviewSession, TopicScoreDetail

logger = logging.getLogger(__name__)

# Same fast/judge-tier model as scoring_judge.py/realtime_feedback.py --
# this call produces a short editorial pick + 1-2 sentence reason, not a
# conversational reply, so it doesn't need llm_client.GROQ_MODEL's budget.
GROQ_HIGHLIGHT_MODEL = "llama-3.1-8b-instant"

# Report generation is not on the interview's latency-sensitive live path
# (unlike scoring_judge.py's 1.0s / realtime_feedback.py's 2.5s), so this
# gets a somewhat larger budget -- but still a single attempt, no retries,
# so a slow/flaky call degrades to the fallback tier promptly rather than
# stalling report generation.
REQUEST_TIMEOUT_SECONDS = 3.0
MAX_OUTPUT_TOKENS = 200

# backend/report/highlight_picker.py -> backend/report -> backend -> project root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_SYSTEM_PROMPT: dict[str, str] = {
    "zh": """你是面试复盘报告的编辑。你会看到候选人本次面试若干轮主问题的题目和综合得分摘要。
请选出其中"最值得被单独标注出来"的一轮——可以是表现最亮眼的一轮，也可以是最有代表性、
最能体现候选人特点或潜力的一轮。这是一个主观的编辑判断，不是简单地选最高分那一轮。

只输出如下 JSON，不要输出任何解释、前缀或多余文字：
{"turn_id":"选中轮次的turn_id","reason":"1-2句话说明为什么选这一轮，要具体、有针对性，不要套话"}""",
    "en": """You are editing an interview review report. You will see this session's main-topic
questions and their overall score summaries. Pick the ONE turn most worth calling out --
either the standout best answer, or the one most representative of the candidate's strengths
or potential. This is a subjective editorial call, not simply picking the highest score.

Output only the following JSON, no explanation, prefix, or extra text:
{"turn_id":"the chosen turn's turn_id","reason":"1-2 sentences on why, specific and concrete, not generic"}""",
}

_FALLBACK_REASON: dict[str, str] = {
    "zh": "本次面试中综合得分最高的一轮回答。",
    "en": "The highest-scoring answer in this session.",
}


# ---------------------------------------------------------------------------
# Tier 1: Groq call + JSON parse
# ---------------------------------------------------------------------------

_client: Optional[Groq] = None
_client_init_attempted = False


def _get_highlight_client() -> Optional[Groq]:
    """
    Lazily construct and cache a Groq client dedicated to highlight-pick
    calls. Kept separate from every other call site's client for the same
    reason scoring_judge.py/realtime_feedback.py give for their own
    separation: each call site owns its own timeout/retry policy. Returns
    None when GROQ_API_KEY is missing, folding "no credentials configured"
    into the same fallback path as any other failure.
    """
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True

    load_dotenv(dotenv_path=_ENV_PATH)
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error(
            "GROQ_API_KEY is not set (expected in %s or the environment); highlight picking will use the rule-based fallback",
            _ENV_PATH,
        )
        return None

    _client = Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
    return _client


def _build_user_prompt(detailed_scores: dict[str, TopicScoreDetail]) -> str:
    lines = [
        f"- turn_id={turn_id} | 题目：{detail.question_text} | 综合得分：{detail.overall_score}/10"
        for turn_id, detail in detailed_scores.items()
    ]
    return "\n".join(lines)


def _call_groq_highlight(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Run the single-attempt highlight-pick completion. Returns None on any failure."""
    client = _get_highlight_client()
    if client is None:
        return None

    started = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=GROQ_HIGHLIGHT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 -- any failure here must degrade, not propagate
        logger.warning(
            "Groq highlight-pick call failed after %.0fms, falling back: %r", (time.monotonic() - started) * 1000, exc
        )
        return None

    content = response.choices[0].message.content
    if not content or not content.strip():
        logger.warning("Groq highlight-pick call returned an empty completion, falling back")
        return None
    return content.strip()


def _parse_json_response(content: str, valid_turn_ids: set[str]) -> Optional[tuple[str, str]]:
    """Strict-ish parse of the `{"turn_id", "reason"}` schema; None on any shape mismatch
    or if the model names a turn_id that isn't one of this session's scored topics."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    turn_id = data.get("turn_id")
    if not isinstance(turn_id, str) or turn_id not in valid_turn_ids:
        return None

    reason = data.get("reason", "")
    if not isinstance(reason, str) or not reason.strip():
        return None

    return turn_id, reason.strip()


# ---------------------------------------------------------------------------
# Tier 2: regex salvage of a bare turn_id
# ---------------------------------------------------------------------------

_TURN_ID_REGEX = re.compile(r'"turn_id"\s*:\s*"([^"]+)"')


def _extract_turn_id_via_regex(content: str, valid_turn_ids: set[str]) -> Optional[str]:
    match = _TURN_ID_REGEX.search(content)
    if match is None or match.group(1) not in valid_turn_ids:
        return None
    return match.group(1)


# ---------------------------------------------------------------------------
# Tier 3: rule-based fallback -- highest overall_score, see module docstring
# ---------------------------------------------------------------------------


def _heuristic_fallback_pick(detailed_scores: dict[str, TopicScoreDetail], language: str) -> tuple[str, str]:
    best_turn_id = max(detailed_scores, key=lambda tid: detailed_scores[tid].overall_score)
    return best_turn_id, _FALLBACK_REASON.get(language, _FALLBACK_REASON["zh"])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def pick_highlight(
    session: InterviewSession,
    detailed_scores: dict[str, TopicScoreDetail],
    language: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Pick this session's (highlight_turn_id, highlight_reason). Returns
    (None, None) only when `detailed_scores` is empty (nothing was scored,
    so there is nothing to highlight) -- otherwise always returns a real
    turn_id from `detailed_scores` (see module docstring for the three-tier
    fallback that guarantees this). `session` is accepted for future
    context (e.g. richer per-turn transcript) but the current prompt only
    needs `detailed_scores`.
    """
    del session  # not yet used -- see docstring
    if not detailed_scores:
        return None, None

    valid_turn_ids = set(detailed_scores.keys())
    system_prompt = _SYSTEM_PROMPT.get(language, _SYSTEM_PROMPT["zh"])
    user_prompt = _build_user_prompt(detailed_scores)

    raw_content = _call_groq_highlight(system_prompt, user_prompt)
    if raw_content is not None:
        parsed = _parse_json_response(raw_content, valid_turn_ids)
        if parsed is not None:
            return parsed

        regex_turn_id = _extract_turn_id_via_regex(raw_content, valid_turn_ids)
        if regex_turn_id is not None:
            logger.info("Groq highlight-pick JSON parse failed, salvaged turn_id=%r via regex", regex_turn_id)
            return regex_turn_id, _FALLBACK_REASON.get(language, _FALLBACK_REASON["zh"])

        logger.warning("Groq highlight-pick completion had no usable turn_id, using heuristic fallback: %r", raw_content)

    return _heuristic_fallback_pick(detailed_scores, language)
