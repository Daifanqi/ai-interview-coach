"""
Speech-to-text transcription via faster-whisper (docs/week4_tech_spec.md
section 2.1).

transcribe_audio() is the only function other modules should call: it wraps
a lazily-loaded, module-level faster-whisper model and always turns on
`word_timestamps=True`, since the word-level timestamps it produces are the
sole input backend/speech/features.py needs for its pause/filler-word
analysis (spec section 2.3 -- those features are computed from timestamps
directly, not from a separate VAD pass).

The transcribed text is the "main" output (goes on to content analysis,
including scoring_judge.judge_answer()); the returned word list is the
"side channel" that features.py consumes in parallel. Both come out of the
same transcribe_audio() call so callers never need to run the model twice.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# backend/speech/transcribe.py -> backend/speech -> backend -> project root
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

InterviewLanguage = Literal["zh", "en"]


@dataclass
class Word:
    """One word-level timestamp entry, as produced by faster-whisper's word_timestamps=True."""

    text: str
    start: float  # seconds from the start of the audio file
    end: float
    probability: float  # faster-whisper's per-word confidence


@dataclass
class TranscriptionResult:
    text: str
    language: str  # language faster-whisper detected/used, e.g. "zh" or "en"
    audio_duration_seconds: float  # duration of the whole input file (info.duration), including any silence
    words: list[Word] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Model configuration -- overridable via env vars (loaded from .env, same
# pattern as backend/conversation/llm_client.py's Groq client), since the
# right size/device/compute_type tradeoff depends on the deployment machine
# and isn't something the spec pins down.
# ---------------------------------------------------------------------------

_DEFAULT_MODEL_SIZE = "small"
_DEFAULT_DEVICE = "cpu"
_DEFAULT_COMPUTE_TYPE = "int8"

_model: Optional[WhisperModel] = None
_model_init_attempted = False


def _get_model() -> WhisperModel:
    """Lazily construct and cache the WhisperModel. Raises on failure -- unlike the Groq
    call sites, there is no meaningful fallback for "the ASR model couldn't load";
    the caller has no text to transcribe at all in that case."""
    global _model, _model_init_attempted
    if _model is not None:
        return _model
    if _model_init_attempted:
        raise RuntimeError("faster-whisper model failed to load on a previous attempt; see earlier logs")
    _model_init_attempted = True

    load_dotenv(dotenv_path=_ENV_PATH)
    model_size = os.environ.get("ASR_MODEL_SIZE", _DEFAULT_MODEL_SIZE)
    device = os.environ.get("ASR_DEVICE", _DEFAULT_DEVICE)
    compute_type = os.environ.get("ASR_COMPUTE_TYPE", _DEFAULT_COMPUTE_TYPE)

    logger.info("Loading faster-whisper model %r (device=%r, compute_type=%r)", model_size, device, compute_type)
    _model = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _model


def transcribe_audio(
    audio_path: str,
    *,
    language: Optional[InterviewLanguage] = None,
    vad_filter: bool = False,
) -> TranscriptionResult:
    """
    Transcribe one answer's audio file with word-level timestamps.

    `language`: hint faster-whisper with the interview's configured
    language (zh/en) when known -- improves accuracy over full
    auto-detection. Pass None to let the model detect it.

    `vad_filter`: spec section 2.3 flags this as one of the week's
    unverified items -- faster-whisper's default Silero-based VAD is
    conservative about short (300ms-1s) "thinking pauses" and may or may
    not drop an isolated filler-word-only utterance (e.g. a lone "嗯...").
    Defaults to False (faster-whisper's own library default / "keep it
    close to default" per spec section 2.3) until that's been validated
    against real recordings; pause/filler features below never depend on
    VAD either way since they're computed purely from `words`.
    """
    model = _get_model()
    segments, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=vad_filter,
    )

    text_parts: list[str] = []
    words: list[Word] = []
    for segment in segments:  # `segments` is a generator -- this is what actually runs the model
        text_parts.append(segment.text)
        for w in segment.words or []:
            stripped = w.word.strip()
            if not stripped:
                continue
            words.append(Word(text=stripped, start=w.start, end=w.end, probability=w.probability))

    return TranscriptionResult(
        text="".join(text_parts).strip(),
        language=info.language,
        audio_duration_seconds=info.duration,
        words=words,
    )
