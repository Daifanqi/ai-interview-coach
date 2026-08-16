"""
Real-recording calibration for backend/speech/features.py's speech-rate
bands (_RATE_BANDS) and pause threshold (PAUSE_THRESHOLD_SECONDS).

Background: docs/decision_log.md decision 20 (item 4) flagged both as
"empirical starting points... need to be recalibrated against real
candidate recordings once available" -- the CPM/WPM slow/normal/fast bands
and the 300ms pause threshold in features.py were never anything more than
a reasoned guess. Decision 45 (week 16) schedules this as the week's other
accuracy-debt item, alongside specificity dimension calibration
(scripts/calibrate_specificity.py) -- this script is the recording side of
that: run faster-whisper + features.py over a handful of real candidate
answers and see how their measured CPM/WPM/pause numbers compare to the
current bands, rather than continuing to run on an unvalidated guess.

This is NOT a formal grid search the way calibrate_specificity.py is --
there is no human "this pace felt slow/normal/fast" label attached to these
recordings, just the recordings themselves. So this script reports the
measured distribution (with percentiles) and prints a suggested band
update, but leaves the actual judgment call -- does a recording that felt
conversationally normal actually land in the "normal" bucket under the
current bands? -- to a human listening to the audio and reading the
numbers side by side, same as decision 20 always intended.

Usage:
    python scripts/calibrate_speech_features.py path/to/recordings/

Expects a directory of audio files (any format soundfile/faster-whisper
can read -- wav/mp3/m4a/etc.), ideally a mix of paces (a deliberately
slow/careful answer, a normal conversational one, a fast/rambling one) so
the reported spread is meaningful rather than a single data point. Prints
per-file measurements and a suggested band update to stdout; does NOT
modify backend/speech/features.py -- apply the suggested constants there by
hand after reviewing them against how each recording actually sounded.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.speech.features import (  # noqa: E402
    PAUSE_THRESHOLD_SECONDS,
    _RATE_BANDS,
    classify_speech_rate,
    compute_pause_features,
    compute_speech_rate,
)
from backend.speech.transcribe import transcribe_audio  # noqa: E402

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}


def _percentile(values: list[float], pct: float) -> float:
    """Simple linear-interpolation percentile, no numpy/scipy dependency needed for this script."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100.0)
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {Path(__file__).name} path/to/recordings/")
        sys.exit(1)

    recordings_dir = Path(sys.argv[1])
    if not recordings_dir.is_dir():
        print(f"Not a directory: {recordings_dir}")
        sys.exit(1)

    audio_files = sorted(p for p in recordings_dir.iterdir() if p.suffix.lower() in _AUDIO_EXTENSIONS)
    if not audio_files:
        print(f"No audio files found in {recordings_dir} (looked for {sorted(_AUDIO_EXTENSIONS)})")
        sys.exit(1)

    print(f"Found {len(audio_files)} recording(s). Transcribing (first call also loads the faster-whisper model)...\n")

    cpm_values: list[float] = []
    wpm_values: list[float] = []
    pause_gap_seconds: list[float] = []  # every individual gap > PAUSE_THRESHOLD_SECONDS, across all files

    print("| File | Duration (s) | Metric | Value | Current label | Pause count | Longest pause (s) |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for audio_path in audio_files:
        transcription = transcribe_audio(str(audio_path))
        rate = compute_speech_rate(transcription.text, transcription.words)
        pauses = compute_pause_features(transcription.words)

        if pauses.longest_seconds > 0:
            # Reconstruct the individual gap list the same way compute_pause_features() does
            # internally, since it only returns aggregates (count/total/longest/average), not
            # the raw list -- needed here to build a percentile distribution across all files.
            words = transcription.words
            gaps = [nxt.start - prev.end for prev, nxt in zip(words, words[1:]) if nxt.start - prev.end > PAUSE_THRESHOLD_SECONDS]
            pause_gap_seconds.extend(gaps)

        if rate is None:
            print(f"| {audio_path.name} | - | (no speech detected) | - | - | {pauses.count} | {pauses.longest_seconds:.2f} |")
            continue

        label = classify_speech_rate(rate.primary_metric, rate.primary_value)
        if rate.primary_metric == "cpm":
            cpm_values.append(rate.primary_value)
        else:
            wpm_values.append(rate.primary_value)

        print(
            f"| {audio_path.name} | {rate.duration_seconds:.1f} | {rate.primary_metric} | "
            f"{rate.primary_value:.0f} | {label} | {pauses.count} | {pauses.longest_seconds:.2f} |"
        )

    # Reads the live constants from features.py rather than hardcoding literal numbers here --
    # an earlier version of this script printed a hardcoded "cpm=(180, 260)" string that silently
    # went stale the moment decision #46 recalibrated the real constant to (230, 330), even though
    # classify_speech_rate() itself (called above) was already using the correct live value the
    # whole time. Caught on the real second run of this script after that recalibration.
    print(
        f"\nCurrent bands: cpm={_RATE_BANDS['cpm']}, wpm={_RATE_BANDS['wpm']}, "
        f"pause_threshold={PAUSE_THRESHOLD_SECONDS}s\n"
    )

    for metric_name, values in (("cpm", cpm_values), ("wpm", wpm_values)):
        if len(values) < 2:
            print(f"{metric_name}: only {len(values)} recording(s) with this metric -- not enough spread to suggest a band.")
            continue
        p25, p50, p75 = _percentile(values, 25), _percentile(values, 50), _percentile(values, 75)
        print(
            f"{metric_name}: n={len(values)}  min={min(values):.0f}  p25={p25:.0f}  "
            f"median={p50:.0f}  p75={p75:.0f}  max={max(values):.0f}"
        )
        print(
            f"  Naive suggestion (p25/p75 as the new slow_max/fast_min, i.e. treat the middle 50% "
            f"of these recordings as 'normal'): ({p25:.0f}, {p75:.0f}) -- sanity-check against how each "
            f"recording actually sounded before applying; a small sample's p25/p75 can be noisy.\n"
        )

    if pause_gap_seconds:
        p50_pause, p90_pause = _percentile(pause_gap_seconds, 50), _percentile(pause_gap_seconds, 90)
        print(
            f"Pauses above the current {PAUSE_THRESHOLD_SECONDS}s threshold: n={len(pause_gap_seconds)}  "
            f"median={p50_pause:.2f}s  p90={p90_pause:.2f}s -- if most real thinking-pauses run "
            f"noticeably longer than {PAUSE_THRESHOLD_SECONDS}s, the threshold may be catching normal "
            f"micro-hesitations rather than the deliberate pauses decision 20 cared about."
        )


if __name__ == "__main__":
    main()
