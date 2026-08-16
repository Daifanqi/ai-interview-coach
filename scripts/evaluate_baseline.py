"""
Baseline scoring accuracy evaluation.

Runs backend/scoring/baseline.py's score_answer() over every human-reviewed
label (status == "scored") in data/labeled_answers_human_reviewed.json and
compares the four raw dimension scores it produces against each record's
human_scores, to answer the question docs/decision_log.md decision 23
left open: how close is the baseline's (still-uncalibrated, see
baseline.py's module docstring) scoring heuristic to human judgment, and
are the two decision-22 protective mechanisms (specificity floor,
keyword-stuffing warning) firing at a sane rate on real data rather than
never firing or firing on nearly everything.

Question lookups are resolved against BOTH data/sample_questions.json
(the original 30-question set decisions 23/27/29 were evaluated against)
and data/question_bank.json (the 200-question job-type-segmented RAG bank,
decisions 24/25) -- week 16 (decision 45) found the labeled-answers file
had grown from 150 to 200 scored records without evaluate_baseline.py
being updated to match, so the extra 50 records (job-type-prefixed
question_ids like "tech_behavioral_01", only present in question_bank.json)
crashed with a KeyError until this was fixed. The two question sources
have no question_id overlap, so a plain dict merge is safe.

Usage:
    python scripts/evaluate_baseline.py

Writes results/baseline_accuracy.md. Requires the sentence-transformers
embedding model (backend/scoring/embedding.py) to be loadable, since
score_answer() embeds every answer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.scoring.baseline import score_answer  # noqa: E402
from models.question_schema import load_questions_from_json  # noqa: E402

LABELED_ANSWERS_PATH = PROJECT_ROOT / "data" / "labeled_answers_human_reviewed.json"
QUESTIONS_PATH = PROJECT_ROOT / "data" / "sample_questions.json"
QUESTION_BANK_PATH = PROJECT_ROOT / "data" / "question_bank.json"
OUTPUT_PATH = PROJECT_ROOT / "results" / "baseline_accuracy.md"

DIMENSIONS = ("structure_completeness", "keyword_coverage", "logical_coherence", "specificity")
DIMENSION_LABELS = {
    "structure_completeness": "Structure completeness",
    "keyword_coverage": "Keyword coverage",
    "logical_coherence": "Logical coherence",
    "specificity": "Specificity",
}
QUESTION_TYPES = ("behavioral", "technical", "case_analysis")
QUESTION_TYPE_LABELS = {
    "behavioral": "Behavioral",
    "technical": "Technical",
    "case_analysis": "Case analysis",
}
# Tolerance bands the task asks for, in points on the 0-10 scale.
TOLERANCE_BANDS = (1.0, 2.0)
TOP_N_WORST = 10

# Frozen snapshot of keyword_coverage's accuracy from the run right before
# docs/decision_log.md decision 29 (exact-substring cluster matching,
# replaced by embedding-based semantic matching in
# backend/scoring/baseline.py's _score_keyword_coverage()). Kept here only
# so render_keyword_coverage_fix_comparison() can render a permanent
# before/after table in section 6 -- it is historical data, not
# recomputed, and is intentionally not wired into evaluate()/main()'s live
# scoring path.
PRE_FIX_KEYWORD_COVERAGE_STATS = {
    "overall": {"n": 150, "mae": 3.59, "within_1": 0.23, "within_2": 0.31},
    "behavioral": {"n": 50, "mae": 4.60, "within_1": 0.18, "within_2": 0.20},
    "technical": {"n": 50, "mae": 2.14, "within_1": 0.30, "within_2": 0.52},
    "case_analysis": {"n": 50, "mae": 4.03, "within_1": 0.20, "within_2": 0.22},
}
PRE_FIX_KEYWORD_STUFFING_WARNINGS = {
    "behavioral": 0,
    "technical": 0,
    "case_analysis": 0,
    "overall": 0,
}


def load_labeled_answers() -> list[dict]:
    """Load the human-reviewed labels, skipping any record not yet fully scored."""
    with LABELED_ANSWERS_PATH.open(encoding="utf-8") as f:
        records = json.load(f)
    scored = [r for r in records if r["status"] == "scored"]
    if len(scored) != len(records):
        print(f"Warning: skipping {len(records) - len(scored)} non-'scored' record(s) out of {len(records)}.")
    return scored


def load_all_questions() -> dict:
    """Merge data/sample_questions.json (the original 30) and data/question_bank.json (the 200-question
    job-type-segmented RAG bank) into one question_id -> Question lookup -- see module docstring."""
    questions = {q.question_id: q for q in load_questions_from_json(QUESTIONS_PATH)}
    questions.update({q.question_id: q for q in load_questions_from_json(QUESTION_BANK_PATH)})
    return questions


def evaluate() -> list[dict]:
    """Run baseline scoring on every labeled answer, pairing it with the human scores and protective-mechanism flags."""
    questions = load_all_questions()
    records = load_labeled_answers()

    evaluated = []
    for record in records:
        question = questions[record["question_id"]]
        report = score_answer(record["answer_text"], question)

        baseline_scores = {dim: report[dim]["score"] for dim in DIMENSIONS}
        human_scores = record["human_scores"]
        abs_errors = {dim: abs(baseline_scores[dim] - human_scores[dim]) for dim in DIMENSIONS}

        evaluated.append(
            {
                "review_id": record["review_id"],
                "question_id": record["question_id"],
                "question_type": question.question_type,
                "score_band": record["score_band"],
                "baseline_scores": baseline_scores,
                "human_scores": human_scores,
                "abs_errors": abs_errors,
                "mean_abs_error": sum(abs_errors.values()) / len(DIMENSIONS),
                "score_ceiling_applied": report["score_ceiling_applied"],
                "keyword_stuffing_warning": report["keyword_stuffing_warning"],
            }
        )
    return evaluated


def compute_dimension_stats(evaluated: list[dict], dim: str) -> dict:
    """MAE plus ±1/±2-point tolerance accuracy for one dimension over a set of evaluated records."""
    errors = [r["abs_errors"][dim] for r in evaluated]
    n = len(errors)
    return {
        "n": n,
        "mae": sum(errors) / n,
        "within": {band: sum(1 for e in errors if e <= band) / n for band in TOLERANCE_BANDS},
    }


def render_stats_table(evaluated: list[dict], include_n: bool) -> str:
    header = "| Dimension |" + (" N |" if include_n else "") + " MAE | Accuracy (±1) | Accuracy (±2) |"
    sep = "| --- |" + (" --- |" if include_n else "") + " --- | --- | --- |"
    lines = [header, sep]
    for dim in DIMENSIONS:
        stats = compute_dimension_stats(evaluated, dim)
        n_cell = f" {stats['n']} |" if include_n else ""
        lines.append(
            f"| {DIMENSION_LABELS[dim]} |{n_cell} {stats['mae']:.2f} | "
            f"{stats['within'][1.0]:.0%} | {stats['within'][2.0]:.0%} |"
        )
    return "\n".join(lines)


def render_by_question_type(evaluated: list[dict]) -> str:
    sections = []
    for qtype in QUESTION_TYPES:
        subset = [r for r in evaluated if r["question_type"] == qtype]
        if not subset:
            continue
        sections.append(f"### {QUESTION_TYPE_LABELS[qtype]} (n={len(subset)})\n\n{render_stats_table(subset, include_n=False)}")
    return "\n\n".join(sections)


def render_worst_records(evaluated: list[dict]) -> str:
    """Ten records with the largest mean absolute error across the four dimensions, all four dimensions shown per record."""
    worst = sorted(evaluated, key=lambda r: r["mean_abs_error"], reverse=True)[:TOP_N_WORST]
    lines = [
        "| Rank (mean err) | review_id | Type | Target band | Dimension | Baseline | Human | Abs error |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rank, record in enumerate(worst, start=1):
        # Largest-error dimension first within each record, so the single
        # biggest miss is visible even though ranking is by the record's mean.
        dims_sorted = sorted(DIMENSIONS, key=lambda d: record["abs_errors"][d], reverse=True)
        for i, dim in enumerate(dims_sorted):
            rank_cell = f"{rank} ({record['mean_abs_error']:.2f})" if i == 0 else ""
            id_cell = record["review_id"] if i == 0 else ""
            type_cell = QUESTION_TYPE_LABELS[record["question_type"]] if i == 0 else ""
            band_cell = record["score_band"] if i == 0 else ""
            lines.append(
                f"| {rank_cell} | {id_cell} | {type_cell} | {band_cell} | {DIMENSION_LABELS[dim]} | "
                f"{record['baseline_scores'][dim]:.1f} | {record['human_scores'][dim]:.1f} | "
                f"{record['abs_errors'][dim]:.2f} |"
            )
    return "\n".join(lines)


def render_protective_mechanisms(evaluated: list[dict]) -> str:
    lines = [
        "| Question type | N | Specificity-floor ceiling applied | Keyword-stuffing warning |",
        "| --- | --- | --- | --- |",
    ]
    for qtype in QUESTION_TYPES:
        subset = [r for r in evaluated if r["question_type"] == qtype]
        if not subset:
            continue
        ceiling_count = sum(1 for r in subset if r["score_ceiling_applied"])
        stuffing_count = sum(1 for r in subset if r["keyword_stuffing_warning"])
        lines.append(
            f"| {QUESTION_TYPE_LABELS[qtype]} | {len(subset)} | "
            f"{ceiling_count} ({ceiling_count / len(subset):.0%}) | "
            f"{stuffing_count} ({stuffing_count / len(subset):.0%}) |"
        )
    n = len(evaluated)
    total_ceiling = sum(1 for r in evaluated if r["score_ceiling_applied"])
    total_stuffing = sum(1 for r in evaluated if r["keyword_stuffing_warning"])
    lines.append(
        f"| **Total** | {n} | **{total_ceiling}** ({total_ceiling / n:.0%}) | "
        f"**{total_stuffing}** ({total_stuffing / n:.0%}) |"
    )
    return "\n".join(lines)


def render_keyword_coverage_fix_comparison(evaluated: list[dict]) -> str:
    """Before (exact-substring matching) vs after (embedding-based semantic matching, decision 29) for keyword_coverage."""
    groups = {
        "overall": evaluated,
        "behavioral": [r for r in evaluated if r["question_type"] == "behavioral"],
        "technical": [r for r in evaluated if r["question_type"] == "technical"],
        "case_analysis": [r for r in evaluated if r["question_type"] == "case_analysis"],
    }
    group_labels = {
        "overall": "**Overall**",
        "behavioral": "Behavioral",
        "technical": "Technical",
        "case_analysis": "Case analysis",
    }

    lines = [
        "| Question type | MAE before | MAE after | Accuracy (±1) before | Accuracy (±1) after | Accuracy (±2) before | Accuracy (±2) after |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in ("overall", "behavioral", "technical", "case_analysis"):
        before = PRE_FIX_KEYWORD_COVERAGE_STATS[key]
        after = compute_dimension_stats(groups[key], "keyword_coverage")
        lines.append(
            f"| {group_labels[key]} | {before['mae']:.2f} | {after['mae']:.2f} | "
            f"{before['within_1']:.0%} | {after['within'][1.0]:.0%} | "
            f"{before['within_2']:.0%} | {after['within'][2.0]:.0%} |"
        )

    stuffing_lines = [
        "",
        "Keyword-stuffing warning trigger count, before vs after (same 150 records; this mechanism reads "
        "keyword_coverage's score directly, so it only became able to fire once keyword_coverage stopped "
        "systematically under-scoring real answers):",
        "",
        "| Question type | N | Warnings before | Warnings after |",
        "| --- | --- | --- | --- |",
    ]
    for qtype in QUESTION_TYPES:
        subset = [r for r in evaluated if r["question_type"] == qtype]
        after_count = sum(1 for r in subset if r["keyword_stuffing_warning"])
        stuffing_lines.append(
            f"| {QUESTION_TYPE_LABELS[qtype]} | {len(subset)} | "
            f"{PRE_FIX_KEYWORD_STUFFING_WARNINGS[qtype]} | {after_count} |"
        )
    total_after = sum(1 for r in evaluated if r["keyword_stuffing_warning"])
    stuffing_lines.append(
        f"| **Total** | {len(evaluated)} | **{PRE_FIX_KEYWORD_STUFFING_WARNINGS['overall']}** | **{total_after}** |"
    )

    return "\n".join(lines) + "\n" + "\n".join(stuffing_lines)


def render_report(evaluated: list[dict]) -> str:
    return f"""# Baseline Scoring Accuracy Evaluation

Evaluates `backend/scoring/baseline.py`'s `score_answer()` against all
{len(evaluated)} human-reviewed labels in
`data/labeled_answers_human_reviewed.json` (questions from
`data/sample_questions.json`). See `docs/decision_log.md` decision 23 for
why this evaluation was blocked until the human review pass landed, and
decision 22 for the two protective mechanisms whose trigger rates are
checked in section 5.

Generated by `scripts/evaluate_baseline.py`.

## 1-2. Overall accuracy (all question types combined)

{render_stats_table(evaluated, include_n=True)}

MAE = mean absolute error on the 0-10 scale. Accuracy (±1) / (±2) = share of
records where the baseline score falls within 1 / 2 points of the human
score.

## 3. Accuracy by question type

Baseline scoring logic differs per question type (structure elements,
dimension weights -- see `backend/scoring/baseline.py` and
`backend/scoring/report.py`'s `DIMENSION_WEIGHTS`), so this checks whether
accuracy holds up across all three types rather than being an aggregate
that hides one weak type.

{render_by_question_type(evaluated)}

## 4. Ten largest-error records

Ranked by mean absolute error across the four dimensions per record; all
four dimensions are listed per record (largest error first) for manual
root-cause analysis.

{render_worst_records(evaluated)}

## 5. Protective mechanism trigger rates

Two decision-22 safeguards, applied in `backend/scoring/report.py`'s
`build_score_report()`:

- **Specificity-floor ceiling**: specificity score < 3 caps the overall
  score at 50% of max.
- **Keyword-stuffing warning**: keyword coverage >= 7 AND specificity <= 4
  flags the answer for manual review.

{render_protective_mechanisms(evaluated)}

## 6. Keyword-coverage fix: before vs after (decision 29)

`_score_keyword_coverage()` originally required an exact substring match
against a keyword cluster's canonical term or synonyms ("before" below).
docs/decision_log.md decision 29 replaced that with embedding-based
semantic similarity matching (cosine similarity >= 0.37, picked by grid
search against these same 150 records -- see
`backend/scoring/baseline.py`'s `_KEYWORD_SIMILARITY_THRESHOLD` comment),
so a natural paraphrase of a keyword cluster is credited instead of only
its exact wording.

{render_keyword_coverage_fix_comparison(evaluated)}
"""


def main() -> None:
    evaluated = evaluate()
    report = render_report(evaluated)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Evaluated {len(evaluated)} labeled answers -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
