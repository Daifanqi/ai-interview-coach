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

import pandas as pd
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
from backend.storage.db import list_sessions_by_user, load_session, save_session
from backend.storage.user_db import InvalidCredentialsError, UsernameTakenError, authenticate_user, create_user
from frontend.strings import PERSONA_LABEL_KEYS, get_language, set_language, t
from models.session_schema import DimensionScoreDetail, InterviewSession, ReviewReport

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


@st.cache_resource
def _warm_up_question_bank() -> None:
    """
    Pre-build/load the RAG question-bank Chroma index once per server
    process (decision #39/week 12), mirroring _warm_up_voices() above --
    otherwise the first candidate to reach a real topic transition
    mid-interview pays the "embed all 200 bank questions" cost inline.
    """
    from backend.rag.retriever import warm_up_retriever

    warm_up_retriever()


_warm_up_voices()
_warm_up_question_bank()

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


# ---------- Login / Register (Week 14, decision #43) ----------
# Gates every stage below -- st.session_state["current_user"] holds a
# models.user_schema.User once logged in, deliberately kept in
# session_state only (not a cookie): a browser refresh logs the candidate
# out again, per decision #43's scope choice to avoid adding a cookie-
# management dependency for this project. Real user_id now flows into
# InterviewSession (see _finalize_triage() below) instead of the "" that
# every session carried before this week.

# Reason code (backend/storage/user_db.py's InvalidCredentialsError.reason)
# -> localized string key, so that backend module never has to hardcode
# zh/en prose itself (see its own docstring).
_VALIDATION_ERROR_STRING_KEYS = {
    "username_too_short": "auth_error_username_too_short",
    "username_too_long": "auth_error_username_too_long",
    "password_too_short": "auth_error_password_too_short",
}


def _render_login_form() -> None:
    with st.form("auth_login_form"):
        username = st.text_input(t("auth_username_label"), key="auth_login_username")
        password = st.text_input(t("auth_password_label"), type="password", key="auth_login_password")
        submitted = st.form_submit_button(t("auth_login_button"), type="primary", use_container_width=True)

    if not submitted:
        return
    user = authenticate_user(username, password)
    if user is None:
        st.error(t("auth_error_invalid_credentials"))
        return
    st.session_state["current_user"] = user
    st.rerun()


def _render_register_form() -> None:
    with st.form("auth_register_form"):
        username = st.text_input(t("auth_username_label"), key="auth_register_username")
        password = st.text_input(t("auth_password_label"), type="password", key="auth_register_password")
        confirm_password = st.text_input(
            t("auth_confirm_password_label"), type="password", key="auth_register_confirm"
        )
        submitted = st.form_submit_button(t("auth_register_button"), type="primary", use_container_width=True)

    if not submitted:
        return
    if password != confirm_password:
        st.error(t("auth_error_password_mismatch"))
        return
    try:
        user = create_user(username, password)
    except InvalidCredentialsError as exc:
        st.error(t(_VALIDATION_ERROR_STRING_KEYS.get(exc.reason, "auth_error_invalid_input")))
        return
    except UsernameTakenError:
        st.error(t("auth_error_username_taken"))
        return

    st.session_state["current_user"] = user
    st.success(t("auth_register_success"))
    st.rerun()


def render_login_page() -> None:
    with st.container(key="auth_container"):
        st.markdown(f"## {t('auth_page_title')}")
        st.write(t("auth_page_body"))

        mode = st.radio(
            t("auth_mode_label"),
            options=["login", "register"],
            format_func=lambda v: t("auth_login_tab") if v == "login" else t("auth_register_tab"),
            index=0,
            key="auth_mode_radio",
            horizontal=True,
            label_visibility="collapsed",
        )
        if mode == "login":
            _render_login_form()
        else:
            _render_register_form()


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
        # Week 14: real user_id, threaded from the login gate below --
        # every session before this week was permanently user_id="" (see
        # backend/storage/db.py's list_sessions_by_user() and decision #43).
        session = InterviewSession(
            config=to_session_config(scenario, language=get_language()),
            user_id=st.session_state["current_user"].user_id,
        )
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
        opening_line, first_question, engine_session, progress = session_adapter.start(
            scenario.persona, language, interview_session.config.job_type, interview_session.config.interview_stage
        )
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
            # go straight to the end screen. Report generation runs async
            # (decision #47, post-roadmap) -- see render_interview_ended_page()
            # for how the handle stashed here drives the "generating..." state.
            st.session_state["report_generation_handle"] = session_adapter.end_interview_async(interview_session)
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
            # Same async report-generation path as the MAX_TOPICS auto-end
            # branch in _process_answer() above (decision #47).
            st.session_state["report_generation_handle"] = session_adapter.end_interview_async(interview_session)
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


def _render_dimension_detail(label: str, dimension: DimensionScoreDetail) -> None:
    """
    One dimension's score/explanation/sentence-highlights (week 15,
    surfacing week 13's backend/scoring/report.py Highlight data for the
    first time). explanation is prose baseline.py generates in Chinese only
    regardless of session language (a pre-existing gap this week doesn't
    fix, not something week 15 introduces) -- everything else here is
    localized normally.
    """
    st.markdown(f"**{label}：** {dimension.score:.1f}/10")
    st.caption(dimension.explanation)
    for highlight in dimension.highlights:
        icon = "✅" if highlight.polarity == "positive" else "⚠️"
        st.markdown(f"{icon} “{highlight.sentence_text}” — {highlight.reason}")


def _render_trend_chart(report: ReviewReport) -> None:
    """
    Cross-session score trend (decision #10/#39, week 13's history_trend +
    week 15's chart). Uses st.line_chart (backed by streamlit's own bundled
    pandas dependency) rather than a custom Altair chart -- this project
    avoids adding dependencies it can't verify are installed in the real
    environment where nothing else needs Altair (decision #44), same
    reasoning as decision #43's stdlib-only password hashing.

    Only includes *today's* point when this session actually produced a
    real score (report.detailed_scores non-empty) -- otherwise a 0.0
    "today" point would visually read as a real bad score and distort the
    trend line, when it actually just means nothing was scoreable this
    session (see render_interview_ended_page()'s own empty-score handling).
    """
    points = [{"date": tp.session_date, "score": tp.overall_score} for tp in report.history_trend]
    if report.detailed_scores:
        points.append({"date": report.generated_at, "score": report.overall_score})

    if len(points) < 2:
        # First-ever scored session (or a history-less account) -- a
        # single-point line chart has nothing useful to show.
        st.caption(t("report_trend_empty_message"))
        return

    trend_df = pd.DataFrame(points).sort_values("date")
    st.line_chart(trend_df, x="date", y="score", use_container_width=True)


def _render_review_report(interview_session: InterviewSession, report: ReviewReport) -> None:
    with st.container(key="report_overview_card"):
        st.markdown(f"## {t('report_page_heading')}")
        if report.detailed_scores:
            st.metric(t("report_overall_score_label"), f"{report.overall_score:.1f} / 10")
        else:
            # Interview ended (e.g. the manual "end interview" button) before
            # any main topic was fully answered -- nothing to score yet, so
            # showing "0.0/10" would misleadingly read as a real bad score.
            st.caption(t("report_no_scoreable_topics_message"))

    if report.highlight_turn_id and report.highlight_reason:
        with st.container(key="report_highlight_card"):
            st.markdown(f"#### {t('report_ai_highlight_title')}")
            highlight_detail = report.detailed_scores.get(report.highlight_turn_id)
            if highlight_detail:
                st.markdown(f"**{highlight_detail.question_text}**")
            st.write(report.highlight_reason)

    if report.detailed_scores:
        with st.container(key="report_topics_card"):
            st.markdown(f"#### {t('report_topics_heading')}")
            for detail in report.detailed_scores.values():
                with st.expander(f"{detail.question_text}　·　{detail.overall_score:.1f}/10"):
                    _render_dimension_detail(t("report_dimension_structure"), detail.structure_completeness)
                    _render_dimension_detail(t("report_dimension_keyword"), detail.keyword_coverage)
                    _render_dimension_detail(t("report_dimension_logical"), detail.logical_coherence)
                    _render_dimension_detail(t("report_dimension_specificity"), detail.specificity)

    with st.container(key="report_voice_card"):
        st.markdown(f"#### {t('report_voice_summary_title')}")
        st.write(report.voice_summary)

    if report.text_correction_suggestions:
        with st.container(key="report_corrections_card"):
            st.markdown(f"#### {t('report_text_corrections_title')}")
            for suggestion in report.text_correction_suggestions:
                st.markdown(f"- {suggestion}")

    with st.container(key="report_trend_card"):
        st.markdown(f"#### {t('report_trend_title')}")
        _render_trend_chart(report)


# How long render_interview_ended_page() blocks per poll iteration while
# waiting on a still-running report-generation handle (decision #47) before
# re-running the script to check again. A few seconds keeps the "generating"
# state feeling responsive without spinning the session's script-run thread
# in a tight loop -- handle.done_event.wait() returns immediately (well
# before this timeout) the moment the background worker actually finishes.
REPORT_POLL_INTERVAL_SECONDS = 2.0


def render_interview_ended_page() -> None:
    with st.container(key="interview_ended_container"):
        st.markdown(f"### {t('interview_ended_heading')}")
        st.success(f"{t('interview_ended_message')} ({t('session_id_label')}: {st.session_state.get('session_id', '')})")

    interview_session: InterviewSession | None = st.session_state.get("interview_session")
    if interview_session is None:
        return

    # Report generation runs on a background thread now (decision #47) --
    # session_adapter.end_interview_async() stashed a handle in
    # session_state right before switching to this stage. While it's still
    # running, show a spinner and poll: wait up to REPORT_POLL_INTERVAL_
    # SECONDS for the worker to finish (returns immediately if it already
    # has), then rerun the script so this function runs again and re-checks.
    # Once done_event is set, interview_session.report is safe to read (see
    # ReportGenerationHandle's own docstring for why that ordering is safe
    # without an explicit lock).
    handle = st.session_state.get("report_generation_handle")
    if handle is not None and not handle.done_event.is_set():
        with st.container(key="report_generating_container"):
            with st.spinner(t("report_generating_spinner_label")):
                handle.done_event.wait(timeout=REPORT_POLL_INTERVAL_SECONDS)
        st.rerun()
        return

    report = interview_session.report
    if report is None:
        # Either report generation failed (_generate_and_save_report()'s
        # try/except leaves interview_session.report as None on any
        # unexpected error) or this page was somehow reached in an odd
        # state -- fall back to just the confirmation above rather than
        # crashing the page.
        return

    _render_review_report(interview_session, report)


def render_history_page() -> None:
    """
    Standalone browse page for a logged-in user's past interview reports
    (post-roadmap, decision #47) -- reachable from the sidebar nav
    (see the auth-gate section below) independent of the just-finished
    interview flow, unlike render_interview_ended_page() above which only
    ever shows the report for *this* browser session's current
    interview_session.

    Two sub-views toggled by whether "history_selected_session_id" is set:
    a list of the user's past sessions (date / job type / score), or one
    selected session's full report, reusing _render_review_report() --
    the same rendering logic render_interview_ended_page() uses -- rather
    than duplicating report layout here.
    """
    with st.container(key="history_container"):
        st.markdown(f"### {t('history_page_heading')}")

        selected_session_id = st.session_state.get("history_selected_session_id")
        if st.button(t("history_back_button"), key="history_back_button"):
            if selected_session_id is not None:
                # Back out of a report detail view to the list first, rather
                # than leaving the history page entirely on the first click.
                st.session_state["history_selected_session_id"] = None
            else:
                st.session_state["onboarding_stage"] = st.session_state.get("history_return_stage", "welcome")
            st.rerun()
            return

        if selected_session_id is not None:
            selected_session = load_session(selected_session_id)
            if selected_session is None or selected_session.report is None:
                # A stale/removed session_id, or one that ended without a
                # scoreable report (e.g. generation failed, or the session
                # was abandoned before any main question was answered).
                st.caption(t("history_report_unavailable_message"))
            else:
                _render_review_report(selected_session, selected_session.report)
            return

        user_id = st.session_state["current_user"].user_id
        past_sessions = list_sessions_by_user(user_id)
        # list_sessions_by_user() returns chronological (oldest-first, see
        # its own docstring) -- reversed here so the most recent interview
        # is the first thing this browse page shows.
        past_sessions = list(reversed(past_sessions))

        if not past_sessions:
            st.caption(t("history_empty_message"))
            return

        for session in past_sessions:
            _render_history_list_item(session)


def _render_history_list_item(session: InterviewSession) -> None:
    session_date = session.ended_at or session.created_at
    date_label = session_date.strftime("%Y-%m-%d %H:%M") if session_date else "-"
    job_type_label = session.config.job_type if session.config else "-"
    if session.report is not None and session.report.detailed_scores:
        score_label = f"{session.report.overall_score:.1f}/10"
    else:
        # Covers both "report generation never ran/failed for this session"
        # and "ended with zero scoreable topics" -- same fallback copy
        # _render_review_report() uses for the latter case on the detail view.
        score_label = t("history_no_score_label")

    with st.container(key=f"history_item_{session.session_id}"):
        cols = st.columns([3, 3, 2, 2])
        cols[0].write(date_label)
        cols[1].write(job_type_label)
        cols[2].write(score_label)
        if cols[3].button(t("history_view_button"), key=f"history_view_{session.session_id}"):
            st.session_state["history_selected_session_id"] = session.session_id
            st.rerun()


_STAGE_RENDERERS = {
    "welcome": render_welcome_page,
    "triage": render_triage_page,
    "result": render_result_page,
    "interview": render_interview_page,
    "interview_ended": render_interview_ended_page,
    "history": render_history_page,
}

# ---------- Auth gate (Week 14) ----------
# Everything above this point (theme/font injection, language resolution,
# header) is shared chrome shown on the login page too; everything the
# onboarding-stage router renders is gated behind a real logged-in user.
if "current_user" not in st.session_state:
    render_login_page()
else:
    st.sidebar.caption(f"👤 {st.session_state['current_user'].username}")

    # History page nav (post-roadmap, decision #47): hidden mid-interview
    # so a sidebar click can't accidentally abandon a live interview
    # (nothing here saves/warns before switching stages), and hidden while
    # already on the history page itself so "back" (see render_history_page())
    # is the only way out rather than this button re-arming its own return
    # stage to "history".
    _current_stage = st.session_state["onboarding_stage"]
    if _current_stage not in ("interview", "history"):
        if st.sidebar.button(t("history_nav_button"), key="history_nav_button"):
            st.session_state["history_return_stage"] = _current_stage
            st.session_state["history_selected_session_id"] = None
            st.session_state["onboarding_stage"] = "history"
            st.rerun()

    if st.sidebar.button(t("auth_logout_button"), key="auth_logout_button"):
        del st.session_state["current_user"]
        st.rerun()
    _STAGE_RENDERERS[st.session_state["onboarding_stage"]]()
