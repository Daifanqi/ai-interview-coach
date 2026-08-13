"""
Interactive CLI for exercising the real dialogue engine end to end.

Lets you pick a persona and language, shows the opening line, then loops:
you type an answer, the script prints the interviewer's reply plus a debug
line showing what the engine internally decided (extreme-case pattern,
follow-up round, action). This is meant purely for manually testing the
engine against the live Groq API before the frontend has a conversation
page to drive it -- run it with:

    python scripts/test_conversation_live.py

Requires a GROQ_API_KEY in a .env file at the project root (see
backend/conversation/llm_client.py) or in the environment already; without
one, call_llm() still works, it just always returns the friendly fallback
message, so the state-machine wiring can still be sanity-checked offline.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running this script directly (`python scripts/test_conversation_live.py`)
# without needing the project installed as a package -- Python only puts this
# script's own directory (scripts/) on sys.path by default, not the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

from backend.conversation import engine  # noqa: E402
from backend.conversation.prompts import Language, Persona  # noqa: E402

_PERSONA_MENU: list[tuple[str, Persona]] = [
    ("1", Persona.FRIENDLY),
    ("2", Persona.TECHNICAL),
    ("3", Persona.STRICT),
]
_PERSONA_LABELS: dict[Persona, str] = {
    Persona.FRIENDLY: "Friendly (HR screening / 亲和型)",
    Persona.TECHNICAL: "Technical (技术挖掘型)",
    Persona.STRICT: "Strict (final round bar raiser / 严格型)",
}

_LANGUAGE_MENU: list[tuple[str, Language]] = [
    ("1", "zh"),
    ("2", "en"),
]
_LANGUAGE_LABELS: dict[Language, str] = {
    "zh": "Chinese (中文)",
    "en": "English",
}

_EXIT_COMMANDS = {"exit", "quit", "q", "退出"}


def _prompt_choice(menu_title: str, menu: list[tuple[str, object]], labels: dict) -> object:
    print(f"\n{menu_title}")
    for key, value in menu:
        print(f"  [{key}] {labels[value]}")
    valid_keys = {key for key, _ in menu}
    while True:
        choice = input("> ").strip()
        for key, value in menu:
            if choice == key:
                return value
        print(f"Please enter one of: {', '.join(sorted(valid_keys))}")


def _check_api_key_configured() -> bool:
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
    return bool(os.environ.get("GROQ_API_KEY"))


def _print_debug_line(result: engine.TurnResult) -> None:
    if result.pattern is None:
        print("[debug] priming turn (no follow-up state applies yet)")
        return
    print(
        f"[debug] pattern={result.pattern.value} action={result.action.value} "
        f"strategy={result.strategy.value}"
    )


def main() -> None:
    print("=== AI Interview Coach -- live conversation test ===")
    if not _check_api_key_configured():
        print(
            "\nWARNING: GROQ_API_KEY is not set (checked .env at the project "
            "root and the environment). The interviewer will only be able to "
            "return its friendly fallback message until you set one -- you "
            "can still use this script to sanity-check the follow-up state "
            "machine wiring."
        )

    persona = _prompt_choice("Choose a persona:", _PERSONA_MENU, _PERSONA_LABELS)
    language = _prompt_choice("Choose a language:", _LANGUAGE_MENU, _LANGUAGE_LABELS)

    opening_line, session = engine.start_interview(persona, language)
    print(f"\n--- Interview starting ({_PERSONA_LABELS[persona]}, {_LANGUAGE_LABELS[language]}) ---")
    print(f"\nInterviewer: {opening_line}")
    print(f"\n(Type your answers below. Type one of {sorted(_EXIT_COMMANDS)} to quit.)")

    while True:
        try:
            answer = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEnding session.")
            break

        if not answer:
            continue
        if answer.lower() in _EXIT_COMMANDS:
            print("Ending session.")
            break

        result = engine.submit_answer(answer, session)
        print(f"\nInterviewer: {result.reply}")
        _print_debug_line(result)


if __name__ == "__main__":
    main()
