"""Baseline comparisons for the Week 7 structure_completeness classifier.

Two baselines that need no GPU/training, so this script runs entirely
locally (not on Colab):

1. Majority-class baseline: always predict the most common band in the
   training portion of whatever split is being evaluated.
2. Existing-app baseline: backend/scoring/baseline.py's score_answer()
   (the heuristic embedding-based scorer currently deployed in the app),
   with its structure_completeness dimension score discretized into the
   same 0-4 bands via ml/prepare_data.py's band_from_score(). This is the
   important one — it's what answers "is fine-tuning actually better than
   what the project already does today?".

A third, optional baseline (zero-shot LLM via the project's existing Groq
client) is included but off by default (--llm-baseline) since it costs API
calls; it is skipped gracefully if no API key is configured.

Evaluated on: each of the 5 CV folds' val set (majority-class baseline
fit on that fold's train_ids only, to mirror how a real model would be
fit/evaluated per fold), the full out-of-fold union (all 5 val sets
concatenated — every one of the 128 CV-pool samples gets exactly one
prediction), and the sealed test set (majority-class fit on the full
128-sample CV pool, since that mirrors fitting a final model on the whole
training pool before evaluating on test).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ml.common as common  # noqa: E402
import ml.metrics as metrics  # noqa: E402
from ml.prepare_data import band_from_score  # noqa: E402

SAMPLE_QUESTIONS_PATH = ROOT / "data" / "sample_questions.json"
RESULTS_PATH = ROOT / "ml" / "results" / "baselines" / "baseline_results.json"


# ---------------------------------------------------------------------------
# Baseline 1: majority class
# ---------------------------------------------------------------------------


def majority_class_baseline(train_labels: list[int], eval_ids: list[str]) -> list[int]:
    """Predict the most frequent label in train_labels for every eval sample.

    Ties broken by Counter.most_common's stable order (lowest band index
    among tied counts, since BAND_LABELS/labels are iterated in band order
    when counts tie in insertion order) — deterministic, not that it should
    matter in practice given ml/data_summary.md's balanced band counts.
    """
    if not train_labels:
        raise ValueError("majority_class_baseline: train_labels is empty")
    majority = Counter(train_labels).most_common(1)[0][0]
    return [majority] * len(eval_ids)


# ---------------------------------------------------------------------------
# Baseline 2: existing app scoring (backend/scoring/baseline.py), discretized
# ---------------------------------------------------------------------------


def _load_questions_by_id():
    # Lazy import: only baseline 2 needs backend.scoring (sentence-transformers
    # model load), so baseline 1 / metrics / split-loading self-tests don't
    # pay that cost.
    from models.question_schema import load_questions_from_json

    questions = load_questions_from_json(SAMPLE_QUESTIONS_PATH)
    return {q.question_id: q for q in questions}


def existing_scoring_baseline(
    eval_ids: list[str], samples_by_id: dict[str, dict], questions_by_id: dict | None = None
) -> list[int]:
    """Run backend/scoring/baseline.py's score_answer() on each eval sample and
    discretize its structure_completeness dimension score into a 0-4 band via
    the same band_from_score() boundary rule prepare_data.py used for labels.
    """
    from backend.scoring.baseline import score_answer

    if questions_by_id is None:
        questions_by_id = _load_questions_by_id()

    preds = []
    for sample_id in eval_ids:
        sample = samples_by_id[sample_id]
        question = questions_by_id[sample["question_id"]]
        report = score_answer(sample["answer_text"], question)
        raw_score = report["structure_completeness"]["score"]
        preds.append(band_from_score(raw_score))
    return preds


# ---------------------------------------------------------------------------
# Baseline 3 (optional): zero-shot LLM
# ---------------------------------------------------------------------------


def zero_shot_llm_baseline(eval_ids: list[str], samples_by_id: dict[str, dict]) -> list[int] | None:
    """Ask the project's existing Groq LLM client to grade structure_completeness
    zero-shot on a 0-10 scale, then discretize the same way as baseline 2.

    Returns None (with a printed notice) if GROQ_API_KEY isn't configured —
    this baseline is opt-in and best-effort, never a hard requirement.
    """
    import os

    if not os.environ.get("GROQ_API_KEY"):
        print("zero_shot_llm_baseline: GROQ_API_KEY not set, skipping.")
        return None

    from groq import Groq

    client = Groq()
    preds = []
    for sample_id in eval_ids:
        sample = samples_by_id[sample_id]
        prompt = (
            "你是一位资深面试官。请只根据回答的\"结构完整度\"（是否包含情境/任务/行动/结果"
            "等应有要素，结构是否清晰）给出一个0到10的分数，只输出数字，不要输出任何其他内容。\n\n"
            f"问题：{sample.get('question_text', '')}\n回答：{sample['answer_text']}\n分数："
        )
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=8,
        )
        text = completion.choices[0].message.content.strip()
        try:
            raw_score = float(text.split()[0])
        except (ValueError, IndexError):
            raw_score = 5.0  # unparseable response falls back to a neutral mid score
        preds.append(band_from_score(max(0.0, min(10.0, raw_score))))
    return preds


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def evaluate_split(
    split_name: str,
    train_ids: list[str],
    eval_ids: list[str],
    samples_by_id: dict[str, dict],
    questions_by_id: dict,
    run_llm: bool = False,
) -> dict:
    y_true = common.ids_to_labels(eval_ids, samples_by_id)
    train_labels = common.ids_to_labels(train_ids, samples_by_id)

    results = {"split": split_name, "n": len(eval_ids)}

    majority_pred = majority_class_baseline(train_labels, eval_ids)
    results["majority_class"] = metrics.compute_metrics(y_true, majority_pred)

    existing_pred = existing_scoring_baseline(eval_ids, samples_by_id, questions_by_id)
    results["existing_app_scoring"] = metrics.compute_metrics(y_true, existing_pred)

    if run_llm:
        llm_pred = zero_shot_llm_baseline(eval_ids, samples_by_id)
        if llm_pred is not None:
            results["zero_shot_llm"] = metrics.compute_metrics(y_true, llm_pred)

    return results


def run_all(run_llm: bool = False) -> dict:
    samples_by_id = common.load_prepared_samples()
    questions_by_id = _load_questions_by_id()

    all_results = {"folds": []}
    oof_true: list[int] = []
    oof_majority: list[int] = []
    oof_existing: list[int] = []
    cv_pool_ids: list[str] = []

    for fold_i in range(common.K_FOLDS):
        fold = common.load_fold(fold_i)
        train_ids, val_ids = fold["train_ids"], fold["val_ids"]
        cv_pool_ids.extend(val_ids)
        fold_result = evaluate_split(
            f"fold_{fold_i}_val", train_ids, val_ids, samples_by_id, questions_by_id, run_llm=run_llm
        )
        all_results["folds"].append(fold_result)
        print(metrics.format_metrics(fold_result["majority_class"], f"fold {fold_i} — majority class"))
        print(metrics.format_metrics(fold_result["existing_app_scoring"], f"fold {fold_i} — existing app scoring"))

        # Recompute predictions once more for OOF aggregation (cheap: majority
        # class is O(1), existing-app scoring re-embeds — acceptable at N=150).
        oof_true.extend(common.ids_to_labels(val_ids, samples_by_id))
        oof_majority.extend(majority_class_baseline(common.ids_to_labels(train_ids, samples_by_id), val_ids))
        oof_existing.extend(existing_scoring_baseline(val_ids, samples_by_id, questions_by_id))

    all_results["oof"] = {
        "n": len(oof_true),
        "majority_class": metrics.compute_metrics(oof_true, oof_majority),
        "existing_app_scoring": metrics.compute_metrics(oof_true, oof_existing),
    }
    print(metrics.format_metrics(all_results["oof"]["majority_class"], "OOF (all 5 val folds) — majority class"))
    print(metrics.format_metrics(all_results["oof"]["existing_app_scoring"], "OOF (all 5 val folds) — existing app scoring"))

    test = common.load_test()
    test_result = evaluate_split(
        "test", cv_pool_ids, test["test_ids"], samples_by_id, questions_by_id, run_llm=run_llm
    )
    all_results["test"] = test_result
    print(metrics.format_metrics(test_result["majority_class"], "TEST — majority class"))
    print(metrics.format_metrics(test_result["existing_app_scoring"], "TEST — existing app scoring"))

    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-baseline", action="store_true",
                         help="Also run the optional zero-shot LLM baseline (needs GROQ_API_KEY).")
    args = parser.parse_args()

    results = run_all(run_llm=args.llm_baseline)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {RESULTS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
