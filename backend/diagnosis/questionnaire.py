"""
AI Interview System - Triage Module: Questionnaire Definitions

Defines the raw questionnaire options collected on the triage page (Q1 job
type, Q2 experience level, Q3 interview stage).

Design notes:
- The `value` of each option for "experience" and "stage" is the exact same
  Chinese string used as dict keys in difficulty.py (EXPERIENCE_BASE /
  STAGE_CONFIG). This keeps the questionnaire and the difficulty engine in
  lockstep -- there is a single source of truth for these vocabularies, and
  matcher.py can pass answers straight into compute_difficulty() without any
  translation/mapping layer.
- Each option also carries a `label_key`, which is a lookup key into
  frontend/strings.py (STRINGS["zh"|"en"]). The *value* (used as the
  matching key) and the *label* (what the user sees, bilingual) are
  deliberately kept separate so the UI can be localized without touching the
  difficulty computation logic at all.
"""
from typing import Literal, TypedDict


# ---------- Q1: Job type ----------
# NOTE (v1 scope): job type does NOT participate in difficulty computation.
# See backend/diagnosis/difficulty.py -- EXPERIENCE_BASE / STAGE_CONFIG have
# no notion of job type. It is collected here purely so it can be attached to
# ScenarioConfig / SessionConfig for a *future* question-bank filtering step
# (e.g. backend/rag retrieval keyed by job type). Do not wire it into
# compute_difficulty() without an explicit follow-up design decision.
JOB_TYPES = [
    "技术",
    "产品",
    "市场营销",
    "运营",
    "设计",
    "咨询",
    "金融",
]

JobType = Literal["技术", "产品", "市场营销", "运营", "设计", "咨询", "金融"]

# ---------- Q2: Experience level ----------
# Values must match difficulty.EXPERIENCE_BASE keys exactly.
EXPERIENCE_LEVELS = ["实习生", "应届", "1-3年", "3年以上"]

# ---------- Q3: Interview stage ----------
# Values must match difficulty.STAGE_CONFIG keys exactly.
INTERVIEW_STAGES = ["HR初筛", "技术面①", "技术面②", "终面"]


class QuestionOption(TypedDict):
    value: str  # canonical value, also the key used by difficulty.py where applicable
    label_key: str  # lookup key into frontend/strings.py STRINGS[lang]


class Question(TypedDict):
    id: str  # answers dict key, consumed by matcher.match_scenario()
    label_key: str  # question prompt, lookup key into frontend/strings.py
    options: list[QuestionOption]


# ---------- Full questionnaire schema, in display order ----------
# Consumed by frontend/app.py to render the form generically: for each
# question, render `label_key` as the prompt and `options` as the choices,
# resolving every piece of text through strings.t(label_key) at render time.
QUESTIONNAIRE: list[Question] = [
    {
        "id": "job_type",
        "label_key": "q_job_type_label",
        "options": [
            {"value": "技术", "label_key": "opt_job_tech"},
            {"value": "产品", "label_key": "opt_job_product"},
            {"value": "市场营销", "label_key": "opt_job_marketing"},
            {"value": "运营", "label_key": "opt_job_ops"},
            {"value": "设计", "label_key": "opt_job_design"},
            {"value": "咨询", "label_key": "opt_job_consulting"},
            {"value": "金融", "label_key": "opt_job_finance"},
        ],
    },
    {
        "id": "experience",
        "label_key": "q_experience_label",
        "options": [
            {"value": "实习生", "label_key": "opt_exp_intern"},
            {"value": "应届", "label_key": "opt_exp_junior"},
            {"value": "1-3年", "label_key": "opt_exp_mid"},
            {"value": "3年以上", "label_key": "opt_exp_senior"},
        ],
    },
    {
        "id": "stage",
        "label_key": "q_stage_label",
        "options": [
            {"value": "HR初筛", "label_key": "opt_stage_hr"},
            {"value": "技术面①", "label_key": "opt_stage_tech1"},
            {"value": "技术面②", "label_key": "opt_stage_tech2"},
            {"value": "终面", "label_key": "opt_stage_final"},
        ],
    },
]


class QuestionnaireAnswers(TypedDict):
    """Shape of the answers dict passed into matcher.match_scenario()."""

    job_type: str
    experience: str
    stage: str
