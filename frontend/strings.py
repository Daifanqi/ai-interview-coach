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
        "lang_name_zh": "中文",
        "lang_name_en": "English",
        # ---------- Onboarding (welcome page, Week 8) ----------
        "onboarding_welcome_title": "欢迎来到智能面试教练",
        "onboarding_welcome_body": (
            "接下来我们会用三个小问题了解你的面试场景，然后为你匹配专属的"
            "AI面试官和难度。先花几秒钟设置一下你的语言和界面风格吧。"
        ),
        "onboarding_language_label": "选择语言",
        "onboarding_font_label": "选择界面风格",
        "onboarding_font_friendly_name": "亲和圆润",
        "onboarding_font_friendly_desc": "温暖轻松的视觉风格，圆润字体，适合放松准备面试。",
        "onboarding_font_professional_name": "专业简洁",
        "onboarding_font_professional_desc": "沉稳克制的衬线字体，更贴近正式面试场合的氛围。",
        "onboarding_start_button": "开始",
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
        "triage_page_heading": "了解你的面试场景",
        "triage_progress_prefix": "问题",
        "triage_next_button": "下一题",
        "triage_finish_button": "完成",
        # ---------- Result ----------
        "result_heading": "匹配结果",
        "result_subtitle": "这是根据你的分诊回答匹配到的专属面试场景",
        "result_job_type_label": "岗位类型",
        "result_stage_label": "面试阶段",
        "result_difficulty_label": "难度",
        "result_persona_label": "面试官人设",
        "session_saved_message": "本次匹配结果已保存",
        "session_id_label": "会话编号",
        "interview_start_button": "开始面试",
        # ---------- Interview (Week 9) ----------
        "interview_page_heading": "模拟面试进行中",
        "interview_end_button": "结束面试",
        "interview_answer_placeholder": "输入你的回答……",
        "interview_ended_heading": "面试已结束",
        "interview_ended_message": "本轮问答记录已保存",
        # ---------- Review report (Week 15) ----------
        # Shown on the interview_ended page once a report was generated
        # (see backend/conversation/session_adapter.py's end_interview()).
        "report_page_heading": "复盘报告",
        "report_overall_score_label": "综合得分",
        "report_no_scoreable_topics_message": "本次面试还没有完整回答过一道主问题，暂时无法生成打分。",
        "report_ai_highlight_title": "🌟 AI高光时刻",
        "report_topics_heading": "逐题详情",
        "report_dimension_structure": "结构完整性",
        "report_dimension_keyword": "关键词覆盖",
        "report_dimension_logical": "逻辑连贯性",
        "report_dimension_specificity": "具体程度",
        "report_voice_summary_title": "🎙️ 语音表现",
        "report_text_corrections_title": "✏️ 表达纠正建议",
        "report_trend_title": "📈 进步趋势",
        "report_trend_empty_message": "这是你第一次留下面试记录，多来几次就能看到自己的进步曲线啦。",
        # ---------- Async report generation (post-roadmap, decision #47) ----------
        # Shown on the interview_ended page while end_interview_async()'s
        # background worker is still running (see
        # backend/conversation/session_adapter.py's ReportGenerationHandle).
        "report_generating_spinner_label": "报告生成中，请稍候…",
        # ---------- History / past reports page (post-roadmap, decision #47) ----------
        "history_nav_button": "📋 历史面试记录",
        "history_page_heading": "历史面试记录",
        "history_back_button": "← 返回",
        "history_empty_message": "还没有历史面试记录，去开始你的第一次模拟面试吧。",
        "history_no_score_label": "未生成报告",
        "history_view_button": "查看",
        "history_report_unavailable_message": "这条记录暂时没有可查看的报告。",
        # ---------- Voice input/output (Week 11) ----------
        "interview_audio_label": "或者，录音回答",
        "interview_voice_asr_error": "语音识别失败，可以直接打字回答。",
        # ---------- Interview input-mode preference dialog (Week 11 followup) ----------
        # Shown once, right before the interview starts. Only sets an
        # initial default -- both text and voice input stay available every
        # round afterward (decision #39 is unchanged; this doesn't lock the
        # session to one mode).
        "interview_mode_dialog_title": "对话方式",
        "interview_mode_dialog_body": (
            "接下来的模拟面试，你想怎么回答？这只是帮你设置一个默认方式，"
            "面试过程中随时可以自由切换文字或语音。"
        ),
        "interview_mode_voice_button": "🎙️ 语音对话",
        "interview_mode_text_button": "⌨️ 打字回答",
        "interview_voice_expander_label": "🎙️ 改用语音回答",
        "interview_mode_hint_voice": "默认：语音对话 · 你也可以随时打字回答",
        "interview_mode_hint_text": "默认：打字回答 · 你也可以随时展开语音回答",
        # ---------- Realtime feedback (Week 10) ----------
        "realtime_feedback_title": "💬 本轮反馈（可点击收起）",
        "realtime_feedback_content_label": "内容反馈",
        "realtime_feedback_expression_label": "表达建议",
        # ---------- Login / Register (Week 14) ----------
        # Gates every other page (decision #43) -- session-only, no
        # cross-refresh persistence; see backend/storage/user_db.py for the
        # username/password rules these error messages describe.
        "auth_page_title": "登录 / 注册",
        "auth_page_body": "登录后就能看到你的历史面试记录和分数趋势。",
        "auth_mode_label": "登录还是注册",
        "auth_login_tab": "登录",
        "auth_register_tab": "注册",
        "auth_username_label": "用户名",
        "auth_password_label": "密码",
        "auth_confirm_password_label": "确认密码",
        "auth_login_button": "登录",
        "auth_register_button": "注册",
        "auth_register_success": "注册成功，已自动登录",
        "auth_logout_button": "退出登录",
        "auth_error_invalid_credentials": "用户名或密码错误",
        "auth_error_username_taken": "该用户名已被注册，换一个试试",
        "auth_error_password_mismatch": "两次输入的密码不一致",
        # Numbers below must match backend/storage/user_db.py's
        # MIN_USERNAME_LENGTH/MAX_USERNAME_LENGTH/MIN_PASSWORD_LENGTH.
        "auth_error_username_too_short": "用户名至少需要3个字符",
        "auth_error_username_too_long": "用户名最多30个字符",
        "auth_error_password_too_short": "密码至少需要6位",
        "auth_error_invalid_input": "输入不合法，请检查后重试",
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
        "lang_name_zh": "中文",
        "lang_name_en": "English",
        # ---------- Onboarding (welcome page, Week 8) ----------
        "onboarding_welcome_title": "Welcome to AI Interview Coach",
        "onboarding_welcome_body": (
            "We'll ask three quick questions to understand your interview "
            "scenario, then match you with a dedicated AI interviewer and "
            "difficulty level. First, take a few seconds to set your "
            "language and interface style."
        ),
        "onboarding_language_label": "Choose your language",
        "onboarding_font_label": "Choose an interface style",
        "onboarding_font_friendly_name": "Warm & Rounded",
        "onboarding_font_friendly_desc": "A warm, relaxed look with rounded type -- good for easing into practice.",
        "onboarding_font_professional_name": "Professional & Serious",
        "onboarding_font_professional_desc": "A composed serif look closer to the tone of a formal interview.",
        "onboarding_start_button": "Get Started",
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
        "triage_page_heading": "Let's Understand Your Interview Scenario",
        "triage_progress_prefix": "Question",
        "triage_next_button": "Next",
        "triage_finish_button": "Finish",
        # ---------- Result ----------
        "result_heading": "Your Matched Scenario",
        "result_subtitle": "Based on your triage answers, here's the scenario we matched you with",
        "result_job_type_label": "Job Type",
        "result_stage_label": "Interview Stage",
        "result_difficulty_label": "Difficulty",
        "result_persona_label": "Interviewer Persona",
        "session_saved_message": "This matched scenario has been saved",
        "session_id_label": "Session ID",
        "interview_start_button": "Start Interview",
        # ---------- Interview (Week 9) ----------
        "interview_page_heading": "Mock Interview In Progress",
        "interview_end_button": "End Interview",
        "interview_answer_placeholder": "Type your answer...",
        "interview_ended_heading": "Interview Ended",
        "interview_ended_message": "This session's Q&A record has been saved",
        # ---------- Review report (Week 15) ----------
        "report_page_heading": "Review Report",
        "report_overall_score_label": "Overall Score",
        "report_no_scoreable_topics_message": (
            "You haven't fully answered a main question yet this session, so there's nothing to score yet."
        ),
        "report_ai_highlight_title": "🌟 AI Highlight Moment",
        "report_topics_heading": "Question-by-Question Breakdown",
        "report_dimension_structure": "Structural Completeness",
        "report_dimension_keyword": "Keyword Coverage",
        "report_dimension_logical": "Logical Coherence",
        "report_dimension_specificity": "Specificity",
        "report_voice_summary_title": "🎙️ Voice Performance",
        "report_text_corrections_title": "✏️ Wording Suggestions",
        "report_trend_title": "📈 Progress Over Time",
        "report_trend_empty_message": (
            "This is your first recorded interview -- come back after a few more to see your progress trend."
        ),
        # ---------- Async report generation (post-roadmap, decision #47) ----------
        "report_generating_spinner_label": "Generating your report…",
        # ---------- History / past reports page (post-roadmap, decision #47) ----------
        "history_nav_button": "📋 Interview History",
        "history_page_heading": "Interview History",
        "history_back_button": "← Back",
        "history_empty_message": "No interview history yet -- go start your first mock interview!",
        "history_no_score_label": "No report",
        "history_view_button": "View",
        "history_report_unavailable_message": "No report is available for this session yet.",
        # ---------- Voice input/output (Week 11) ----------
        "interview_audio_label": "Or, record your answer",
        "interview_voice_asr_error": "Speech recognition failed -- feel free to just type your answer instead.",
        # ---------- Interview input-mode preference dialog (Week 11 followup) ----------
        "interview_mode_dialog_title": "How would you like to answer?",
        "interview_mode_dialog_body": (
            "This just sets a default for the mock interview -- you can "
            "freely switch between typing and talking at any point."
        ),
        "interview_mode_voice_button": "🎙️ Talk",
        "interview_mode_text_button": "⌨️ Type",
        "interview_voice_expander_label": "🎙️ Switch to voice",
        "interview_mode_hint_voice": "Default: voice -- you can type anytime too",
        "interview_mode_hint_text": "Default: typing -- you can expand voice input anytime",
        # ---------- Realtime feedback (Week 10) ----------
        "realtime_feedback_title": "💬 Feedback on this round (click to collapse)",
        "realtime_feedback_content_label": "Content feedback",
        "realtime_feedback_expression_label": "Expression suggestions",
        # ---------- Login / Register (Week 14) ----------
        "auth_page_title": "Log In / Sign Up",
        "auth_page_body": "Log in to see your past interviews and score trends.",
        "auth_mode_label": "Log in or sign up",
        "auth_login_tab": "Log In",
        "auth_register_tab": "Sign Up",
        "auth_username_label": "Username",
        "auth_password_label": "Password",
        "auth_confirm_password_label": "Confirm Password",
        "auth_login_button": "Log In",
        "auth_register_button": "Sign Up",
        "auth_register_success": "Account created -- you're logged in",
        "auth_logout_button": "Log Out",
        "auth_error_invalid_credentials": "Incorrect username or password",
        "auth_error_username_taken": "That username is already taken -- try another",
        "auth_error_password_mismatch": "Passwords don't match",
        "auth_error_username_too_short": "Username must be at least 3 characters",
        "auth_error_username_too_long": "Username must be at most 30 characters",
        "auth_error_password_too_short": "Password must be at least 6 characters",
        "auth_error_invalid_input": "Invalid input -- please check and try again",
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
