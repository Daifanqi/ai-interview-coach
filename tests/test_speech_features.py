"""
Unit tests for backend/speech/features.py's pure feature-extraction
functions (week 16, decision #45's test-coverage debt item -- decision #39
flagged the week 9-11 speech modules as having zero test coverage).

Only the parts of features.py that operate on synthetic Word lists are
covered here (speech rate, pause detection, filler-word detection) -- these
need no real audio file and no faster-whisper model, just hand-built
backend.speech.transcribe.Word objects with chosen timestamps/text, the
same way a real transcribe_audio() call's word list would look.
compute_volume_features() (raw-waveform analysis, needs a real audio file
via soundfile) is intentionally NOT covered here; it stays validated by
manual real-recording walkthroughs the way TTS/ASR always have been in this
project, since fabricating a synthetic WAV file to unit-test against isn't
worth the complexity for one function.
"""
from __future__ import annotations

from backend.speech.features import (
    PAUSE_THRESHOLD_SECONDS,
    classify_speech_rate,
    compute_filler_features,
    compute_pause_features,
    compute_speech_rate,
)
from backend.speech.transcribe import Word


def _word(text: str, start: float, end: float, probability: float = 0.95) -> Word:
    return Word(text=text, start=start, end=end, probability=probability)


# ---------------------------------------------------------------------------
# compute_speech_rate / classify_speech_rate
# ---------------------------------------------------------------------------


def test_compute_speech_rate_returns_none_for_no_words():
    assert compute_speech_rate("", []) is None


def test_compute_speech_rate_returns_none_for_zero_duration():
    # Two words with identical start/end -- degenerate zero-duration span.
    words = [_word("嗯", 1.0, 1.0), _word("啊", 1.0, 1.0)]
    assert compute_speech_rate("嗯啊", words) is None


def test_compute_speech_rate_picks_cpm_for_pure_chinese_answer():
    text = "这是一段测试文本内容呀"
    words = [_word(ch, i * 0.5, i * 0.5 + 0.4) for i, ch in enumerate(text)]
    result = compute_speech_rate(text, words)
    assert result is not None
    assert result.primary_metric == "cpm"
    assert result.chinese_char_count == len(text)
    assert result.english_word_count == 0


def test_compute_speech_rate_picks_wpm_for_pure_english_answer():
    text = "this is a short test answer about the project"
    words = [_word(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(text.split())]
    result = compute_speech_rate(text, words)
    assert result is not None
    assert result.primary_metric == "wpm"
    assert result.english_word_count == len(text.split())
    assert result.chinese_char_count == 0


def test_compute_speech_rate_mixed_language_picks_majority_metric():
    # More Chinese characters than English words -> cpm, per the module's own tie-break rule.
    # Note the spaces around "test": _count_english_words() splits `text` on whitespace, so an
    # English token needs an actual space boundary to be counted separately from adjacent CJK
    # text -- "这是一个test案例" with no spaces would count zero English words, since
    # text.split() can't isolate "test" without whitespace to split on.
    text = "这是一个 test 案例"
    words = [_word("这是一个", 0.0, 1.0), _word("test", 1.0, 1.5), _word("案例", 1.5, 2.0)]
    result = compute_speech_rate(text, words)
    assert result is not None
    assert result.primary_metric == "cpm"
    assert result.chinese_char_count == 6
    assert result.english_word_count == 1


def test_classify_speech_rate_buckets_slow_normal_fast():
    assert classify_speech_rate("cpm", 100.0) == "slow"  # below 180
    assert classify_speech_rate("cpm", 220.0) == "normal"  # between 180-260
    assert classify_speech_rate("cpm", 300.0) == "fast"  # above 260
    assert classify_speech_rate("wpm", 80.0) == "slow"
    assert classify_speech_rate("wpm", 120.0) == "normal"
    assert classify_speech_rate("wpm", 180.0) == "fast"


# ---------------------------------------------------------------------------
# compute_pause_features
# ---------------------------------------------------------------------------


def test_compute_pause_features_no_gaps_returns_zeroed_result():
    words = [_word("a", 0.0, 0.5), _word("b", 0.5, 1.0), _word("c", 1.0, 1.5)]
    result = compute_pause_features(words)
    assert result.count == 0
    assert result.total_seconds == 0.0
    assert result.longest_seconds == 0.0
    assert result.average_seconds == 0.0


def test_compute_pause_features_detects_gaps_above_threshold_only():
    # Gap 1: 0.5 -> 1.0 is exactly at threshold (not counted, strictly-greater-than check).
    # Gap 2: 1.5 -> 2.5 is a real 1.0s pause (counted).
    words = [
        _word("a", 0.0, 0.5),
        _word("b", 0.5 + PAUSE_THRESHOLD_SECONDS, 1.5),
        _word("c", 2.5, 3.0),
    ]
    result = compute_pause_features(words)
    assert result.count == 1
    assert result.longest_seconds == 1.0
    assert result.total_seconds == 1.0
    assert result.average_seconds == 1.0


def test_compute_pause_features_reports_longest_and_average_across_multiple_gaps():
    words = [
        _word("a", 0.0, 0.5),
        _word("b", 1.0, 1.5),  # gap = 0.5
        _word("c", 3.5, 4.0),  # gap = 2.0
    ]
    result = compute_pause_features(words)
    assert result.count == 2
    assert result.longest_seconds == 2.0
    assert result.total_seconds == 2.5
    assert result.average_seconds == 1.25


# ---------------------------------------------------------------------------
# compute_filler_features
# ---------------------------------------------------------------------------


def test_compute_filler_features_counts_strong_fillers_unconditionally():
    # Strong Chinese fillers count on every occurrence, no isolating-context check needed.
    words = [_word("嗯", 0.0, 0.3), _word("这个", 0.3, 0.6), _word("方案", 0.6, 1.0)]
    result = compute_filler_features(words)
    assert result.strong_count == 1
    assert result.counts.get("嗯") == 1


def test_compute_filler_features_weak_filler_counts_only_with_isolating_context():
    # "这个" immediately followed by a real pause (> PAUSE_THRESHOLD_SECONDS) reads as hesitation.
    words_hesitant = [
        _word("这个", 0.0, 0.4),
        _word("嗯", 0.4 + PAUSE_THRESHOLD_SECONDS + 0.1, 1.0),
    ]
    hesitant_result = compute_filler_features(words_hesitant)
    assert hesitant_result.weak_count == 1

    # "这个" used normally, immediately followed by more content with no gap and no punctuation --
    # not a filler.
    words_normal = [_word("这个", 0.0, 0.4), _word("方案", 0.4, 0.8), _word("可行", 0.8, 1.2)]
    normal_result = compute_filler_features(words_normal)
    assert normal_result.weak_count == 0


def test_compute_filler_features_empty_words_returns_zeroed_result():
    result = compute_filler_features([])
    assert result.strong_count == 0
    assert result.weak_count == 0
    assert result.counts == {}


def test_compute_filler_features_no_double_counts_overlapping_phrases():
    # "就是说" (weak filler, 3 chars) fully contains "就是" (weak filler, 2 chars) -- the longer
    # phrase should win and the shorter one must not also fire on the same span.
    words = [
        _word("就是说", 0.0, 0.5),
        _word("嗯", 0.5 + PAUSE_THRESHOLD_SECONDS + 0.1, 1.0),
    ]
    result = compute_filler_features(words)
    assert result.counts.get("就是说") == 1
    assert "就是" not in result.counts
