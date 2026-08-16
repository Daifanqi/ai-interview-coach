"""
AI Interview System - Onboarding Flow (Week 8 UI overhaul)

Three-stage flow driven by st.session_state["onboarding_stage"]
("welcome" -> "triage" -> "result"), replacing the earlier single-page
layout that inferred which section to show from whether `scenario` was
None or not. Backend logic (match_scenario(), session persistence) is
unchanged -- this file only changes *when* that logic runs and *which*
block renders; see docs/decision_log.md decisions #16 and #17 (item 1).

Stage 1 (welcome): app intro + language picker + font style picker, both
moved out of the sidebar per decision #16.
Stage 2 (triage): the same 3-question backend/diagnosis/questionnaire.py
QUESTIONNAIRE schema, now asked one question at a time through st.dialog
modals instead of one static st.form (decision #17 item 1).
Stage 3 (result): the same difficulty badge / persona tag result
rendering as before, moved onto its own page for more visual "reveal"
weight.

All user-facing text is routed through strings.t(key) -- see
frontend/strings.py for the bilingual string table and language resolution
order (manual override > browser Accept-Language detection > "zh" fallback).
"""
import logging
import os
import sys
import tempfile
from pathlib import Path

import streamlit as st

# Project root (parent of this frontend/ dir) must be on sys.path so
# `backend.*` / `models.*` absolute imports resolve regardless of the
# working directory `streamlit run` was launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.conversation import session_adapter
from backend.diagnosis.difficulty import difficulty_badge_html, persona_tag_html
from backend.diagnosis.matcher import ScenarioConfig, match_scenario, to_session_config
from backend.diagnosis.questionnaire import QUESTIONNAIRE
from backend.speech import tts
from backend.speech.features import analyze_speech
from backend.speech.transcribe import transcribe_audio
from backend.storage.db import save_session
from frontend.strings import PERSONA_LABEL_KEYS, get_language, set_language, t
from models.session_schema import InterviewSession

logger = logging.getLogger(__name__)

st.set_page_config(page_title="AI Interview Coach", page_icon="🎯")


@st.cache_resource
def _warm_up_voices() -> None:
    """
    Pre-download/load every configured Piper voice once per server process
    (decision #39/week 11) -- st.cache_resource makes the body run exactly
    once no matter how many sessions or reruns hit this script, so a
    candidate's first real interviewer reply mid-interview never pays the
    download-on-first-use latency (see tts.warm_up_voices()'s docstring).
    """
    tts.warm_up_voices()


_warm_up_voices()

# ---------- Theme injection ----------
# Usage per theme.css's own header comment: read the file once at the very
# start of app.py and inject it as a single <style> block.
_theme_css_path = Path(__file__).resolve().parent / "styles" / "theme.css"
with open(_theme_css_path, encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ---------- Font style override ----------
# Two selectable font profiles (decision #16: font style picker lives on the
# welcome page, see render_welcome_page() below). "friendly" mirrors
# theme.css's own default Nunito-based font -- kept as an explicit entry
# (rather than "no override") so the welcome-page radio always has a real
# default value in session_state, even on the very first render.
FONT_STYLES = {
    "friendly": {
        "font_family": "'Nunito', 'PingFang SC', 'Microsoft YaHei', sans-serif",
        "import_url": None,  # already @import-ed by theme.css
    },
    "professional": {
        "font_family": "'Source Serif 4', 'Songti SC', 'SimSun', serif",
        "import_url": (
            "https://fonts.googleapis.com/css2?family=Source+Serif+4:"
            "opsz,wght@8..60,400;8..60,600;8..60,700&display=swap"
        ),
    },
}
DEFAULT_FONT_STYLE = "friendly"

_selected_font = FONT_STYLES[st.session_state.get("font_style", DEFAULT_FONT_STYLE)]
_font_css = ""
if _selected_font["import_url"]:
    _font_css += f"@import url('{_selected_font['import_url']}');\n"
_font_css += (
    'html, body, [class*="css"] { font-family: '
    f"{_selected_font['font_family']} !important; }}\n"
)
st.markdown(f"<style>{_font_css}</style>", unsafe_allow_html=True)

# ---------- Language resolution (must run before any t() call renders) ----------
get_language()  # auto-detects into st.session_state["language"] on first run of this session

# ---------- Onboarding stage routing ----------
# Explicit page router (decision #16): replaces the old implicit
# "scenario is None -> show form, else -> show result" branching. The
# underlying computation (match_scenario()) is unchanged; only *when* it
# fires and *which block renders* is now driven by this field.
if "onboarding_stage" not in st.session_state:
    st.session_state["onboarding_stage"] = "welcome"

# ---------- Header (shown on every stage) ----------
st.title(t("app_title"))
st.caption(t("app_subtitle"))


def render_welcome_page() -> None:
    with st.container(key="onboarding_welcome_container"):
        st.markdown(f"## {t('onboarding_welcome_title')}")
        st.write(t("onboarding_welcome_body"))

        st.markdown(f"**{t('onboarding_language_label')}**")
        lang_options = ["zh", "en"]
        current_lang = get_language()
        selected_lang = st.radio(
            t("onboarding_language_label"),
            options=lang_options,
            format_func=lambda v: t("lang_name_zh") if v == "zh" else t("lang_name_en"),
            index=lang_options.index(current_lang),
            key="onboarding_language_radio",
            label_visibility="collapsed",
            horizontal=True,
        )
        if selected_lang != current_lang:
            set_language(selected_lang)
            st.rerun()

        st.markdown(f"**{t('onboarding_font_label')}**")
        font_options = ["friendly", "professional"]
        current_font = st.session_state.get("font_style", DEFAULT_FONT_STYLE)
        selected_font = st.radio(
            t("onboarding_font_label"),
            options=font_options,
            format_func=lambda v: t(f"onboarding_font_{v}_name"),
            index=font_options.index(current_font),
            key="onboarding_font_radio",
            label_visibility="collapsed",
            horizontal=True,
        )
        st.session_state["font_style"] = selected_font
        st.caption(t(f"onboarding_font_{selected_font}_desc"))

        st.write("")
        if st.button(t("onboarding_start_button"), key="onboarding_start_button", type="primary"):
            st.session_state["onboarding_stage"] = "triage"
            st.rerun()


def render_triage_page() -> None:
    with st.container(key="onboarding_triage_container"):
        st.markdown(f"### {t('triage_page_heading')}")
        total_questions = len(QUESTIONNAIRE)
        current_index = st.session_state.get("triage_question_index", 0)
        st.progress(min(current_index, total_questions) / total_questions)

        if current_index < total_questions:
            _render_triage_dialog(current_index, total_questions)
        else:
            _finalize_triage()


def _render_triage_dialog(index: int, total: int) -> None:
    # Conversational, one-question-at-a-time modal (decision #17 item 1),
    # replacing the old single st.form with all 3 questions stacked at
    # once. option `value`/`label_key` schema and match_scenario() input
    # shape are untouched -- backend/diagnosis/questionnaire.py owns that.
    question = QUESTIONNAIRE[index]
    option_values = [opt["value"] for opt in question["options"]]
    option_labels = {opt["value"]: t(opt["label_key"]) for opt in question["options"]}
    is_last_question = index == total - 1
    dialog_title = f"{t('triage_progress_prefix')} {index + 1}/{total}"

    @st.dialog(dialog_title)
    def _ask() -> None:
        choice = st.radio(
            t(question["label_key"]),
            options=option_values,
            format_func=lambda v: option_labels[v],
            index=None,
            key=f"triage_dialog_choice_{index}",
        )
        button_label = t("triage_finish_button") if is_last_question else t("triage_next_button")
        if st.button(button_label, disabled=choice is None, key=f"triage_dialog_submit_{index}"):
            st.session_state.setdefault("triage_answers", {})[question["id"]] = choice
            st.session_state["triage_question_index"] = index + 1
            st.rerun()

    _ask()


def _finalize_triage() -> None:
    # Runs once all 3 questions are answered. Same match_scenario() /
    # InterviewSession persistence logic as the old form-submit handler,
    # just triggered from the dialog flow instead of a form submit button.
    # The "session_id" not in st.session_state guard is unchanged -- it's
    # what stops a later rerun (e.g. toggling font style on the result
    # page) from writing a duplicate row.
    answers = st.session_state.get("triage_answers", {})
    scenario: ScenarioConfig = match_scenario(answers)  # type: ignore[arg-type]
    st.session_state["scenario"] = scenario

    if "session_id" not in st.session_state:
        session = InterviewSession(config=to_session_config(scenario, language=get_language()))
        save_session(session)
        st.session_state["session_id"] = session.session_id
        # Kept in-memory (not just session_id) so the interview stage can
        # append qa_items onto this exact InterviewSession -- same row,
        # updated via save_session()'s upsert, never a second INSERT.
        st.session_state["interview_session"] = session

    st.session_state["onboarding_stage"] = "result"
    st.rerun()


def render_result_page() -> None:
    scenario: ScenarioConfig | None = st.session_state.get("scenario")
    if scenario is None:
        # Defensive fallback -- normal navigation always sets `scenario`
        # in _finalize_triage() before switching to "result", but this
        # avoids a crash if onboarding_stage ever desyncs from it.
        st.session_state["onboarding_stage"] = "welcome"
        st.rerun()
        return

    with st.container(key="onboarding_result_container"):
        st.markdown(
            f'<p class="result-reveal-heading">{t("result_heading")}</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p class="result-reveal-subtitle">{t("result_subtitle")}</p>',
            unsafe_allow_html=True,
        )

        with st.container(key="result_coach_card"):
            job_type_label = next(
                t(opt["label_key"])
                for q in QUESTIONNAIRE
                for opt in q["options"]
                if q["id"] == "job_type" and opt["value"] == scenario.job_type
            )
            stage_label = next(
                t(opt["label_key"])
                for q in QUESTIONNAIRE
                for opt in q["options"]
                if q["id"] == "stage" and opt["value"] == scenario.stage
            )
            persona_label = t(PERSONA_LABEL_KEYS[scenario.persona_css])

            st.markdown(f"**{t('result_job_type_label')}:** {job_type_label}")
            st.markdown(f"**{t('result_stage_label')}:** {stage_label}")
            st.markdown(
                f"**{t('result_difficulty_label')}:** "
                + difficulty_badge_html(scenario.difficulty)
                + "&nbsp;&nbsp;"
                + f"**{t('result_persona_label')}:** "
                + persona_tag_html(scenario.persona_css, persona_label),
                unsafe_allow_html=True,
            )

        st.success(f"{t('session_saved_message')} ({t('session_id_label')}: {st.session_state['session_id']})")

        st.write("")
        if st.button(t("interview_start_button"), key="interview_start_button", type="primary"):
            st.session_state["onboarding_stage"] = "interview"
            st.rerun()


def _synthesize_reply_audio(text: str, persona, language: str) -> bytes | None:
    """
    Best-effort TTS for one interviewer line (week 11/decision #39). Returns
    None on any synthesis failure instead of raising -- a Piper hiccup
    should degrade to text-only for that line, the same "never let an
    optional enhancement take the session down" rule the project already
    applies to realtime_feedback.py's Groq calls.
    """
    try:
        return tts.synthesize_short_reply(text, persona, language)
    except Exception:
        logger.warning("TTS synthesis failed for an interviewer line; falling back to text-only.", exc_info=True)
        return None


def _render_input_mode_dialog() -> None:
    # Asked once, right before the interview starts (user-requested followup
    # to week 11 voice integration). This sets only an initial *default* --
    # decision #39's "never a forced either/or" still holds every round;
    # both st.chat_input and st.audio_input stay reachable afterward no
    # matter which button is picked here (see render_interview_page()'s
    # input section, which reads preferred_input_mode just to decide
    # whether the voice recorder starts expanded or tucked in an expander).
    @st.dialog(t("interview_mode_dialog_title"))
    def _ask() -> None:
        st.write(t("interview_mode_dialog_body"))
        col_voice, col_text = st.columns(2)
        with col_voice:
            if st.button(
                t("interview_mode_voice_button"),
                key="interview_mode_voice_button",
                type="primary",
                use_container_width=True,
            ):
                st.session_state["preferred_input_mode"] = "voice"
                st.rerun()
        with col_text:
            if st.button(
                t("interview_mode_text_button"),
                key="interview_mode_text_button",
                use_container_width=True,
            ):
                st.session_state["preferred_input_mode"] = "text"
                st.rerun()

    _ask()


def render_interview_page() -> None:
    scenario: ScenarioConfig | None = st.session_state.get("scenario")
    interview_session: InterviewSession | None = st.session_state.get("interview_session")
    if scenario is None or interview_session is None:
        # Defensive fallback, same reasoning as render_result_page()'s --
        # normal navigation always sets both before switching to "interview".
        st.session_state["onboarding_stage"] = "welcome"
        st.rerun()
        return

    if "preferred_input_mode" not in st.session_state:
        # Blocks the rest of this page behind the modal until answered --
        # nothing below (engine start, transcript, inputs) needs to render
        # while the dialog is still up.
        _render_input_mode_dialog()
        return

    persona = session_adapter.resolve_persona(scenario.persona)
    language = get_language()

    if "engine_session" not in st.session_state:
        # First entry into this stage: kick off the engine and immediately
        # run the priming exchange (decision #4) so the transcript already
        # contains the opening line *and* the first real question before
        # the candidate has to type anything. Each assistant line's audio is
        # synthesized once here and cached on the transcript entry itself,
        # rather than re-synthesized on every rerun's render pass.
        opening_line, first_question, engine_session, progress = session_adapter.start(scenario.persona, language)
        st.session_state["engine_session"] = engine_session
        st.session_state["interview_progress"] = progress
        st.session_state["interview_transcript"] = [
            {
                "role": "assistant",
                "content": opening_line,
                "audio_bytes": _synthesize_reply_audio(opening_line, persona, language),
            },
            {
                "role": "assistant",
                "content": first_question,
                "audio_bytes": _synthesize_reply_audio(first_question, persona, language),
            },
        ]
        st.session_state["audio_input_generation"] = 0

    def _process_answer(answer_text: str, speech_analysis=None) -> None:
        """
        Shared submit_round() tail for both input paths (decision #39/week 11
        design decision #1: typed and spoken answers converge here) -- the
        only difference between them is whether speech_analysis is None.
        """
        result, new_progress, should_end, feedback = session_adapter.submit_round(
            answer_text,
            st.session_state["engine_session"],
            st.session_state["interview_progress"],
            interview_session,
            speech_analysis=speech_analysis,
        )
        st.session_state["interview_progress"] = new_progress

        user_turn = {"role": "user", "content": answer_text}
        if feedback.content_feedback or feedback.expression_suggestions:
            user_turn["content_feedback"] = feedback.content_feedback
            user_turn["expression_suggestions"] = feedback.expression_suggestions
        st.session_state["interview_transcript"].append(user_turn)

        if should_end:
            # result.reply bleeds into a topic we're not asking (see
            # session_adapter.submit_round()'s docstring) -- discard it,
            # go straight to the end screen.
            session_adapter.end_interview(interview_session)
            st.session_state["onboarding_stage"] = "interview_ended"
        else:
            st.session_state["interview_transcript"].append(
                {
                    "role": "assistant",
                    "content": result.reply,
                    "audio_bytes": _synthesize_reply_audio(result.reply, persona, language),
                }
            )
        st.rerun()

    with st.container(key="interview_container"):
        st.markdown(f"### {t('interview_page_heading')}")

        if st.session_state.get("voice_input_error"):
            # Shown for exactly one rerun (the one right after the failed
            # attempt) -- see the ASR try/except below for why this flag
            # exists instead of an inline st.error() at the failure site.
            st.error(t("interview_voice_asr_error"))
            st.session_state["voice_input_error"] = False

        transcript = st.session_state["interview_transcript"]
        # Only the most recent interviewer line should autoplay -- st.audio's
        # `controls` bar is always rendered regardless of autoplay (verified
        # against Streamlit 1.45.1's frontend bundle), so every older line
        # still has a visible, clickable play button; it just doesn't
        # self-start when the transcript is re-rendered on every rerun.
        last_assistant_idx = max((i for i, turn in enumerate(transcript) if turn["role"] == "assistant"), default=-1)
        for i, turn in enumerate(transcript):
            st.chat_message(turn["role"]).write(turn["content"])
            if turn["role"] == "assistant" and turn.get("audio_bytes"):
                st.audio(turn["audio_bytes"], format="audio/wav", autoplay=(i == last_assistant_idx))
            # Week 10 coach aside (decision #17 item 2): rendered in its own
            # expander, visually separate from the chat bubbles above, since
            # this is feedback about the candidate's last answer, not part
            # of the interviewer's in-character dialogue. Only shown when
            # generation actually produced something -- a silent skip on
            # failure, never an error message (see realtime_feedback.py).
            if turn.get("content_feedback") or turn.get("expression_suggestions"):
                with st.expander(t("realtime_feedback_title"), expanded=True):
                    if turn.get("content_feedback"):
                        st.markdown(f"**{t('realtime_feedback_content_label')}:** {turn['content_feedback']}")
                    if turn.get("expression_suggestions"):
                        st.markdown(f"**{t('realtime_feedback_expression_label')}:**")
                        for suggestion in turn["expression_suggestions"]:
                            st.markdown(f"- {suggestion}")

        if st.button(t("interview_end_button"), key="interview_end_button"):
            session_adapter.end_interview(interview_session)
            st.session_state["onboarding_stage"] = "interview_ended"
            st.rerun()

        # Voice input: always reachable alongside typed input, never a forced
        # either/or (decision #39/week 11 design decision #1) -- the
        # pre-interview dialog above only sets which one is the *visible
        # default* here. "voice" keeps the recorder directly on the page
        # (unchanged from before); "text" tucks it behind a collapsed
        # expander so the page reads as typing-first, one click away from
        # switching to voice. Either way st.chat_input below is always live.
        st.caption(
            t("interview_mode_hint_voice")
            if st.session_state["preferred_input_mode"] == "voice"
            else t("interview_mode_hint_text")
        )

        # The widget's key carries a generation counter so it resets to
        # empty right after each processed recording -- st.audio_input has
        # no .clear() of its own, and would otherwise keep re-returning the
        # same bytes on every later rerun and get reprocessed as a "new"
        # answer.
        audio_key = f"interview_audio_input_{st.session_state['audio_input_generation']}"
        if st.session_state["preferred_input_mode"] == "voice":
            audio_value = st.audio_input(t("interview_audio_label"), key=audio_key)
        else:
            with st.expander(t("interview_voice_expander_label"), expanded=False):
                audio_value = st.audio_input(t("interview_audio_label"), key=audio_key)

        if audio_value is not None:
            st.session_state["audio_input_generation"] += 1
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(prefix="interview_answer_", suffix=".wav", delete=False) as tmp_file:
                    tmp_file.write(audio_value.getvalue())
                    tmp_path = tmp_file.name

                # transcribe_audio() raises RuntimeError on failure (design
                # decision #2/week 11) -- unlike this project's Groq call
                # sites, it has no built-in fallback, so the UI layer is
                # responsible for catching it and degrading gracefully
                # instead of taking the whole session down with it.
                try:
                    transcription = transcribe_audio(tmp_path, language=language)
                except RuntimeError:
                    logger.warning("ASR failed for a voice answer; candidate can retry by typing.", exc_info=True)
                    st.session_state["voice_input_error"] = True
                    st.rerun()
                    return

                answer_text = transcription.text.strip()
                if not answer_text:
                    # Nothing recognizable (e.g. silence) -- same recovery
                    # path as an outright ASR failure.
                    st.session_state["voice_input_error"] = True
                    st.rerun()
                    return

                speech_analysis = analyze_speech(transcription, tmp_path)
            finally:
                # Clean up the ASR temp file regardless of outcome (design
                # decision #6/week 11) -- never let recording attempts
                # accumulate on disk.
                if tmp_path is not None:
                    os.unlink(tmp_path)

            _process_answer(answer_text, speech_analysis=speech_analysis)
            return

        answer = st.chat_input(t("interview_answer_placeholder"))
        if answer:
            _process_answer(answer)


def render_interview_ended_page() -> None:
    with st.container(key="interview_ended_container"):
        st.markdown(f"### {t('interview_ended_heading')}")
        st.success(f"{t('interview_ended_message')} ({t('session_id_label')}: {st.session_state.get('session_id', '')})")


_STAGE_RENDERERS = {
    "welcome": render_welcome_page,
    "triage": render_triage_page,
    "result": render_result_page,
    "interview": render_interview_page,
    "interview_ended": render_interview_ended_page,
}
_STAGE_RENDERERS[st.session_state["onboarding_stage"]]()
