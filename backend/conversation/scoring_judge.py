"""
LLM-judge scoring for the follow-up state machine, replacing the old
length + keyword heuristic that used to live in engine.py
(docs/week4_tech_spec.md section 1).

judge_answer() is the single entry point: it scores one answer against its
question as HIGH/LOW ("is this specific enough to keep probing?") using a
small, low-latency Groq model, and always returns a result -- it never
raises and never blocks the follow-up pipeline waiting on a slow call.

Three-tier fallback (spec section 1.2 point 3), each tier only reached if
the one before it failed:
  1. LLM call + strict JSON parse of the `{"level", "hook"}` schema.
  2. If JSON parsing/validation failed (Groq's `json_object` mode only
     guarantees syntactically valid JSON, not schema conformance): salvage
     a bare "high"/"low" keyword out of the raw completion text via regex.
  3. If there was no usable completion at all (missing API key, timeout,
     network/5xx error, empty completion) or the regex salvage also came up
     empty: fall back to the original length + keyword rule engine.py used
     before this module existed.

Persona differentiation follows spec section 1.3's recommended "option C":
the JSON schema and core grading rubric are shared across all three
personas (a fast/stable gating signal shouldn't carry per-persona branching
complexity), and only a short, persona-specific addendum is appended to the
system prompt's tail to nudge what counts as "specific" for that persona.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from groq import Groq

from backend.conversation.follow_up_state import Score
from backend.conversation.prompts import Persona

logger = logging.getLogger(__name__)

# A separate, much smaller/faster model than llm_client.GROQ_MODEL -- this
# call sits on the real-time follow-up path and only needs to produce a
# 2-field classification, not a conversational reply (spec section 1.2
# point 1).
GROQ_JUDGE_MODEL = "llama-3.1-8b-instant"

# Spec section 1.2 point 5 calls for an 800ms-1.2s budget; the judge call
# gets exactly one attempt at this timeout and no retry loop -- a slow/
# flaky API call must fall through to the fallback tiers immediately
# rather than eating further into the follow-up turn's latency budget.
REQUEST_TIMEOUT_SECONDS = 1.0

# The JSON schema is two short fields (~15-25 output tokens per spec
# section 1.2); cap generation well above that as a safety margin without
# leaving room for a runaway/verbose completion to blow the latency budget.
MAX_OUTPUT_TOKENS = 60

# backend/conversation/scoring_judge.py -> backend/conversation -> backend -> project root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

JudgeSource = Literal["llm", "regex_fallback", "heuristic_fallback"]


@dataclass
class JudgeResult:
    """judge_answer()'s return value: the HIGH/LOW gate plus which tier produced it."""

    level: Score
    # A short, quotable detail the next follow-up can hook into (spec
    # section 1.2's output schema). Only ever populated by the LLM tier --
    # the fallback tiers have no reliable way to extract one, so they
    # always return "".
    hook: str
    source: JudgeSource


# ---------------------------------------------------------------------------
# Persona-specific system prompt addenda (spec section 1.3, option C)
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT_CORE = """你是面试追问判断助手。任务：判断候选人回答相对于当前面试问题的"具体性"——
是否包含可以继续深挖的细节（如数据指标、技术选型、时间线、决策权衡、个人角色贡献、具体案例）。

判定标准：
- high：回答中出现具体的技术名词/数字/时间线/权衡决策/个人贡献等可以继续追问的实体
- low：回答空泛、套话、纯自我评价、缺乏具体细节、明显跑题，或过短（少于15个字）

只输出如下 JSON，不要输出任何解释、前缀或多余文字：
{"level":"high或low","hook":"可追问的具体点，不超过10个字；level为low时填空字符串"}"""

_PERSONA_ADDENDA: dict[Persona, str] = {
    Persona.TECHNICAL: """# 技术挖掘型追加标准
对"技术具体性"要求更高：必须包含技术选型、架构设计、量化指标（性能数据/规模数字）
中的至少一项才能判定为 high；纯流程描述不算。""",
    Persona.FRIENDLY: """# 亲和型追加标准
更看重语言的真实感和个人化程度：第一人称具体经历、带有真实细节的表达（哪怕不够
"技术"）判定为 high；明显背诵式、模板化的回答即使包含关键词也判定为 low。""",
    Persona.STRICT: """# 严格型追加标准
重点关注回答是否直接、逻辑自洽：如果回答存在回避问题、自相矛盾、或对具体问题给
泛泛而谈的回应，判定为 low，即使包含个别专业词汇。""",
}


def _build_judge_system_prompt(persona: Persona) -> str:
    """Assemble the shared grading backbone with this persona's short addendum (spec 1.3)."""
    return f"{_JUDGE_SYSTEM_PROMPT_CORE}\n\n{_PERSONA_ADDENDA[persona]}"


# ---------------------------------------------------------------------------
# Input truncation (spec section 1.2 point 4)
# ---------------------------------------------------------------------------

_TRUNCATION_THRESHOLD_CHARS = 300
_HEAD_CHARS = 200
_TAIL_CHARS = 50


def _truncate_answer(answer: str) -> str:
    """
    Keep the opening (usually the thesis/main point) and closing (usually
    the conclusion/quantified result) of an overlong answer, dropping the
    middle -- cheaper on input tokens than truncating from one end, and
    per spec section 1.2 point 4, loses less signal than a naive head-only
    cut for this scoring task.
    """
    if len(answer) <= _TRUNCATION_THRESHOLD_CHARS:
        return answer
    return f"{answer[:_HEAD_CHARS]} …(中间部分省略)… {answer[-_TAIL_CHARS:]}"


# ---------------------------------------------------------------------------
# Tier 1: Groq call + JSON parse
# ---------------------------------------------------------------------------

_client: Optional[Groq] = None
_client_init_attempted = False


def _get_judge_client() -> Optional[Groq]:
    """
    Lazily construct and cache a Groq client dedicated to judge calls.

    Kept separate from llm_client._get_client(): this call site needs its
    own, much shorter timeout and no client-level retries, and the two
    call sites shouldn't be coupled just to save a few lines of client
    setup. Returns None when GROQ_API_KEY is missing, folding "no
    credentials configured" into the same fallback path as any other
    failure.
    """
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True

    load_dotenv(dotenv_path=_ENV_PATH)
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY is not set (expected in %s or the environment); judge calls will use fallback scoring", _ENV_PATH)
        return None

    _client = Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
    return _client


def _call_groq_judge(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Run the single-attempt, short-timeout judge completion. Returns None on any failure."""
    client = _get_judge_client()
    if client is None:
        return None

    started = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=GROQ_JUDGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 -- any failure here must degrade, not propagate
        logger.warning("Groq judge call failed after %.0fms, falling back: %r", (time.monotonic() - started) * 1000, exc)
        return None

    content = response.choices[0].message.content
    if not content or not content.strip():
        logger.warning("Groq judge returned an empty completion, falling back")
        return None
    return content.strip()


_VALID_LEVELS = {"high", "low"}
_MAX_HOOK_CHARS = 40  # generous cap above the spec's ~10-char guidance -- json_object mode doesn't enforce it


def _parse_json_response(content: str) -> Optional[tuple[Score, str]]:
    """Strict-ish parse of the `{"level", "hook"}` schema; None on any shape mismatch."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    level = data.get("level")
    if not isinstance(level, str) or level.strip().lower() not in _VALID_LEVELS:
        return None

    hook = data.get("hook", "")
    if not isinstance(hook, str):
        hook = ""

    return level.strip().lower(), hook.strip()[:_MAX_HOOK_CHARS]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tier 2: regex salvage of a bare high/low keyword (spec section 1.2 point 3)
# ---------------------------------------------------------------------------

_LEVEL_REGEX = re.compile(r'"level"\s*:\s*"(high|low)"', re.IGNORECASE)
_BARE_LEVEL_REGEX = re.compile(r"\b(high|low)\b", re.IGNORECASE)


def _extract_level_via_regex(content: str) -> Optional[Score]:
    """Salvage a level out of a completion that failed strict JSON parsing/validation."""
    match = _LEVEL_REGEX.search(content) or _BARE_LEVEL_REGEX.search(content)
    if match is None:
        return None
    return match.group(1).lower()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Tier 3: the original length + keyword rule from engine.py
# ---------------------------------------------------------------------------

# Below this length (characters), an answer is treated as too short to
# count as HIGH even if it happens to contain a detail marker.
_FALLBACK_MIN_HIGH_LENGTH = 40

# Rough signal that an answer contains reasoning/specifics rather than just
# a bare assertion -- moved here verbatim from engine.py's old
# _heuristic_score_answer(), now used only as the last-resort tier.
_FALLBACK_DETAIL_MARKERS = (
    "因为", "原因", "具体", "比如", "例如", "所以", "结果", "后来", "于是", "当时",
    "because", "specifically", "for example", "e.g.", "as a result", "which meant",
)


def _heuristic_fallback_score(answer: str) -> Score:
    """
    Last-resort tier 3: reached only when both the LLM call and its regex
    salvage failed. Has no way to produce a `hook`, so judge_answer()
    always pairs this with hook="".
    """
    normalized = answer.strip()
    lowered = normalized.lower()
    has_detail_marker = any(marker in lowered for marker in _FALLBACK_DETAIL_MARKERS) or bool(re.search(r"\d", normalized))
    return "high" if len(normalized) >= _FALLBACK_MIN_HIGH_LENGTH and has_detail_marker else "low"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def judge_answer(question: str, answer: str, persona: Persona) -> JudgeResult:
    """
    Score `answer` (given the `question` it responds to) as HIGH/LOW
    "follow-up-worthiness" for `persona`, per docs/week4_tech_spec.md
    section 1. Always returns a JudgeResult -- see module docstring for the
    three-tier fallback that guarantees this.
    """
    system_prompt = _build_judge_system_prompt(persona)
    user_prompt = f"【问题】{question}\n【回答】{_truncate_answer(answer)}"

    raw_content = _call_groq_judge(system_prompt, user_prompt)
    if raw_content is not None:
        parsed = _parse_json_response(raw_content)
        if parsed is not None:
            level, hook = parsed
            return JudgeResult(level=level, hook=hook, source="llm")

        regex_level = _extract_level_via_regex(raw_content)
        if regex_level is not None:
            logger.info("Groq judge JSON parse failed, salvaged level=%r via regex", regex_level)
            return JudgeResult(level=regex_level, hook="", source="regex_fallback")

        logger.warning("Groq judge completion had no parseable level, using heuristic fallback: %r", raw_content)

    return JudgeResult(level=_heuristic_fallback_score(answer), hook="", source="heuristic_fallback")
