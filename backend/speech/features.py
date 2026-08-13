"""
Speech feature extraction from a transcribe_audio() result
(docs/week4_tech_spec.md section 2): speech rate, pauses, filler words, and
volume -- the four parallel "side channel" features that ride alongside the
transcribed text (spec section 2.1), computed here rather than in
transcribe.py so ASR itself stays a thin, single-purpose wrapper.

Design notes shared by more than one feature below:

- Pause and filler-word detection both work directly off word-level
  timestamps (backend/speech/transcribe.py's Word list), never off a VAD
  segmentation -- spec section 2.3 explicitly calls for this, since
  faster-whisper's default VAD is tuned for dropping/splitting on longer
  silence and isn't sensitive enough to the 300ms-1s "thinking pause"
  range these features care about.
- Speech rate and filler-word detection both need to tell Chinese
  characters apart from English word tokens; `_CJK_CHAR_PATTERN` (the
  Unicode CJK Unified Ideographs block, matching the doc's "一-鿿" range)
  is the shared primitive for that.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import soundfile as sf

from backend.speech.transcribe import TranscriptionResult, Word

logger = logging.getLogger(__name__)

_CJK_CHAR_PATTERN = re.compile(r"[一-鿿]")


def _is_cjk_token(token: str) -> bool:
    return bool(token) and all(_CJK_CHAR_PATTERN.match(ch) is not None for ch in token)


# ---------------------------------------------------------------------------
# 2.2 Speech rate: CPM/WPM main indicator + cross-language SRI
# ---------------------------------------------------------------------------

_ENGLISH_SYLLABLES_PER_WORD = 1.3  # spec 2.2's empirical constant for the SRI formula

RateMetric = Literal["cpm", "wpm"]
RateLabel = Literal["slow", "normal", "fast"]

# Empirical starting points from spec section 2.2's reference table -- spec
# section 4 flags these as needing recalibration against real candidate
# recordings once available; see docs/decision_log.md.
_RATE_BANDS: dict[RateMetric, tuple[float, float]] = {
    "cpm": (180.0, 260.0),  # < slow_max is slow, > fast_min is fast, between is normal
    "wpm": (100.0, 150.0),
}


@dataclass
class SpeechRateResult:
    chinese_char_count: int
    english_word_count: int
    duration_seconds: float  # word[-1].end - word[0].start, deliberately includes internal pauses (spec 2.2)
    primary_metric: Optional[RateMetric]  # None only when the answer has no countable chinese chars or english words
    primary_value: float  # value in `primary_metric`'s unit; 0.0 when primary_metric is None
    syllables_per_minute: float  # cross-language SRI (spec 2.2) -- internal thresholding use only, not for display


def _count_chinese_chars(text: str) -> int:
    return len(_CJK_CHAR_PATTERN.findall(text))


def _count_english_words(text: str) -> int:
    """Whitespace-split tokens that contain no CJK characters and at least one alnum char (spec 2.2)."""
    return sum(1 for token in text.split() if not _CJK_CHAR_PATTERN.search(token) and re.search(r"[A-Za-z0-9]", token))


def compute_speech_rate(text: str, words: list[Word]) -> Optional[SpeechRateResult]:
    """
    None when there are no words at all (nothing to time) or the timed span
    collapses to zero duration -- callers should treat that as "no speech
    rate data for this answer" rather than a fabricated 0 WPM/CPM.
    """
    if not words:
        return None
    duration_seconds = words[-1].end - words[0].start
    if duration_seconds <= 0:
        return None

    chinese_chars = _count_chinese_chars(text)
    english_words = _count_english_words(text)
    minutes = duration_seconds / 60.0
    sri = (chinese_chars * 1.0 + english_words * _ENGLISH_SYLLABLES_PER_WORD) / minutes

    if chinese_chars == 0 and english_words == 0:
        primary_metric: Optional[RateMetric] = None
        primary_value = 0.0
    elif english_words == 0:
        primary_metric, primary_value = "cpm", chinese_chars / minutes
    elif chinese_chars == 0:
        primary_metric, primary_value = "wpm", english_words / minutes
    else:
        # Mixed-language answer: spec 2.2 only defines a display metric for
        # "pure" Chinese/English answers and reserves SRI for internal use.
        # For a mixed answer, show whichever language contributes more as a
        # judgment call the spec leaves open -- SRI is still returned for
        # internal thresholding either way.
        if chinese_chars >= english_words:
            primary_metric, primary_value = "cpm", chinese_chars / minutes
        else:
            primary_metric, primary_value = "wpm", english_words / minutes

    return SpeechRateResult(
        chinese_char_count=chinese_chars,
        english_word_count=english_words,
        duration_seconds=duration_seconds,
        primary_metric=primary_metric,
        primary_value=primary_value,
        syllables_per_minute=sri,
    )


def classify_speech_rate(metric: RateMetric, value: float) -> RateLabel:
    """Bucket a CPM/WPM value into slow/normal/fast per the (unvalidated) reference bands above."""
    slow_max, fast_min = _RATE_BANDS[metric]
    if value < slow_max:
        return "slow"
    if value > fast_min:
        return "fast"
    return "normal"


# ---------------------------------------------------------------------------
# 2.3 Pause features, from word-level timestamps only
# ---------------------------------------------------------------------------

PAUSE_THRESHOLD_SECONDS = 0.3


@dataclass
class PauseFeatures:
    count: int
    total_seconds: float
    longest_seconds: float
    average_seconds: float


def compute_pause_features(words: list[Word]) -> PauseFeatures:
    gaps = [nxt.start - prev.end for prev, nxt in zip(words, words[1:]) if nxt.start - prev.end > PAUSE_THRESHOLD_SECONDS]
    if not gaps:
        return PauseFeatures(count=0, total_seconds=0.0, longest_seconds=0.0, average_seconds=0.0)
    return PauseFeatures(
        count=len(gaps),
        total_seconds=sum(gaps),
        longest_seconds=max(gaps),
        average_seconds=sum(gaps) / len(gaps),
    )


# ---------------------------------------------------------------------------
# 2.4 Filler-word detection
# ---------------------------------------------------------------------------

# Longer phrases are tried first within each list (see _match_phrases) so
# e.g. "就是说"/"umm" win over the shorter "就是"/"um" they contain.
_ZH_STRONG_FILLERS = ["嗯", "啊", "呃", "诶", "哦"]
_ZH_WEAK_FILLERS = ["这个", "那个", "就是说", "就是", "然后", "其实", "怎么说呢", "你知道吧", "对吧", "是吧", "这样子"]
_EN_STRONG_FILLERS = ["umm", "uhh", "um", "uh", "erm", "er"]
_EN_WEAK_FILLERS = ["you know", "i mean", "sort of", "kind of", "basically", "actually", "like", "right", "well", "so"]

_ISOLATING_PUNCTUATION = set("，,。.!?！？;；、")


@dataclass
class FillerFeatures:
    counts: dict[str, int] = field(default_factory=dict)  # phrase -> count, counted occurrences only
    strong_count: int = 0
    weak_count: int = 0


def _build_searchable_text(words: list[Word]) -> tuple[str, list[int]]:
    """
    Reconstruct one searchable string from `words` plus a per-character
    "which word index produced this character" map.

    faster-whisper's word-level granularity differs by script: English
    tokens come out roughly as whitespace-delimited words, while Chinese
    (having no spaces) tends to come out closer to one character per
    "word". Consecutive CJK tokens are therefore joined with no separator
    (so multi-character phrases like "这个"/"就是说" reassemble correctly),
    while everything else gets a single space, matching how the phrase
    lists above are written and letting the same substring/word-boundary
    matching logic handle both scripts.
    """
    chars: list[str] = []
    owners: list[int] = []
    prev_is_cjk: Optional[bool] = None
    for i, w in enumerate(words):
        token = w.text.strip()
        if not token:
            continue
        is_cjk = _is_cjk_token(token)
        if chars and not (prev_is_cjk and is_cjk):
            chars.append(" ")
            owners.append(i)
        chars.extend(token)
        owners.extend([i] * len(token))
        prev_is_cjk = is_cjk
    return "".join(chars), owners


def _match_phrases(
    full_text: str,
    owners: list[int],
    phrases: list[str],
    *,
    case_insensitive: bool,
    whole_word: bool,
    consumed: list[bool],
) -> list[tuple[str, int, int]]:
    """
    Find non-overlapping occurrences of `phrases` in `full_text`, longest
    phrase first, marking matched character ranges in `consumed` so a
    shorter phrase can't double-count a span already claimed by a longer
    one (e.g. "就是" inside an already-matched "就是说").

    Returns (phrase, start_word_index, end_word_index) tuples, the word
    index range the match spans -- needed by weak-filler occurrences to
    look up their surrounding timing/text context.
    """
    results: list[tuple[str, int, int]] = []
    for phrase in sorted(phrases, key=len, reverse=True):
        pattern = re.escape(phrase)
        if whole_word:
            pattern = r"\b" + pattern + r"\b"
        flags = re.IGNORECASE if case_insensitive else 0
        for m in re.finditer(pattern, full_text, flags):
            if any(consumed[m.start() : m.end()]):
                continue
            for idx in range(m.start(), m.end()):
                consumed[idx] = True
            results.append((phrase, owners[m.start()], owners[m.end() - 1]))
    results.sort(key=lambda r: r[1])
    return results


def _has_isolating_context(start_word_index: int, end_word_index: int, words: list[Word]) -> bool:
    """
    True when a weak-filler candidate is preceded/followed by a pause
    (>PAUSE_THRESHOLD_SECONDS) or by punctuation -- the signal spec section
    2.4 uses to tell a real filler ("这个... 那我们聊聊别的") apart from
    ordinary usage ("这个方案就是我做的", spoken with no surrounding gap).

    A word with no neighbor on one side (start/end of the answer) has no
    gap signal to check on that side -- this deliberately does *not* treat
    "no neighbor" as "isolated", since e.g. a sentence-initial "这个" used
    normally ("这个方案就是我做的...") is just as common as a hesitant one,
    and a genuine hesitation at the very start would still show up as a
    gap *after* the word (silence while the speaker collects their
    thought) rather than needing a boundary special-case.
    """
    gap_before = start_word_index > 0 and (
        words[start_word_index].start - words[start_word_index - 1].end > PAUSE_THRESHOLD_SECONDS
    )
    gap_after = end_word_index < len(words) - 1 and (
        words[end_word_index + 1].start - words[end_word_index].end > PAUSE_THRESHOLD_SECONDS
    )
    punct_before = start_word_index > 0 and words[start_word_index - 1].text.strip()[-1:] in _ISOLATING_PUNCTUATION
    punct_after = end_word_index < len(words) - 1 and words[end_word_index + 1].text.strip()[:1] in _ISOLATING_PUNCTUATION
    return gap_before or gap_after or punct_before or punct_after


def compute_filler_features(words: list[Word]) -> FillerFeatures:
    """
    Strong fillers (嗯/啊/um/uh/...) count on every occurrence. Weak fillers
    (这个/然后/like/actually/...) only count when `_has_isolating_context`
    confirms they're being used as a filler rather than with their normal
    semantic meaning (spec section 2.4).
    """
    if not words:
        return FillerFeatures()

    full_text, owners = _build_searchable_text(words)
    consumed = [False] * len(full_text)
    features = FillerFeatures()

    strong_matches = _match_phrases(
        full_text, owners, _ZH_STRONG_FILLERS, case_insensitive=False, whole_word=False, consumed=consumed
    ) + _match_phrases(full_text, owners, _EN_STRONG_FILLERS, case_insensitive=True, whole_word=True, consumed=consumed)
    for phrase, _start, _end in strong_matches:
        features.counts[phrase] = features.counts.get(phrase, 0) + 1
        features.strong_count += 1

    weak_matches = _match_phrases(
        full_text, owners, _ZH_WEAK_FILLERS, case_insensitive=False, whole_word=False, consumed=consumed
    ) + _match_phrases(full_text, owners, _EN_WEAK_FILLERS, case_insensitive=True, whole_word=True, consumed=consumed)
    for phrase, start_i, end_i in weak_matches:
        if _has_isolating_context(start_i, end_i, words):
            features.counts[phrase] = features.counts.get(phrase, 0) + 1
            features.weak_count += 1

    return features


# ---------------------------------------------------------------------------
# 2.5 Volume features, from the raw PCM waveform (not from ASR output)
# ---------------------------------------------------------------------------

_VOLUME_WINDOW_SECONDS = 0.2  # spec 2.5's suggested fixed window
_BASELINE_SECONDS = 3.0  # spec 2.5 says "the first few seconds" without pinning a number; 3s is this module's choice
_SILENCE_FLOOR_RMS = 1e-10  # avoids log10(0) for a fully-silent window


@dataclass
class VolumeFeatures:
    volume_std_dbfs: float  # spec 2.5's "音量标准差" -- overall loudness instability
    baseline_dbfs: float  # mean dBFS of the first ~_BASELINE_SECONDS
    relative_deviation_dbfs: float  # mean(whole answer) - baseline; negative = quieter than the opening baseline


def _load_mono_samples(audio_path: str) -> Optional[tuple[np.ndarray, int]]:
    try:
        samples, sample_rate = sf.read(audio_path, dtype="float32", always_2d=False)
    except Exception as exc:  # noqa: BLE001 -- any unreadable/corrupt file just means "no volume data"
        logger.warning("Failed to read audio for volume analysis (%s): %r", audio_path, exc)
        return None
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples, sample_rate


def _compute_dbfs_curve(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    window_size = max(1, int(_VOLUME_WINDOW_SECONDS * sample_rate))
    n_windows = len(samples) // window_size
    if n_windows == 0:
        return np.array([])
    trimmed = samples[: n_windows * window_size].reshape(n_windows, window_size).astype(np.float64)
    rms = np.sqrt(np.mean(trimmed**2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, _SILENCE_FLOOR_RMS))


def compute_volume_features(audio_path: str) -> Optional[VolumeFeatures]:
    """None when the audio file can't be read or is too short for even one analysis window."""
    loaded = _load_mono_samples(audio_path)
    if loaded is None:
        return None
    samples, sample_rate = loaded
    curve = _compute_dbfs_curve(samples, sample_rate)
    if curve.size == 0:
        return None

    n_baseline_windows = max(1, int(_BASELINE_SECONDS / _VOLUME_WINDOW_SECONDS))
    baseline_dbfs = float(np.mean(curve[: min(n_baseline_windows, curve.size)]))
    return VolumeFeatures(
        volume_std_dbfs=float(np.std(curve)),
        baseline_dbfs=baseline_dbfs,
        relative_deviation_dbfs=float(np.mean(curve)) - baseline_dbfs,
    )


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------


@dataclass
class SpeechAnalysis:
    speech_rate: Optional[SpeechRateResult]
    pauses: PauseFeatures
    fillers: FillerFeatures
    volume: Optional[VolumeFeatures]


def analyze_speech(transcription: TranscriptionResult, audio_path: str) -> SpeechAnalysis:
    """
    Run all four feature extractors for one answer's turn: speech rate and
    filler words from the transcription text, pauses from its word
    timestamps, and volume from the raw audio file directly (spec 2.1's
    four parallel side-channel features).
    """
    return SpeechAnalysis(
        speech_rate=compute_speech_rate(transcription.text, transcription.words),
        pauses=compute_pause_features(transcription.words),
        fillers=compute_filler_features(transcription.words),
        volume=compute_volume_features(audio_path),
    )
