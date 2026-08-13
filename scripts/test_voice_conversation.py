"""
Interactive CLI for exercising the full voice-in/voice-out pipeline.

This is scripts/test_conversation_live.py's loop with text I/O swapped for
real audio: persona/language selection is reused directly from that script
(rather than duplicated) since the picking logic itself hasn't changed --
only how answers get in and replies get out. On top of that it wires in
the three speech modules built for the Week 4 tech spec
(docs/week4_tech_spec.md):

  - backend/speech/tts.py synthesizes and plays every interviewer line
    (opening line, main questions, follow-ups) via its simplified one-shot
    path -- see tts.py's own docstring on why the sentence-chunked
    streaming path isn't needed for single-utterance interview turns like
    these, only for long-form summaries/feedback.
  - Recording is press-Enter-to-start / press-Enter-to-stop against the
    default microphone, rather than a fixed duration, so an answer isn't
    truncated or padded with dead air just because it didn't match a
    preset length.
  - backend/speech/transcribe.py turns the recording back into text, which
    then goes through the exact same engine.submit_answer() pipeline as
    the text-only test script (dialogue reply + scoring_judge.judge_answer()
    follow-up scoring).

Every turn is also printed as plain text (transcribed answer, interviewer
reply, and the same follow-up debug line test_conversation_live.py prints)
so the voice and text versions of the conversation can be compared side by
side while debugging.

Run it with:

    python scripts/test_voice_conversation.py

Needs a working microphone and speakers, a GROQ_API_KEY (see
backend/conversation/llm_client.py), and enough disk space/network for
faster-whisper's model and Piper's voice files to download on first use.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

# Allow running this script directly (`python scripts/test_voice_conversation.py`)
# without needing the project installed as a package -- Python only puts this
# script's own directory (scripts/) on sys.path by default, not the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Reused as-is from the text-only test script -- same persona/language menus,
# same "is GROQ_API_KEY configured" check, same follow-up debug-line
# formatting. Both scripts live directly in scripts/, so this import works
# without any package/__init__.py machinery (Python puts a run script's own
# directory on sys.path automatically).
from test_conversation_live import (  # noqa: E402
    _EXIT_COMMANDS,
    _LANGUAGE_LABELS,
    _LANGUAGE_MENU,
    _PERSONA_LABELS,
    _PERSONA_MENU,
    _check_api_key_configured,
    _print_debug_line,
    _prompt_choice,
)

from backend.conversation import engine  # noqa: E402
from backend.conversation.prompts import Language, Persona  # noqa: E402
from backend.speech import transcribe, tts  # noqa: E402

# faster-whisper works fine at other rates too, but 16kHz is its native
# training rate and keeps the recorded file small -- no reason to record
# any higher just to immediately downsample it internally.
RECORDING_SAMPLE_RATE = 16000
RECORDING_CHANNELS = 1


def record_until_enter(sample_rate: int = RECORDING_SAMPLE_RATE) -> np.ndarray:
    """
    Record from the default microphone from right now until the next
    Enter keypress. Returns mono float32 samples; an empty array if
    nothing was captured (e.g. Enter was hit immediately).
    """
    frames: list[np.ndarray] = []

    def _on_audio_block(indata: np.ndarray, frame_count: int, time_info, status: sd.CallbackFlags) -> None:
        if status:
            print(f"[recording warning] {status}", file=sys.stderr)
        frames.append(indata.copy())

    print("Recording... press Enter to stop.")
    with sd.InputStream(samplerate=sample_rate, channels=RECORDING_CHANNELS, dtype="float32", callback=_on_audio_block):
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    print("Recording stopped.")

    if not frames:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(frames, axis=0).reshape(-1)


def _write_temp_wav(samples: np.ndarray, sample_rate: int) -> str:
    """Write `samples` to a throw-away WAV file -- transcribe_audio() needs a file path, not raw samples."""
    tmp_file = tempfile.NamedTemporaryFile(prefix="voice_test_answer_", suffix=".wav", delete=False)
    tmp_file.close()
    sf.write(tmp_file.name, samples, sample_rate)
    return tmp_file.name


def play_wav_bytes(wav_bytes: bytes) -> None:
    """Play back an in-memory WAV (as produced by tts.py) through the default output device, blocking until done."""
    samples, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    sd.play(samples, sample_rate)
    sd.wait()


def speak(text: str, persona: Persona, language: Language) -> None:
    """
    Synthesize `text` and play it back.

    Every line spoken in this script -- opening line, main questions,
    follow-ups -- is a single short interview utterance, exactly the case
    tts.py's own docstring earmarks for its simplified one-shot path
    (synthesize_short_reply) rather than the sentence-chunked streaming
    path, which only pays off for long-form text like a full session summary.
    """
    print("[synthesizing voice reply...]")
    audio = tts.synthesize_short_reply(text, persona, language)
    play_wav_bytes(audio)


def record_and_transcribe_answer(language: Language) -> str:
    """One press-Enter-to-start/stop recording, transcribed to text via faster-whisper."""
    samples = record_until_enter()
    if samples.size == 0:
        return ""

    wav_path = _write_temp_wav(samples, RECORDING_SAMPLE_RATE)
    try:
        print("[transcribing...]")
        result = transcribe.transcribe_audio(wav_path, language=language)
    finally:
        os.unlink(wav_path)
    return result.text


def main() -> None:
    print("=== AI Interview Coach -- voice conversation test ===")
    if not _check_api_key_configured():
        print(
            "\nWARNING: GROQ_API_KEY is not set (checked .env at the project "
            "root and the environment). The interviewer will only be able to "
            "return its friendly fallback message until you set one."
        )

    persona = _prompt_choice("Choose a persona:", _PERSONA_MENU, _PERSONA_LABELS)
    language = _prompt_choice("Choose a language:", _LANGUAGE_MENU, _LANGUAGE_LABELS)

    opening_line, session = engine.start_interview(persona, language)
    print(f"\n--- Interview starting ({_PERSONA_LABELS[persona]}, {_LANGUAGE_LABELS[language]}) ---")
    print(f"\nInterviewer: {opening_line}")
    speak(opening_line, persona, language)

    print(f"\n(Press Enter to record a spoken answer each turn. Type one of {sorted(_EXIT_COMMANDS)} to quit.)")

    while True:
        try:
            command = input("\n[Enter] to record your answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEnding session.")
            break
        if command.lower() in _EXIT_COMMANDS:
            print("Ending session.")
            break

        answer_text = record_and_transcribe_answer(language)
        print(f"You (transcribed): {answer_text!r}")
        if not answer_text.strip():
            print("Nothing was transcribed -- try again.")
            continue

        result = engine.submit_answer(answer_text, session)
        print(f"\nInterviewer: {result.reply}")
        _print_debug_line(result)
        speak(result.reply, persona, language)


if __name__ == "__main__":
    main()
