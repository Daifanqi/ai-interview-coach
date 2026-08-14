"""
Structured output format for baseline scoring (backend/scoring/baseline.py),
plus the parts of docs/scoring_rubric.md that are about *assembling* a
final report rather than about analyzing an individual answer:

- The per-question-type dimension weight table (rubric section 4).
- The three protective mechanisms finalized in docs/decision_log.md
  decision 22, applied here as report-level post-processing over four
  already-computed dimension scores:
    1. Minimum-score floor: specificity < 3 caps the overall score at 50%.
    2. Keyword-stuffing linkage flag: high keyword coverage + low
       specificity gets flagged for manual review.
    3. A fixed "scores are only comparable within the same question_type"
       caveat carried on every report, for the frontend to display.

baseline.py owns *how* each dimension's score is derived from answer text;
this module owns *what a finished report looks like* once those four
numbers exist. Keeping that split means the safeguards above are testable
independent of the (heavier, model-dependent) scoring heuristics.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.question_schema import Question, QuestionType

# ---------------------------------------------------------------------------
# Dimension weights (docs/scoring_rubric.md section 4)
# ---------------------------------------------------------------------------

DIMENSION_NAMES = ("structure_completeness", "keyword_coverage", "logical_coherence", "specificity")

# Weights sum to 1.0 within each question_type -- copied verbatim from the
# rubric's "三套权重方案建议" table.
DIMENSION_WEIGHTS: dict[QuestionType, dict[str, float]] = {
    "behavioral": {
        "structure_completeness": 0.35,
        "keyword_coverage": 0.15,
        "logical_coherence": 0.15,
        "specificity": 0.35,
    },
    "technical": {
        "structure_completeness": 0.15,
        "keyword_coverage": 0.25,
        "logical_coherence": 0.30,
        "specificity": 0.30,
    },
    "case_analysis": {
        "structure_completeness": 0.30,
        "keyword_coverage": 0.15,
        "logical_coherence": 0.30,
        "specificity": 0.25,
    },
}

# ---------------------------------------------------------------------------
# Protective mechanism thresholds (docs/decision_log.md decision 22)
# ---------------------------------------------------------------------------

# Mechanism 1: specificity dimension score (0-10) below this floor caps the
# overall score at 50% of the max (5.0 on the 0-10 scale) -- decision 22
# point 1, guarding against "well-structured but fabricated" answers scoring
# artificially high via the other three dimensions.
SPECIFICITY_FLOOR_THRESHOLD = 3.0
OVERALL_SCORE_MAX = 10.0
OVERALL_SCORE_CEILING_UNDER_FLOOR = OVERALL_SCORE_MAX * 0.5

# Mechanism 2: keyword coverage >= this AND specificity <= this together
# flag "suspected keyword stuffing" for manual review (decision 22 point 2).
# Thresholds correspond to the rubric's "7-8" (high) and "3-4" (low) score
# bands respectively (docs/scoring_rubric.md sections 3.2 / 3.4).
KEYWORD_STUFFING_COVERAGE_THRESHOLD = 7.0
KEYWORD_STUFFING_SPECIFICITY_THRESHOLD = 4.0

# Mechanism 3: fixed caveat every report carries, for the frontend to render
# next to any displayed score (decision 22 point 3).
CROSS_QUESTION_TYPE_CAVEAT = (
    "分数仅题型内可比：行为题、技术题、案例分析题使用不同的评分权重和标准，"
    "不同题型之间的分数不能直接比较高低。"
)


@dataclass
class DimensionScore:
    """One dimension's result: a 0-10 score (5 bands per docs/scoring_rubric.md) plus a human-readable explanation."""

    score: float
    explanation: str


@dataclass
class ScoreReport:
    """The full structured output of backend/scoring/baseline.py's score_answer()."""

    question_id: str
    question_type: QuestionType
    job_type: str | None

    structure_completeness: DimensionScore
    keyword_coverage: DimensionScore
    logical_coherence: DimensionScore
    specificity: DimensionScore

    # Weighted sum of the four dimension scores per DIMENSION_WEIGHTS,
    # before the minimum-score floor (mechanism 1) is applied.
    overall_score_raw: float
    # overall_score_raw, capped by mechanism 1 if triggered. This is the
    # number that should actually be shown to the user.
    overall_score: float
    score_ceiling_applied: bool  # True if mechanism 1's floor capped overall_score

    keyword_stuffing_warning: bool  # True if mechanism 2's linkage check tripped
    cross_question_type_note: str = CROSS_QUESTION_TYPE_CAVEAT


def compute_weighted_overall(dimension_scores: dict[str, float], question_type: QuestionType) -> float:
    """Weighted sum of the four dimension scores using DIMENSION_WEIGHTS[question_type]."""
    weights = DIMENSION_WEIGHTS[question_type]
    return sum(dimension_scores[name] * weights[name] for name in DIMENSION_NAMES)


def build_score_report(
    question: Question,
    structure_completeness: DimensionScore,
    keyword_coverage: DimensionScore,
    logical_coherence: DimensionScore,
    specificity: DimensionScore,
) -> ScoreReport:
    """
    Assemble a ScoreReport from four already-computed DimensionScores,
    applying the weighting and the two numeric safeguards from decision 22.
    """
    raw_scores = {
        "structure_completeness": structure_completeness.score,
        "keyword_coverage": keyword_coverage.score,
        "logical_coherence": logical_coherence.score,
        "specificity": specificity.score,
    }
    overall_raw = compute_weighted_overall(raw_scores, question.question_type)

    ceiling_applied = specificity.score < SPECIFICITY_FLOOR_THRESHOLD
    overall = min(overall_raw, OVERALL_SCORE_CEILING_UNDER_FLOOR) if ceiling_applied else overall_raw

    stuffing_warning = (
        keyword_coverage.score >= KEYWORD_STUFFING_COVERAGE_THRESHOLD
        and specificity.score <= KEYWORD_STUFFING_SPECIFICITY_THRESHOLD
    )

    return ScoreReport(
        question_id=question.question_id,
        question_type=question.question_type,
        job_type=question.job_type,
        structure_completeness=structure_completeness,
        keyword_coverage=keyword_coverage,
        logical_coherence=logical_coherence,
        specificity=specificity,
        overall_score_raw=round(overall_raw, 2),
        overall_score=round(overall, 2),
        score_ceiling_applied=ceiling_applied,
        keyword_stuffing_warning=stuffing_warning,
    )
