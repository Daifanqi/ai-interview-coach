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
import sys
from pathlib import Path

import streamlit as st

# Project root (parent of this frontend/ dir) must be on sys.path so
# `backend.*` / `models.*` absolute imports resolve regardless of the
# working directory `streamlit run` was launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.diagnosis.difficulty import difficulty_badge_html, persona_tag_html
from backend.diagnosis.matcher import ScenarioConfig, match_scenario, to_session_config
from backend.diagnosis.questionnaire import QUESTIONNAIRE
from backend.storage.db import save_session
from frontend.strings import PERSONA_LABEL_KEYS, get_language, set_language, t
from models.session_schema import InterviewSession

st.set_page_config(page_title="AI Interview Coach", page_icon="🎯")

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


_STAGE_RENDERERS = {
    "welcome": render_welcome_page,
    "triage": render_triage_page,
    "result": render_result_page,
}
_STAGE_RENDERERS[st.session_state["onboarding_stage"]]()
