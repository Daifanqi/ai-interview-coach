"""
Grid-search calibration for backend/scoring/baseline.py's specificity
dimension (_score_specificity()), analogous to docs/decision_log.md
decision 29's keyword_coverage threshold grid search.

Background: decision 27's accuracy evaluation found specificity was the
second-worst-performing dimension (MAE 2.27, +/-1 accuracy 36%) of the
four. Decision 45 (week 16) widened the fixed marker-word list and added a
proper-noun/tool-name regex signal (_count_proper_noun_markers()) on top of
the existing marker-density + reference-point-similarity blend, but left
_SPECIFICITY_MARKER_WEIGHT and _EXPECTED_MARKER_DENSITY at their original
reasoned-but-unvalidated placeholder values (0.5 / 0.5). This script
re-picks both against the same 150 human-reviewed records decision 29 used,
the same way decision 29 did: embed each record once, then grid-search the
two parameters purely arithmetically (cheap -- no re-embedding per grid
point) and print the MAE / tolerance-accuracy surface so a combination can
be picked with reasoning (is it a plateau or a knife-edge single-point
peak? decision 29 explicitly checked this before committing to its own
threshold) rather than blindly taking the single best cell.

Caveat this script does NOT resolve on its own (state honestly, don't
gloss over it): both this grid search and decision 29's original one tune
against the same 150 records evaluate_baseline.py's accuracy numbers are
reported on -- there is no held-out split. A combination that looks best
here is at least partly fit to this exact dataset, not proven to
generalize. Treat the result as a reasoned improvement over the untuned
0.5/0.5 starting point, not as a validated final answer; a future dataset
expansion (data/labeled_answers_draft_batch2.json, still unreviewed per
decision 30) would be the right place to confirm it holds out of sample.

Usage:
    python scripts/calibrate_specificity.py

Requires the sentence-transformers embedding model to be loadable (same
prerequisite as scripts/evaluate_baseline.py). Prints a markdown grid to
stdout; does NOT modify backend/scoring/baseline.py -- after picking a
combination, update _SPECIFICITY_MARKER_WEIGHT / _EXPECTED_MARKER_DENSITY
there by hand and re-run scripts/evaluate_baseline.py to confirm the
overall specificity MAE/accuracy improved, the same way decision 29's
before/after table was produced.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from backend.scoring import baseline  # noqa: E402
from models.question_schema import load_questions_from_json  # noqa: E402

LABELED_ANSWERS_PATH = PROJECT_ROOT / "data" / "labeled_answers_human_reviewed.json"
QUESTIONS_PATH = PROJECT_ROOT / "data" / "sample_questions.json"

# Coarse grid -- wide enough to see whether the current 0.5/0.5 starting
# point sits near a plateau or far from one. Narrow/refine around the best
# region afterwards the same way decision 29's threshold search did
# (coarse 0.02 steps, then refined to 0.01 steps near the peak), if the
# coarse pass here doesn't already show a clear, stable plateau.
WEIGHT_GRID = [round(float(w), 2) for w in np.arange(0.30, 0.71, 0.05)]
DENSITY_GRID = [round(float(d), 2) for d in np.arange(0.3, 1.01, 0.1)]

TOLERANCE_BANDS = (1.0, 2.0)


def load_labeled_answers() -> list[dict]:
    with LABELED_ANSWERS_PATH.open(encoding="utf-8") as f:
        records = json.load(f)
    return [r for r in records if r["status"] == "scored"]


def precompute_signals() -> list[dict]:
    """
    One embedding pass per record, extracting exactly the raw signals
    _score_specificity() combines (marker_count, sentence_count,
    ref_signal) plus the human specificity score -- everything the grid
    search needs, computed once so the actual weight/density sweep below is
    pure arithmetic instead of replaying the (expensive) embedding step
    per grid point.

    Records whose answer has no sentences at all are skipped: those hit
    _score_specificity()'s hardcoded "empty answer -> score 1.0, band 0-2"
    early return, which doesn't depend on weight/density at all, so they
    can't be improved (or hurt) by this calibration either way.
    """
    questions = {q.question_id: q for q in load_questions_from_json(QUESTIONS_PATH)}
    records = load_labeled_answers()
    signals: list[dict] = []
    skipped_empty = 0
    for record in records:
        question = questions[record["question_id"]]
        answer = record["answer_text"]
        sentences = baseline._split_sentences(answer)
        if not sentences:
            skipped_empty += 1
            continue

        sentence_embeddings = baseline.embed_texts(sentences)
        reference_embeddings = (
            baseline.embed_texts(question.reference_points)
            if question.reference_points
            else np.empty((0, 0), dtype=np.float32)
        )

        digit_hits = len(baseline._DIGIT_PATTERN.findall(answer))
        lowered = answer.lower()
        word_hits = sum(1 for w in baseline._DETAIL_MARKER_WORDS if w in lowered)
        proper_noun_hits = baseline._count_proper_noun_markers(answer)
        marker_count = digit_hits + word_hits + proper_noun_hits

        _avg_ref_sim, ref_signal = baseline._reference_point_signal(sentence_embeddings, reference_embeddings)

        signals.append(
            {
                "marker_count": marker_count,
                "sentence_count": len(sentences),
                "ref_signal": ref_signal,
                "human_score": record["human_scores"]["specificity"],
            }
        )

    if skipped_empty:
        print(f"Skipped {skipped_empty} record(s) with an empty/whitespace-only answer (score is fixed at 1.0 regardless of params).\n")
    return signals


def score_for_params(signal: dict, weight: float, density: float) -> float:
    """Reimplements _score_specificity()'s combine step for one precomputed signal, given a
    candidate (weight, density) pair -- mirrors the real scorer exactly, just without re-embedding."""
    marker_density = signal["marker_count"] / signal["sentence_count"]
    marker_signal = min(marker_density / density, 1.0)
    combined = weight * marker_signal + (1 - weight) * signal["ref_signal"]
    if signal["marker_count"] == 0:
        combined = min(combined, baseline._ZERO_MARKER_SIGNAL_CAP)
    score, _band = baseline._ratio_to_band(combined)
    return score


def stats_for_params(signals: list[dict], weight: float, density: float) -> dict:
    errors = [abs(score_for_params(s, weight, density) - s["human_score"]) for s in signals]
    n = len(errors)
    within = {band: sum(1 for e in errors if e <= band) / n for band in TOLERANCE_BANDS}
    return {"weight": weight, "density": density, "mae": sum(errors) / n, "within_1": within[1.0], "within_2": within[2.0]}


def grid_search(signals: list[dict]) -> list[dict]:
    return [stats_for_params(signals, weight, density) for weight in WEIGHT_GRID for density in DENSITY_GRID]


def main() -> None:
    signals = precompute_signals()
    print(f"Grid-searching over {len(signals)} labeled answers with non-empty text.\n")

    current = stats_for_params(signals, baseline._SPECIFICITY_MARKER_WEIGHT, baseline._EXPECTED_MARKER_DENSITY)
    print(
        f"Current baseline.py values -- weight={current['weight']}, density={current['density']}: "
        f"MAE={current['mae']:.2f}  +/-1={current['within_1']:.0%}  +/-2={current['within_2']:.0%}\n"
    )

    results = grid_search(signals)
    results.sort(key=lambda r: r["mae"])

    print("Top 10 (weight, density) combinations by MAE:\n")
    print("| weight | density | MAE | +/-1 accuracy | +/-2 accuracy |")
    print("| --- | --- | --- | --- | --- |")
    for r in results[:10]:
        print(f"| {r['weight']:.2f} | {r['density']:.2f} | {r['mae']:.2f} | {r['within_1']:.0%} | {r['within_2']:.0%} |")

    best = results[0]
    # Plateau check, same spirit as decision 29's: how many of the top 10
    # sit within a small margin of the single best MAE? A wide plateau
    # means the winning cell isn't a fragile single-point overfit.
    close = [r for r in results if r["mae"] <= best["mae"] + 0.05]
    print(f"\n{len(close)} combination(s) within 0.05 MAE of the best ({best['mae']:.2f}) -- treat this as the plateau, not just the single top row.")


if __name__ == "__main__":
    main()
