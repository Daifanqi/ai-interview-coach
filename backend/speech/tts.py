"""
Piper-based text-to-speech synthesis (docs/week4_tech_spec.md section 3).

Two synthesis paths, per spec section 3.2 point 5:
- synthesize_short_reply(): a simple one-shot "wait for the full text, then
  synthesize" path. Used for short replies (follow-up questions) where
  generation is already fast -- the streaming machinery below buys little
  and adds engineering complexity the spec says isn't worth it there.
- stream_reply_to_speech(): sentence-chunked streaming synthesis (spec
  section 3.2 option B) for longer text (interview summaries / long
  feedback): as text arrives incrementally (e.g. from an LLM streaming
  call), it's split into sentence-sized chunks, each chunk is handed to a
  small Piper worker pool as soon as it's ready, and WAV bytes come out in
  original order -- so playback of the first sentence can start well
  before the model has finished generating the rest of the reply.

Voice/persona mapping is spec section 3.1: English gets three distinct
Piper voices (one per persona). Chinese has exactly one official Piper
voice (zh_CN-huayan-medium -- Piper's catalog has no second zh_CN voice),
so persona differentiation there is entirely via per-persona
SynthesisConfig parameters (length_scale/noise_scale/noise_w_scale).
"""
from __future__ import annotations

import io
import logging
import re
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

from piper import PiperVoice, SynthesisConfig
from piper.download_voices import download_voice

from backend.conversation.prompts import Language, Persona

logger = logging.getLogger(__name__)

# backend/speech/tts.py -> backend/speech -> backend -> project root -> data/
# (matches backend/storage/db.py's DEFAULT_DB_PATH convention for local data)
_VOICES_DIR = Path(__file__).resolve().parents[2] / "data" / "piper_voices"


# ---------------------------------------------------------------------------
# 3.1 Voice/persona mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VoiceProfile:
    voice_id: str  # Piper voice name, e.g. "en_US-amy-medium"
    length_scale: Optional[float] = None
    noise_scale: Optional[float] = None
    noise_w_scale: Optional[float] = None


_EN_VOICE_PROFILES: dict[Persona, VoiceProfile] = {
    Persona.FRIENDLY: VoiceProfile("en_US-amy-medium"),
    Persona.TECHNICAL: VoiceProfile("en_US-ryan-high"),
    Persona.STRICT: VoiceProfile("en_GB-alan-medium"),
}

# All three personas share the one official Piper zh_CN voice and
# differentiate purely through synthesis parameters (spec section 3.1's
# table) -- this is a deliberately limited substitute for a real second
# voice; see docs/decision_log.md's "needs a listening evaluation" item.
_ZH_VOICE_ID = "zh_CN-huayan-medium"
_ZH_VOICE_PROFILES: dict[Persona, VoiceProfile] = {
    Persona.FRIENDLY: VoiceProfile(_ZH_VOICE_ID, length_scale=1.08, noise_scale=0.75, noise_w_scale=0.85),
    Persona.TECHNICAL: VoiceProfile(_ZH_VOICE_ID, length_scale=1.00, noise_scale=0.60, noise_w_scale=0.70),
    Persona.STRICT: VoiceProfile(_ZH_VOICE_ID, length_scale=0.92, noise_scale=0.50, noise_w_scale=0.60),
}


def _voice_profile(persona: Persona, language: Language) -> VoiceProfile:
    return _ZH_VOICE_PROFILES[persona] if language == "zh" else _EN_VOICE_PROFILES[persona]


def warm_up_voices() -> None:
    """
    Pre-download and load every voice this module is configured to use.

    The actual startup/ops warm-up step list_configured_voice_ids()'s own
    docstring anticipates (week 11/decision #39): calling this once when the
    app process starts means the first real synthesize_short_reply() call
    mid-interview never pays the download-on-first-use cost, which would
    otherwise surprise a candidate with several seconds of dead air.
    """
    for voice_id in list_configured_voice_ids():
        _get_voice(voice_id)


def list_configured_voice_ids() -> set[str]:
    """
    All distinct Piper voice ids this module is configured to use --
    intended for a startup/ops warm-up step that pre-downloads every voice
    once (each is tens of MB; letting the first real synthesis call trigger
    the download would surprise a candidate with several seconds of dead
    air).
    """
    return {p.voice_id for p in _EN_VOICE_PROFILES.values()} | {_ZH_VOICE_ID}


# ---------------------------------------------------------------------------
# Voice loading (download-on-first-use, then cached in-process)
# ---------------------------------------------------------------------------

_loaded_voices: dict[str, PiperVoice] = {}


def _get_voice(voice_id: str) -> PiperVoice:
    if voice_id in _loaded_voices:
        return _loaded_voices[voice_id]

    _VOICES_DIR.mkdir(parents=True, exist_ok=True)
    model_path = _VOICES_DIR / f"{voice_id}.onnx"
    config_path = _VOICES_DIR / f"{voice_id}.onnx.json"
    if not model_path.exists() or not config_path.exists():
        logger.info("Downloading Piper voice %r into %s", voice_id, _VOICES_DIR)
        download_voice(voice_id, _VOICES_DIR)

    voice = PiperVoice.load(model_path, config_path)
    _loaded_voices[voice_id] = voice
    return voice


def _synthesis_config(profile: VoiceProfile) -> SynthesisConfig:
    return SynthesisConfig(
        length_scale=profile.length_scale,
        noise_scale=profile.noise_scale,
        noise_w_scale=profile.noise_w_scale,
    )


def _synthesize_to_wav_bytes(voice: PiperVoice, text: str, syn_config: SynthesisConfig) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        voice.synthesize_wav(text, wav_file, syn_config=syn_config)
    return buffer.getvalue()


def save_wav(audio_bytes: bytes, output_path: str) -> str:
    """Write previously-synthesized WAV bytes to disk; returns `output_path` for chaining."""
    Path(output_path).write_bytes(audio_bytes)
    return output_path


# ---------------------------------------------------------------------------
# Simplified one-shot path (spec 3.2 point 5) -- short replies / follow-ups
# ---------------------------------------------------------------------------


def synthesize_short_reply(text: str, persona: Persona, language: Language) -> bytes:
    """
    Synthesize `text` in a single Piper call and return WAV bytes.

    For short, already-fully-generated replies (typically 1-2 sentences,
    e.g. a follow-up question) -- spec section 3.2 point 5 explicitly
    prefers this simple path over sentence-chunked streaming there, since
    generation is already fast and streaming's first-audio-latency win is
    negligible for text this short.
    """
    profile = _voice_profile(persona, language)
    voice = _get_voice(profile.voice_id)
    return _synthesize_to_wav_bytes(voice, text, _synthesis_config(profile))


# ---------------------------------------------------------------------------
# 3.2 points 1-3: streamed-text sentence chunking
# ---------------------------------------------------------------------------

_SENTENCE_END_CHARS = set("。！？.!?")
_FORCE_SPLIT_CHARS = set("，, ")

_ZH_MIN_SEGMENT_CHARS = 6
_ZH_MAX_SEGMENT_CHARS = 40
_EN_MIN_SEGMENT_WORDS = 4
_EN_MAX_SEGMENT_WORDS = 25

# A '.' preceded by a digit is treated as a decimal/version-number point,
# never a sentence end (covers "3.14", "v2.0", spec 3.2 point 3). This is a
# deliberately conservative simplification: a sentence that genuinely ends
# right after a number ("...grew by 40.") won't be split here either, but
# will still get force-split once it runs past the max-length threshold, or
# closed out by flush() once the stream ends -- matching the spec's "simple
# regex is enough for the common cases" scope, not a full sentence-boundary model.
_DIGIT_BEFORE_PERIOD = re.compile(r"\d$")

# Common English abbreviations whose internal/trailing periods aren't
# sentence ends (spec 3.2 point 3's "e.g., v2.0"-style examples).
_ABBREVIATION_TAIL = re.compile(
    r"\b(?:[A-Za-z]\.){1,3}$|\b(?:Mr|Mrs|Ms|Dr|Prof|vs|etc|approx|Inc|Ltd|Jr|Sr)\.$",
    re.IGNORECASE,
)


def _is_false_positive_period(text_through_period: str) -> bool:
    prefix = text_through_period[:-1]
    if _DIGIT_BEFORE_PERIOD.search(prefix):
        return True
    return bool(_ABBREVIATION_TAIL.search(text_through_period))


@dataclass
class TextChunker:
    """
    Buffers incrementally-arriving text and yields sentence-sized chunks
    ready for TTS, per spec section 3.2 points 1-3.

    feed() is meant to be called once per token/delta as an LLM reply
    streams in; flush() closes out whatever's left once the stream ends,
    even if it never reached a sentence boundary.
    """

    language: Language
    _buffer: str = field(default="", init=False, repr=False)

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        return self._drain()

    def flush(self) -> Optional[str]:
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining or None

    def _min_length(self) -> int:
        return _ZH_MIN_SEGMENT_CHARS if self.language == "zh" else _EN_MIN_SEGMENT_WORDS

    def _max_length(self) -> int:
        return _ZH_MAX_SEGMENT_CHARS if self.language == "zh" else _EN_MAX_SEGMENT_WORDS

    def _segment_length(self, segment: str) -> int:
        return len(segment.strip()) if self.language == "zh" else len(segment.split())

    def _drain(self) -> list[str]:
        text = self._buffer
        chunks: list[str] = []
        start = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in _SENTENCE_END_CHARS and not (ch == "." and _is_false_positive_period(text[: i + 1])):
                candidate = text[start : i + 1]
                if self._segment_length(candidate) >= self._min_length():
                    chunks.append(candidate.strip())
                    start = i + 1
                # Too short: leave `start` where it is and keep scanning --
                # this boundary gets absorbed into a longer chunk ending at
                # a later one (spec 3.2 point 2's "merge into the next
                # punctuation mark, then split").
            elif self._segment_length(text[start : i + 1]) > self._max_length():
                force_at = self._nearest_force_split(text, start, i)
                if force_at is not None:
                    chunks.append(text[start : force_at + 1].strip())
                    start = force_at + 1
            i += 1
        self._buffer = text[start:]
        return [c for c in chunks if c]

    @staticmethod
    def _nearest_force_split(text: str, start: int, upto: int) -> Optional[int]:
        for j in range(upto, start, -1):
            if text[j] in _FORCE_SPLIT_CHARS:
                return j
        return None


# ---------------------------------------------------------------------------
# 3.2 point 4: synthesis worker pool + ordered playback queue
# ---------------------------------------------------------------------------

DEFAULT_STREAMING_WORKERS = 2  # spec 3.2 point 4: "可视资源情况开1-2个并行"


def stream_reply_to_speech(
    text_stream: Iterable[str],
    persona: Persona,
    language: Language,
    *,
    max_workers: int = DEFAULT_STREAMING_WORKERS,
) -> Iterator[bytes]:
    """
    Full pipeline for spec section 3.2's streaming path.

    Consumes `text_stream` (incremental text deltas, e.g. from an LLM
    streaming call), sentence-chunks it via TextChunker as each delta
    arrives, submits each completed chunk to a small Piper worker pool
    immediately, and yields WAV bytes strictly in original order.

    Because `text_stream` is itself pulled one delta at a time, synthesis
    of an already-completed sentence runs in a background thread while
    later deltas are still arriving -- by the time the model finishes
    generating, the earlier chunks are typically already synthesized, and
    any that finish early are yielded immediately rather than waiting for
    the whole reply. A caller that wants true "audio for sentence 1 plays
    while sentence 3 is still being generated" gets that for free by
    iterating this generator concurrently with its own playback.
    """
    profile = _voice_profile(persona, language)
    voice = _get_voice(profile.voice_id)  # load/download once, before any submission
    syn_config = _synthesis_config(profile)
    chunker = TextChunker(language)

    pool = ThreadPoolExecutor(max_workers=max_workers)
    pending: dict[int, Future] = {}
    next_submit_index = 0
    next_yield_index = 0

    def _submit(chunk_text: str) -> None:
        nonlocal next_submit_index
        pending[next_submit_index] = pool.submit(_synthesize_to_wav_bytes, voice, chunk_text, syn_config)
        next_submit_index += 1

    try:
        for delta in text_stream:
            for chunk in chunker.feed(delta):
                _submit(chunk)
            while next_yield_index in pending and pending[next_yield_index].done():
                yield pending.pop(next_yield_index).result()
                next_yield_index += 1

        remaining = chunker.flush()
        if remaining is not None:
            _submit(remaining)

        while next_yield_index < next_submit_index:
            yield pending.pop(next_yield_index).result()
            next_yield_index += 1
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
