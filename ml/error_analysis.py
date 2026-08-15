"""Error-pattern analysis for the fine-tuned classifier's predictions.

Reads a predictions file (list of {"id", "true", "pred"}, band indices
0-4) — by default ml/results/train/{model}/oof_predictions.json, i.e. the
5-fold out-of-fold predictions train.py writes after a full 5-fold run
(every one of the 128 CV-pool samples gets exactly one prediction, from
whichever fold had it in val). Groups the |pred - true| >= 2 "major
miss" samples by question_type / true band / over-vs-under-prediction to
summarize what the model tends to get badly wrong.

IMPORTANT, read before trusting anything below: data/labeled_answers_human_
reviewed.json has exactly ONE human reviewer per answer (see
docs/decision_log.md) — there is no second independent rater. This script
therefore never computes or reports any inter-annotator agreement metric
(Cohen's kappa / ICC / anything of that shape) — there is no second rater
to agree or disagree with, and fabricating such a number would misrepresent
label quality. Every "error" analyzed here is "model disagreed with the
one available label", not "model disagreed with ground truth" — some
fraction of these disagreements may be label noise rather than model
error, and this script has no way to tell which.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ml.common as common  # noqa: E402
from ml.metrics import BAND_LABELS  # noqa: E402

RESULTS_DIR = ROOT / "ml" / "results" / "error_analysis"
MAJOR_MISS_THRESHOLD = 2  # |pred - true| >= this counts as a "major miss"

SINGLE_ANNOTATOR_CAVEAT = (
    "**单一标注者警示**：`data/labeled_answers_human_reviewed.json` 里每条答案只有一位"
    "人工复核者打分，没有第二名标注者独立评分做对照。因此本报告**不计算、也不报告任何"
    "标注者间一致性指标**（如 Cohen's kappa、ICC 等本质上衡量两个评分者之间一致程度的"
    "指标）——没有第二个评分者，这类指标无从谈起，虚构一个数字会误导对标签质量的判断。"
    "下面所有\"误判\"都只是\"模型预测 vs 这唯一一位标注者给出的标签\"之间的偏差，"
    "不能确定这些偏差中有多少是模型真正的错误、有多少只是标注本身的噪声/主观差异。"
)


def load_predictions(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run `python ml/train.py --model <name>` for all 5 folds "
            f"first (it writes oof_predictions.json only once every fold in range(5) has run)."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def find_major_misses(predictions: list[dict], threshold: int = MAJOR_MISS_THRESHOLD) -> list[dict]:
    return [p for p in predictions if abs(p["pred"] - p["true"]) >= threshold]


def summarize_errors(predictions: list[dict], samples_by_id: dict[str, dict], threshold: int = MAJOR_MISS_THRESHOLD) -> dict:
    major = find_major_misses(predictions, threshold=threshold)

    by_type_total = Counter(samples_by_id[p["id"]]["question_type"] for p in predictions)
    by_type_major = Counter(samples_by_id[p["id"]]["question_type"] for p in major)

    by_true_band_total = Counter(BAND_LABELS[p["true"]] for p in predictions)
    by_true_band_major = Counter(BAND_LABELS[p["true"]] for p in major)

    direction = Counter("over-predicted" if p["pred"] > p["true"] else "under-predicted" for p in major)

    lengths_all = [samples_by_id[p["id"]]["answer_length"] for p in predictions]
    lengths_major = [samples_by_id[p["id"]]["answer_length"] for p in major]

    return {
        "n_total": len(predictions),
        "n_major_miss": len(major),
        "major_miss_rate": len(major) / len(predictions) if predictions else float("nan"),
        "by_question_type": {
            qt: {"total": by_type_total[qt], "major_miss": by_type_major.get(qt, 0)}
            for qt in sorted(by_type_total)
        },
        "by_true_band": {
            b: {"total": by_true_band_total[b], "major_miss": by_true_band_major.get(b, 0)}
            for b in BAND_LABELS
        },
        "direction_of_major_miss": dict(direction),
        "mean_answer_length_all": sum(lengths_all) / len(lengths_all) if lengths_all else float("nan"),
        "mean_answer_length_major_miss": sum(lengths_major) / len(lengths_major) if lengths_major else float("nan"),
        "major_miss_samples": [
            {
                "id": p["id"],
                "question_type": samples_by_id[p["id"]]["question_type"],
                "true_band": BAND_LABELS[p["true"]],
                "pred_band": BAND_LABELS[p["pred"]],
                "answer_length": samples_by_id[p["id"]]["answer_length"],
                "answer_preview": samples_by_id[p["id"]]["answer_text"][:80],
            }
            for p in major
        ],
    }


def render_report(model_name: str, summary: dict) -> str:
    lines = [f"# 错误分析：{model_name}", "", SINGLE_ANNOTATOR_CAVEAT, ""]
    lines.append(f"总样本数：{summary['n_total']}，偏离≥{MAJOR_MISS_THRESHOLD}档的\"重大误判\"："
                 f"{summary['n_major_miss']}（{summary['major_miss_rate']:.1%}）")
    lines.append("")
    lines.append("## 按题型")
    lines.append("")
    lines.append("| 题型 | 总数 | 重大误判 | 误判率 |")
    lines.append("| --- | --- | --- | --- |")
    for qt, stats in summary["by_question_type"].items():
        rate = stats["major_miss"] / stats["total"] if stats["total"] else float("nan")
        lines.append(f"| {qt} | {stats['total']} | {stats['major_miss']} | {rate:.1%} |")
    lines.append("")
    lines.append("## 按真实档位")
    lines.append("")
    lines.append("| 档位 | 总数 | 重大误判 | 误判率 |")
    lines.append("| --- | --- | --- | --- |")
    for b, stats in summary["by_true_band"].items():
        rate = stats["major_miss"] / stats["total"] if stats["total"] else float("nan")
        lines.append(f"| {b} | {stats['total']} | {stats['major_miss']} | {rate:.1%} |")
    lines.append("")
    lines.append("## 误判方向（重大误判内部）")
    lines.append("")
    for direction, count in summary["direction_of_major_miss"].items():
        lines.append(f"- {direction}: {count}")
    lines.append("")
    lines.append("## 长度信号")
    lines.append("")
    lines.append(f"- 全体样本平均长度：{summary['mean_answer_length_all']:.1f} 字符")
    lines.append(f"- 重大误判样本平均长度：{summary['mean_answer_length_major_miss']:.1f} 字符"
                 f"（{'明显偏长' if summary['mean_answer_length_major_miss'] > summary['mean_answer_length_all'] * 1.2 else '明显偏短' if summary['mean_answer_length_major_miss'] < summary['mean_answer_length_all'] * 0.8 else '与全体接近，长度不是主要信号'}）")
    lines.append("")
    lines.append("## 重大误判样本明细（人工阅读用）")
    lines.append("")
    lines.append("| id | 题型 | 真实档位 | 预测档位 | 长度 | 回答开头 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for s in summary["major_miss_samples"]:
        preview = s["answer_preview"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {s['id']} | {s['question_type']} | {s['true_band']} | {s['pred_band']} | "
                     f"{s['answer_length']} | {preview}... |")
    lines.append("")
    lines.append("以上模式是描述性归纳（哪些题型/档位/长度区间误判更集中），不是因果结论，"
                 "样本量小（N=150）时尤其不要过度解读某个子分组的误判率差异。")
    return "\n".join(lines)


def length_error_correlation(predictions: list[dict], samples_by_id: dict[str, dict]) -> float:
    """Pearson correlation between answer_length and signed error (pred - true).

    Positive -> longer answers tend to get predicted a higher band relative
    to their true band (over-prediction skews long); negative -> the
    opposite. NaN if there's no variance in length or error (can't
    correlate a constant)."""
    import numpy as np

    lengths = np.array([samples_by_id[p["id"]]["answer_length"] for p in predictions], dtype=float)
    signed_errors = np.array([p["pred"] - p["true"] for p in predictions], dtype=float)
    if len(lengths) < 2 or np.std(lengths) == 0 or np.std(signed_errors) == 0:
        return float("nan")
    return float(np.corrcoef(lengths, signed_errors)[0, 1])


def compare_length_bias(
    before_predictions: list[dict], after_predictions: list[dict], samples_by_id: dict[str, dict]
) -> dict:
    """Length-artifact cross-check for a before/after (e.g. plain vs.
    back-translation-augmented training) comparison.

    Why this exists: ml/augment.py's back-translation makes AUGMENTED
    TRAINING samples run ~23% longer on average than their originals (see
    ml/augment_review.md) — purely a translation-round-trip side effect,
    not a structure change. If a model trained on that augmented data
    starts treating "longer answer" as a proxy for "more complete
    structure", the val/test set (never augmented, same original-length
    answers in both the before and after run) would show that up as: the
    after-run's errors improve disproportionately on already-long true
    answers and/or worsen on short true answers, relative to the
    before-run. That's a shortcut artifact, not a real structural-scoring
    improvement — this function is the check for it, not a proof either
    way (small N, correlational, see the caveat in the rendered report).

    before_predictions/after_predictions must cover the same sample ids
    (the CV val sets are identical in both runs — only the training data
    differs) for the paired delta comparison to mean anything.
    """
    import numpy as np

    before_by_id = {p["id"]: p for p in before_predictions}
    after_by_id = {p["id"]: p for p in after_predictions}
    common_ids = sorted(set(before_by_id) & set(after_by_id))
    if not common_ids:
        raise ValueError("compare_length_bias: no overlapping sample ids between before/after predictions")
    missing = (set(before_by_id) ^ set(after_by_id))

    lengths = np.array([samples_by_id[i]["answer_length"] for i in common_ids], dtype=float)
    before_abs_err = np.array([abs(before_by_id[i]["pred"] - before_by_id[i]["true"]) for i in common_ids], dtype=float)
    after_abs_err = np.array([abs(after_by_id[i]["pred"] - after_by_id[i]["true"]) for i in common_ids], dtype=float)
    delta = after_abs_err - before_abs_err  # negative = improved (smaller error) after augmentation

    corr = float(np.corrcoef(lengths, delta)[0, 1]) if np.std(lengths) > 0 and np.std(delta) > 0 else float("nan")

    order = np.argsort(lengths)
    thirds = np.array_split(order, 3)
    tertile_labels = ["短（长度下三分之一）", "中（长度中三分之一）", "长（长度上三分之一）"]
    tertiles = [
        {
            "tertile": label,
            "n": int(len(idx)),
            "mean_length": float(lengths[idx].mean()),
            "mean_delta_abs_error": float(delta[idx].mean()),
        }
        for label, idx in zip(tertile_labels, thirds)
    ]

    return {
        "n_common": len(common_ids),
        "n_missing_from_one_side": len(missing),
        "before_length_error_correlation": length_error_correlation(
            [before_by_id[i] for i in common_ids], samples_by_id
        ),
        "after_length_error_correlation": length_error_correlation(
            [after_by_id[i] for i in common_ids], samples_by_id
        ),
        "length_vs_delta_abs_error_correlation": corr,
        "length_tertiles": tertiles,
    }


def render_length_bias_report(before_name: str, after_name: str, comparison: dict) -> str:
    lines = [f"# 长度伪影交叉检查：{before_name} vs {after_name}", ""]
    lines.append(
        "**用途**：`ml/augment.py` 的回译增强会让增强后的*训练*样本平均变长约23%"
        "（见 `ml/augment_review.md`），这是翻译副作用，不是结构变化。如果模型"
        "从增强训练数据里学到\"更长=结构更完整\"这种捷径而不是真实的结构信号，"
        "在（未被增强、长度分布不变的）验证集上会表现为：增强后模型在原本就较长的"
        "真实答案上误差改善更多，在较短答案上改善更少甚至变差。下面的相关性和分档"
        "统计就是用来检查这个模式是否存在——**这只是一个排查线索，不是因果证明**，"
        "小样本下相关系数本身噪声很大，不要单独据此下结论，要结合重大误判样本明细"
        "一起看。"
    )
    lines.append("")
    if comparison["n_missing_from_one_side"]:
        lines.append(f"⚠️ {before_name} 和 {after_name} 的预测样本id集合不完全一致，"
                     f"有 {comparison['n_missing_from_one_side']} 个只出现在其中一侧"
                     f"（正常情况下两次跑的val集合应该完全相同，出现差异说明两次跑用的"
                     f"折/数据不一致，下面的配对对比只用了两边都有的"
                     f"{comparison['n_common']}条，解读前先确认这个差异是否符合预期）。")
        lines.append("")
    lines.append(f"配对比较的样本数：{comparison['n_common']}")
    lines.append("")
    lines.append(f"- {before_name}：长度 vs (预测-真实) 有符号误差的相关系数 = "
                 f"{comparison['before_length_error_correlation']:.3f}")
    lines.append(f"- {after_name}：长度 vs (预测-真实) 有符号误差的相关系数 = "
                 f"{comparison['after_length_error_correlation']:.3f}")
    lines.append(f"- 长度 vs \"增强后比增强前误差变化量\"(after减before，负值=改善) 的相关系数 = "
                 f"{comparison['length_vs_delta_abs_error_correlation']:.3f}"
                 f"（明显负相关 = 越长的真实答案在增强后误差改善越多，是长度伪影的可疑信号；"
                 f"接近0 = 改善/恶化和长度没有明显关系，更支持是真实的结构信号提升）")
    lines.append("")
    lines.append("## 按长度分三档看误差变化")
    lines.append("")
    lines.append("| 长度档位 | 样本数 | 平均长度 | 平均误差变化（负=改善）|")
    lines.append("| --- | --- | --- | --- |")
    for t in comparison["length_tertiles"]:
        lines.append(f"| {t['tertile']} | {t['n']} | {t['mean_length']:.0f} | {t['mean_delta_abs_error']:+.3f} |")
    lines.append("")
    lines.append("解读方式：如果\"长\"这一档的平均误差变化明显比\"短\"这一档更负（改善更多），"
                 "且上面的相关系数也明显偏负，两个信号一致指向长度伪影，这种情况下增强前后"
                 "的整体指标变化不能直接当作\"模型变强了\"来写进报告结论，需要在报告里"
                 "如实注明这个保留意见。如果三档的误差变化差不多、相关系数接近0，"
                 "则没有看到长度伪影的证据，指标变化更可能反映真实的结构判断能力变化。")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="xlm-roberta-base")
    parser.add_argument("--predictions", type=Path, default=None,
                         help="Default: ml/results/train/{model}/oof_predictions.json")
    parser.add_argument("--threshold", type=int, default=MAJOR_MISS_THRESHOLD)
    parser.add_argument("--compare-augmentation", action="store_true",
                         help="Also run the length-artifact cross-check between --model (treated "
                              "as the 'before'/non-augmented run) and its '__augmented' counterpart. "
                              "Use this whenever the augmented run's val metrics differ noticeably "
                              "from the plain run's, in either direction — see ml/augment_review.md "
                              "for why (back-translation systematically lengthens training text).")
    parser.add_argument("--augmented-model", default=None,
                         help="Name of the augmented run if it doesn't follow the default "
                              "'{--model}__augmented' convention train.py uses.")
    args = parser.parse_args()

    predictions_path = args.predictions or (ROOT / "ml" / "results" / "train" / args.model / "oof_predictions.json")
    predictions = load_predictions(predictions_path)
    samples_by_id = common.load_prepared_samples()

    summary = summarize_errors(predictions, samples_by_id, threshold=args.threshold)
    report = render_report(args.model, summary)

    print(report)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.model}_error_analysis.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nWrote {out_path.relative_to(ROOT)}")

    if args.compare_augmentation:
        augmented_model = args.augmented_model or f"{args.model}__augmented"
        augmented_path = ROOT / "ml" / "results" / "train" / augmented_model / "oof_predictions.json"
        augmented_predictions = load_predictions(augmented_path)

        comparison = compare_length_bias(predictions, augmented_predictions, samples_by_id)
        length_report = render_length_bias_report(args.model, augmented_model, comparison)

        print("\n" + length_report)

        length_out_path = RESULTS_DIR / f"{args.model}_vs_{augmented_model}_length_bias.md"
        length_out_path.write_text(length_report, encoding="utf-8")
        print(f"\nWrote {length_out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
