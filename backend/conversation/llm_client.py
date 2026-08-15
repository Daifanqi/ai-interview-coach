"""
Thin wrapper around the Groq chat completions API.

call_llm() is the single point in the codebase that talks to Groq -- every
other module in backend/conversation/ only ever builds prompt text and
message history, never touches the SDK directly. That keeps the retry /
timeout / error-fallback policy defined in exactly one place.

Design choices:
- The Groq client's own built-in retry logic is disabled (max_retries=0 at
  construction) and replaced with an explicit outer loop here, so "at most
  3 retries" is a single, easy-to-audit number instead of being the product
  of two retry layers stacked on top of each other.
- Errors are never raised out of call_llm(): a candidate mid-interview
  should see a graceful in-character-adjacent message, not a stack trace.
  Only genuinely transient failures (timeouts, connection errors, rate
  limits, 5xx) are retried; config-shaped errors (bad/missing API key,
  malformed request) fail fast since retrying won't fix them.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional, TypedDict

import groq
from dotenv import load_dotenv
from groq import Groq

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.0
# Fallback wait when a 429 response has no Retry-After header at all (rare --
# Groq normally sends one). Deliberately longer than _RETRY_BACKOFF_SECONDS:
# a rate-limit window is seconds-to-a-minute wide, not the ~1s a plain
# connection hiccup needs.
_DEFAULT_RATE_LIMIT_WAIT_SECONDS = 5.0

# call_llm()'s default retry-wait cap. This module's primary caller is
# backend/conversation/engine.py's real-time interview dialogue turn --
# decisions 17/20 in docs/decision_log.md require the live path to degrade
# fast rather than make a candidate wait on retries, so the *default* is the
# real-time-safe one. ml/augment.py's offline batch translation is the one
# caller that should actually wait out Groq's real Retry-After cooldown
# (rate-limit windows run seconds-to-a-minute wide); it opts into that
# explicitly by passing a larger max_retry_wait_seconds rather than the
# default silently getting slower for every caller.
_DEFAULT_MAX_RETRY_WAIT_SECONDS = 2.0

# backend/conversation/llm_client.py -> backend/conversation -> backend -> project root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

_FRIENDLY_ERROR_MESSAGE = (
    "抱歉，AI面试官暂时无法回应，可能是网络或服务出现了问题，请稍后重试。"
    "(Sorry, the AI interviewer is temporarily unavailable due to a network "
    "or service issue -- please try again in a moment.)"
)

# Errors that won't be fixed by retrying: bad/missing credentials, a
# malformed request, or a resource that genuinely doesn't exist.
_NON_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    groq.AuthenticationError,
    groq.BadRequestError,
    groq.PermissionDeniedError,
    groq.NotFoundError,
    groq.UnprocessableEntityError,
)


def _rate_limit_wait_seconds(exc: "groq.RateLimitError") -> float:
    """How long to actually wait after a 429 before retrying.

    Groq's 429 responses carry a Retry-After (or the more precise
    Retry-After-Ms) header with the real cooldown; a fixed 1s/2s backoff
    does nothing once that window is exhausted -- it just burns the retry
    budget on calls that were always going to fail. Bounded to (0, 60]
    seconds, mirroring the same sanity bound the Groq SDK's own (disabled)
    retry logic uses internally, so one malformed/extreme header value can't
    stall a caller indefinitely.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None:
        raw_ms = headers.get("retry-after-ms")
        if raw_ms is not None:
            try:
                wait = float(raw_ms) / 1000
                if 0 < wait <= 60:
                    return wait
            except ValueError:
                pass
        raw = headers.get("retry-after")
        if raw is not None:
            try:
                wait = float(raw)
                if 0 < wait <= 60:
                    return wait
            except ValueError:
                pass
    return _DEFAULT_RATE_LIMIT_WAIT_SECONDS


class ChatMessage(TypedDict):
    """One turn in the conversation history passed to call_llm(), Groq's own message shape."""

    role: str  # "user" or "assistant"
    content: str


_client: Optional[Groq] = None
_client_init_attempted = False


def _get_client() -> Optional[Groq]:
    """
    Lazily construct the Groq client on first use and cache it.

    Returns None (rather than raising) when GROQ_API_KEY is missing, so
    call_llm() can fold "no credentials configured" into the same friendly
    fallback path as any other failure.
    """
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    _client_init_attempted = True

    load_dotenv(dotenv_path=_ENV_PATH)
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY is not set (expected in %s or the environment)", _ENV_PATH)
        return None

    _client = Groq(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
    return _client


def call_llm(
    prompt: str,
    history: list[ChatMessage],
    max_retry_wait_seconds: float = _DEFAULT_MAX_RETRY_WAIT_SECONDS,
) -> str:
    """
    Send `prompt` as the system message plus `history` as the prior
    conversation turns to Groq, and return the assistant's reply text.

    `max_retry_wait_seconds` bounds how long any single inter-attempt sleep
    (including a Retry-After-driven 429 wait) is allowed to run -- callers on
    a latency-sensitive path (the default, e.g. engine.py's live interview
    turn) get a short cap so a rate limit or other transient failure falls
    through to the friendly-fallback response quickly instead of stalling
    the candidate; a patient offline caller (e.g. ml/augment.py's batch
    translation) can pass a larger value to actually wait out Groq's real
    cooldown instead of burning retries uselessly. Pass 0 to never sleep
    between attempts at all.

    Never raises: on persistent failure (or a missing API key) this
    returns a friendly, bilingual fallback string instead, so a calling
    dialogue loop can always treat the return value as user-facing text.
    """
    client = _get_client()
    if client is None:
        return _FRIENDLY_ERROR_MESSAGE

    messages = [{"role": "system", "content": prompt}, *history]

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip()
            last_error = RuntimeError("Groq returned an empty completion")
            wait = _RETRY_BACKOFF_SECONDS * attempt
        except _NON_RETRYABLE_ERRORS as exc:
            logger.error("Non-retryable Groq API error, giving up: %r", exc)
            last_error = exc
            break
        except groq.RateLimitError as exc:  # 429 -- wait the real cooldown, not a guess
            wait = _rate_limit_wait_seconds(exc)
            last_error = exc
        except Exception as exc:  # transient SDK/network failure -- retry
            logger.warning("Groq API call failed (attempt %d/%d): %r", attempt, MAX_ATTEMPTS, exc)
            last_error = exc
            wait = _RETRY_BACKOFF_SECONDS * attempt

        if attempt < MAX_ATTEMPTS:
            capped_wait = min(wait, max_retry_wait_seconds)
            if isinstance(last_error, groq.RateLimitError):
                logger.warning(
                    "Groq rate limit hit (attempt %d/%d), waiting %.1fs before retrying "
                    "(Groq suggested %.1fs, capped to max_retry_wait_seconds=%.1fs): %r",
                    attempt, MAX_ATTEMPTS, capped_wait, wait, max_retry_wait_seconds, last_error,
                )
            time.sleep(capped_wait)

    logger.error("All %d attempt(s) to call Groq failed, returning fallback message: %r", MAX_ATTEMPTS, last_error)
    return _FRIENDLY_ERROR_MESSAGE
