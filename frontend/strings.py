"""
AI Interview System - Bilingual (zh/en) String Table

All frontend copy lives in STRINGS, keyed first by language code then by a
lookup key. Nothing in frontend/app.py (or any other frontend module) should
hardcode a user-facing zh or en literal -- every piece of text is fetched
through t(key), so STRINGS is the single place translations get added or
edited.

Language resolution order:
1. Manual override -- once the user clicks the language toggle, set_language()
   writes st.session_state["language"] and that always wins from then on.
2. Auto-detection -- on first render (session_state not yet populated),
   detect_browser_language() inspects the browser's Accept-Language header
   via st.context.headers.
3. Fallback -- "zh", whenever the header is missing, empty, or unparsable.
"""
import streamlit as st

DEFAULT_LANGUAGE = "zh"
SUPPORTED_LANGUAGES = ("zh", "en")

STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        # ---------- App shell ----------
        "app_title": "智能面试教练",
        "app_subtitle": "三步为你匹配专属模拟面试场景",
        "sidebar_language_label": "语言",
        "lang_name_zh": "中文",
        "lang_name_en": "English",
        # ---------- Questionnaire ----------
        "q_job_type_label": "你应聘的岗位类型是？",
        "q_experience_label": "你的经验水平是？",
        "q_stage_label": "当前处于哪个面试阶段？",
        "opt_job_tech": "技术",
        "opt_job_product": "产品",
        "opt_job_marketing": "市场营销",
        "opt_job_ops": "运营",
        "opt_job_design": "设计",
        "opt_job_consulting": "咨询",
        "opt_job_finance": "金融",
        "opt_exp_intern": "实习生",
        "opt_exp_junior": "应届",
        "opt_exp_mid": "1-3年",
        "opt_exp_senior": "3年以上",
        "opt_stage_hr": "HR初筛",
        "opt_stage_tech1": "技术面①",
        "opt_stage_tech2": "技术面②",
        "opt_stage_final": "终面",
        "submit_button": "生成我的面试场景",
        "form_incomplete_warning": "请完成全部三项选择后再提交",
        # ---------- Result ----------
        "result_heading": "匹配结果",
        "result_job_type_label": "岗位类型",
        "result_stage_label": "面试阶段",
        "result_difficulty_label": "难度",
        "result_persona_label": "面试官人设",
        "session_saved_message": "本次匹配结果已保存",
        "session_id_label": "会话编号",
        # ---------- Interviewer personas (persona_tag_html label param) ----------
        "persona_friendly": "亲和型",
        "persona_technical": "技术挖掘型",
        "persona_strict": "严格型",
        # ---------- difficulty_badge_html() label word ----------
        "difficulty_word": "难度",
    },
    "en": {
        # ---------- App shell ----------
        "app_title": "AI Interview Coach",
        "app_subtitle": "Three questions to match your mock interview scenario",
        "sidebar_language_label": "Language",
        "lang_name_zh": "中文",
        "lang_name_en": "English",
        # ---------- Questionnaire ----------
        "q_job_type_label": "What type of role are you interviewing for?",
        "q_experience_label": "What is your experience level?",
        "q_stage_label": "Which interview stage are you preparing for?",
        "opt_job_tech": "Technology",
        "opt_job_product": "Product",
        "opt_job_marketing": "Marketing",
        "opt_job_ops": "Operations",
        "opt_job_design": "Design",
        "opt_job_consulting": "Consulting",
        "opt_job_finance": "Finance",
        "opt_exp_intern": "Intern",
        "opt_exp_junior": "New Graduate",
        "opt_exp_mid": "1-3 Years",
        "opt_exp_senior": "3+ Years",
        "opt_stage_hr": "HR Screen",
        "opt_stage_tech1": "Technical Round 1",
        "opt_stage_tech2": "Technical Round 2",
        "opt_stage_final": "Final Round",
        "submit_button": "Match My Interview Scenario",
        "form_incomplete_warning": "Please answer all three questions before submitting",
        # ---------- Result ----------
        "result_heading": "Your Matched Scenario",
        "result_job_type_label": "Job Type",
        "result_stage_label": "Interview Stage",
        "result_difficulty_label": "Difficulty",
        "result_persona_label": "Interviewer Persona",
        "session_saved_message": "This matched scenario has been saved",
        "session_id_label": "Session ID",
        # ---------- Interviewer personas (persona_tag_html label param) ----------
        "persona_friendly": "Friendly",
        "persona_technical": "Technical Prober",
        "persona_strict": "Rigorous",
        # ---------- difficulty_badge_html() label word ----------
        "difficulty_word": "Difficulty",
    },
}

# Maps difficulty.STAGE_CONFIG's persona_css value to the STRINGS key holding
# the localized persona label, so app.py can pass a language-appropriate
# label into persona_tag_html() without hardcoding any zh/en literal itself.
PERSONA_LABEL_KEYS = {
    "friendly": "persona_friendly",
    "technical": "persona_technical",
    "strict": "persona_strict",
}


def detect_browser_language() -> str:
    """
    Best-effort detection of the visitor's preferred language from the
    browser's Accept-Language request header, exposed by Streamlit via
    st.context.headers.

    Falls back to DEFAULT_LANGUAGE ("zh") whenever st.context is unavailable
    (e.g. this module imported outside a running Streamlit script), the
    header is missing/empty, or it simply doesn't mention "en" -- so an
    unparsable or unexpected header value never raises, it just falls back.
    """
    try:
        headers = st.context.headers
        accept_language = (headers.get("Accept-Language") or "") if headers else ""
    except Exception:
        accept_language = ""

    if "en" in accept_language.lower():
        return "en"
    return DEFAULT_LANGUAGE


def get_language() -> str:
    """
    Current UI language. Auto-detects and caches into session_state on first
    call each session; every call after that (including after the user
    manually toggles via set_language()) just reads the cached value back.
    """
    if "language" not in st.session_state:
        st.session_state["language"] = detect_browser_language()
    return st.session_state["language"]


def set_language(lang: str) -> None:
    """Manual override, e.g. from the sidebar toggle button. Wins over auto-detection."""
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {lang}, expected one of {SUPPORTED_LANGUAGES}")
    st.session_state["language"] = lang


def t(key: str) -> str:
    """Look up `key` in STRINGS for the current language, falling back to DEFAULT_LANGUAGE."""
    lang = get_language()
    table = STRINGS.get(lang, STRINGS[DEFAULT_LANGUAGE])
    return table.get(key, STRINGS[DEFAULT_LANGUAGE].get(key, key))
