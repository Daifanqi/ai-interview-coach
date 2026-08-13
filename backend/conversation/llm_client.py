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


def call_llm(prompt: str, history: list[ChatMessage]) -> str:
    """
    Send `prompt` as the system message plus `history` as the prior
    conversation turns to Groq, and return the assistant's reply text.

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
        except _NON_RETRYABLE_ERRORS as exc:
            logger.error("Non-retryable Groq API error, giving up: %r", exc)
            last_error = exc
            break
        except Exception as exc:  # transient SDK/network failure -- retry
            logger.warning("Groq API call failed (attempt %d/%d): %r", attempt, MAX_ATTEMPTS, exc)
            last_error = exc

        if attempt < MAX_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_SECONDS * attempt)

    logger.error("All %d attempt(s) to call Groq failed, returning fallback message: %r", MAX_ATTEMPTS, last_error)
    return _FRIENDLY_ERROR_MESSAGE
