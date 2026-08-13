"""
AI Interview System - Triage Questionnaire Page

Flow: render the 3-question questionnaire (job type / experience / stage) ->
on submit, match_scenario() computes the ScenarioConfig -> render the
difficulty badge + persona tag -> persist as an InterviewSession via
backend/storage/db.py.

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

# ---------- Language resolution (must run before any t() call renders) ----------
get_language()  # auto-detects into st.session_state["language"] on first run of this session

with st.sidebar:
    st.markdown(f"**{t('sidebar_language_label')}**")
    current_lang = get_language()
    target_lang = "en" if current_lang == "zh" else "zh"
    target_lang_name = t("lang_name_en") if target_lang == "en" else t("lang_name_zh")
    if st.button(target_lang_name, key="language_toggle_button"):
        set_language(target_lang)
        st.rerun()

# ---------- Header ----------
st.title(t("app_title"))
st.caption(t("app_subtitle"))

# ---------- Questionnaire form ----------
# Rendered generically off backend/diagnosis/questionnaire.py's QUESTIONNAIRE
# schema: each option's `value` is the canonical (Chinese) key matcher.py /
# difficulty.py expect, `label_key` is what gets localized for display.
with st.form("triage_questionnaire"):
    answers: dict[str, str | None] = {}
    for question in QUESTIONNAIRE:
        option_values = [opt["value"] for opt in question["options"]]
        option_labels = {opt["value"]: t(opt["label_key"]) for opt in question["options"]}
        answers[question["id"]] = st.radio(
            t(question["label_key"]),
            options=option_values,
            format_func=lambda v, _labels=option_labels: _labels[v],
            index=None,
            key=f"triage_{question['id']}",
        )
    submitted = st.form_submit_button(t("submit_button"))

if submitted:
    if any(value is None for value in answers.values()):
        st.warning(t("form_incomplete_warning"))
    else:
        scenario: ScenarioConfig = match_scenario(answers)  # type: ignore[arg-type]
        st.session_state["scenario"] = scenario

# ---------- Result ----------
scenario: ScenarioConfig | None = st.session_state.get("scenario")
if scenario is not None:
    st.markdown(f'<div class="coach-card">', unsafe_allow_html=True)
    st.subheader(t("result_heading"))

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
    st.markdown("</div>", unsafe_allow_html=True)

    # Persist as an InterviewSession on first render of this result (guarded
    # by session_id already being stashed) so a page rerun -- e.g. toggling
    # the language switch -- doesn't write duplicate rows.
    if "session_id" not in st.session_state:
        session = InterviewSession(
            config=to_session_config(scenario, language=get_language()),
        )
        save_session(session)
        st.session_state["session_id"] = session.session_id

    st.success(f"{t('session_saved_message')} ({t('session_id_label')}: {st.session_state['session_id']})")
