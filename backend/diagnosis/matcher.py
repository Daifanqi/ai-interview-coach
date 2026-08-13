"""
AI Interview System - Triage Module: Scenario Matcher

match_scenario() is the single entry point the frontend questionnaire page
calls after the user submits their answers. It is a thin orchestration layer:
all difficulty math stays in difficulty.py (compute_difficulty), this module
is only responsible for (1) validating job_type, which difficulty.py knows
nothing about, and (2) assembling the full ScenarioConfig the rest of the
app consumes.

See docs/decision_log.md decision 11: difficulty is not a unique key --
the same final_difficulty can arise from different (experience, stage)
combinations with different personas, so downstream modules (dialogue
engine, question-bank retrieval) must key off (difficulty, persona, stage)
together, never difficulty alone. ScenarioConfig always carries all three.
"""
from dataclasses import dataclass

from backend.diagnosis.difficulty import compute_difficulty
from backend.diagnosis.questionnaire import JOB_TYPES, QuestionnaireAnswers
from models.session_schema import ExperienceLevel, InterviewStage, SessionConfig

# Translation tables from the questionnaire's Chinese vocabulary to the
# English enums used by models.session_schema.SessionConfig. Kept here
# (rather than in session_schema.py) because this mapping is specifically
# about interpreting *questionnaire answers* -- session_schema.py itself
# should stay free of any dependency on how the triage UI phrases things.
_EXPERIENCE_TO_ENUM = {
    "实习生": ExperienceLevel.INTERN,
    "应届": ExperienceLevel.JUNIOR,
    "1-3年": ExperienceLevel.MID,
    "3年以上": ExperienceLevel.SENIOR,
}

_STAGE_TO_ENUM = {
    "HR初筛": InterviewStage.HR_SCREEN,
    "技术面①": InterviewStage.TECH_ROUND_1,
    "技术面②": InterviewStage.TECH_ROUND_2,
    "终面": InterviewStage.FINAL,
}


@dataclass
class ScenarioConfig:
    """
    Full result of triage matching for one questionnaire submission.

    job_type is carried through for future question-bank filtering only
    (see questionnaire.py note) -- it plays no part in difficulty/persona.
    """

    job_type: str
    experience: str
    stage: str
    difficulty: int
    persona: str
    persona_css: str
    base_difficulty: int
    difficulty_adjustment: int
    was_clamped: bool


def match_scenario(answers: QuestionnaireAnswers) -> ScenarioConfig:
    """
    Turn raw questionnaire answers into a ScenarioConfig.

    Raises ValueError if job_type is not one of the known options, or if
    experience/stage are invalid (bubbled up from compute_difficulty's own
    validation, so error messages stay defined in exactly one place).
    """
    job_type = answers["job_type"]
    if job_type not in JOB_TYPES:
        raise ValueError(f"未知岗位类型: {job_type}，请从 {JOB_TYPES} 中选择")

    result = compute_difficulty(answers["experience"], answers["stage"])

    return ScenarioConfig(
        job_type=job_type,
        experience=result["experience"],
        stage=result["stage"],
        difficulty=result["final_difficulty"],
        persona=result["persona"],
        persona_css=result["persona_css"],
        base_difficulty=result["base"],
        difficulty_adjustment=result["adjustment"],
        was_clamped=result["was_clamped"],
    )


def to_session_config(
    scenario: ScenarioConfig,
    language: str = "zh",
    target_company: str | None = None,
) -> SessionConfig:
    """
    Build the SessionConfig handed off to the dialogue engine / storage layer.

    Kept separate from match_scenario() so the frontend can inspect/display
    a ScenarioConfig (e.g. render the difficulty badge + persona tag) before
    committing to a SessionConfig, which additionally requires `language`
    (see strings.py) and an optional target_company that the questionnaire
    itself does not collect.
    """
    return SessionConfig(
        job_type=scenario.job_type,
        experience_level=_EXPERIENCE_TO_ENUM[scenario.experience],
        interview_stage=_STAGE_TO_ENUM[scenario.stage],
        target_company=target_company,
        difficulty=scenario.difficulty,
        interviewer_persona=scenario.persona,
        language=language,
    )
