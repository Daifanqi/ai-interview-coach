"""Build the labeled dataset for the Week 7 structure_completeness classifier.

Scope: only batch1 of data/labeled_answers_human_reviewed.json — the 150
answers drafted from data/sample_questions.json (the 30-question general
calibration set). This is NOT the same file as data/question_bank.json
(200 questions used by the unrelated RAG retrieval bank) and it is NOT the
current on-disk labeled_answers_human_reviewed.json in full, which also
contains 50 already-reviewed batch2 answers drafted from question_bank.json
(a 7-domain, job-targeted question set). Those 50 are deliberately excluded
this week — see docs/decision_log.md entry 30 for why (different question
source than batch1, and including only behavioral coverage from batch2
would unbalance the type stratification used in split_data.py).

Ground truth label = human_scores["structure_completeness"], re-banded from
its native 0-10 float scale into 5 discrete bands (0-4). The pre-existing
score_band field on each record is NOT the label source (it records which
band the draft answer was *written* to hit, not what a human reviewer
actually scored it) — it is used only as a consistency check against the
re-banded label, since the two should usually agree.

question_type is joined from data/sample_questions.json (authoritative),
not parsed from the question_id prefix, per docs/decision_log.md's note
that review_labels.py uses the same join-based approach.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWED_PATH = ROOT / "data" / "labeled_answers_human_reviewed.json"
SAMPLE_QUESTIONS_PATH = ROOT / "data" / "sample_questions.json"
OUT_PATH = ROOT / "ml" / "data" / "prepared_samples.json"
SUMMARY_PATH = ROOT / "ml" / "data_summary.md"

EXPECTED_BATCH1_COUNT = 150
BAND_LABELS = ["0-2", "3-4", "5-6", "7-8", "9-10"]


def band_from_score(score: float) -> int:
    """Map a 0-10 structure_completeness score to a 0-4 band index.

    Boundaries are the midpoints between adjacent bands (2.5, 4.5, 6.5,
    8.5). A score exactly on a boundary (e.g. 2.5) falls into the *higher*
    band — this is the rule that reproduces the ~2 known score_band
    mismatches (see the consistency check below) rather than 3.
    """
    if score < 2.5:
        return 0
    elif score < 4.5:
        return 1
    elif score < 6.5:
        return 2
    elif score < 8.5:
        return 3
    else:
        return 4


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_samples() -> tuple[list[dict], list[dict]]:
    """Returns (samples, mismatches)."""
    questions = load_json(SAMPLE_QUESTIONS_PATH)
    question_type_by_id = {q["question_id"]: q["question_type"] for q in questions}
    batch1_ids = set(question_type_by_id)

    reviewed = load_json(REVIEWED_PATH)
    batch1_records = [r for r in reviewed if r["question_id"] in batch1_ids]

    if len(batch1_records) != EXPECTED_BATCH1_COUNT:
        raise SystemExit(
            f"Expected exactly {EXPECTED_BATCH1_COUNT} batch1 records (question_id "
            f"present in {SAMPLE_QUESTIONS_PATH.name}), found {len(batch1_records)} in "
            f"{REVIEWED_PATH.name}. Refusing to proceed silently — investigate before "
            f"re-running (has sample_questions.json or the reviewed file changed?)."
        )

    samples = []
    mismatches = []
    for r in batch1_records:
        qid = r["question_id"]
        score = r["human_scores"]["structure_completeness"]
        band_idx = band_from_score(score)
        band_label = BAND_LABELS[band_idx]

        # question_type: prefer the sample_questions.json join (authoritative);
        # fall back to the question_id prefix only if the join ever misses
        # (shouldn't happen for batch1 by construction of batch1_ids above).
        question_type = question_type_by_id.get(qid)
        if question_type is None:
            question_type = qid.rsplit("_", 1)[0]

        if band_label != r["score_band"]:
            mismatches.append(
                {
                    "review_id": r["review_id"],
                    "question_id": qid,
                    "structure_completeness_score": score,
                    "original_score_band": r["score_band"],
                    "rebanded_label": band_label,
                }
            )

        samples.append(
            {
                "id": r["review_id"],
                "question_id": qid,
                "question_type": question_type,
                "answer_text": r["answer_text"],
                "answer_length": len(r["answer_text"]),
                "structure_completeness_score": score,
                "original_score_band": r["score_band"],
                "band_label": band_idx,
                "band_range": band_label,
            }
        )

    return samples, mismatches


def confirm_mismatches(mismatches: list[dict], auto_yes: bool) -> None:
    print(f"Consistency check: {len(mismatches)} record(s) where the re-banded label "
          f"(from human_scores.structure_completeness) disagrees with the original "
          f"score_band field.")
    for m in mismatches:
        print(
            f"  {m['review_id']}: score={m['structure_completeness_score']} -> "
            f"rebanded={m['rebanded_label']}, but original score_band={m['original_score_band']}"
        )
    if not mismatches:
        return
    if auto_yes:
        print("(--yes passed, proceeding without interactive confirmation)")
        return
    reply = input("Proceed using the re-banded labels for these records? [y/N] ").strip().lower()
    if reply != "y":
        raise SystemExit("Aborted: mismatches not confirmed.")


def summarize(samples: list[dict]) -> dict:
    type_counts = Counter(s["question_type"] for s in samples)
    band_counts = Counter(s["band_range"] for s in samples)
    joint_counts = Counter((s["question_type"], s["band_range"]) for s in samples)
    lengths = [s["answer_length"] for s in samples]
    length_stats = {
        "min": min(lengths),
        "max": max(lengths),
        "mean": round(statistics.mean(lengths), 1),
        "median": statistics.median(lengths),
        "stdev": round(statistics.stdev(lengths), 1),
    }
    return {
        "type_counts": type_counts,
        "band_counts": band_counts,
        "joint_counts": joint_counts,
        "length_stats": length_stats,
    }


def is_chinese_dominant(text: str) -> bool:
    han = sum(1 for ch in text if "一" <= ch <= "鿿")
    return han / max(len(text), 1) >= 0.3


def write_summary(samples: list[dict], mismatches: list[dict], stats: dict) -> None:
    type_counts = stats["type_counts"]
    band_counts = stats["band_counts"]
    joint_counts = stats["joint_counts"]
    length_stats = stats["length_stats"]

    non_chinese = [s["id"] for s in samples if not is_chinese_dominant(s["answer_text"])]

    lines = []
    lines.append("# ml/ 数据准备摘要（Week 7）")
    lines.append("")
    lines.append("自动生成，来源：`ml/prepare_data.py`。此文件由 `prepare_data.py` 整体覆写，"
                  "`split_data.py` 会在其后追加划分相关章节，不要手工编辑本文件靠上的部分。")
    lines.append("")
    lines.append("## 1. 数据范围")
    lines.append("")
    lines.append(f"- 来源文件：`data/labeled_answers_human_reviewed.json`")
    lines.append(f"- 样本量：**{len(samples)}** 条（仅 batch1，question_id 命中 "
                  f"`data/sample_questions.json` 30道通用题的记录）")
    lines.append("- **不包含** 当前文件里另外50条 batch2 behavioral 记录（来自 "
                  "`data/question_bank.json` 7个领域题库）。原因见 "
                  "`docs/decision_log.md` 条目30：数据源不同、题型分布会失衡"
                  "（50/50/50 变成 100/50/50），本周不采用。")
    lines.append("- **不使用** `data/question_bank.json`（200道题的RAG检索题库，与本实验无关）。")
    lines.append("")
    lines.append("## 2. 标签构建")
    lines.append("")
    lines.append("- 真实标签 = `human_scores.structure_completeness`（0-10浮点数），"
                  "重新分档为 0-4 五档：0-2 / 3-4 / 5-6 / 7-8 / 9-10。")
    lines.append("- 分档边界取相邻档位的中点（2.5 / 4.5 / 6.5 / 8.5）；边界值本身"
                  "归入较高的一档（例如 2.5 归入 \"3-4\" 而非 \"0-2\"）。")
    lines.append("- `question_type` 通过 `question_id` join `sample_questions.json` 的"
                  "权威字段得到，不是从 `question_id` 前缀猜测的（batch1 全部能 join 成功）。")
    lines.append("")
    lines.append("## 3. 一致性校验：重新分档 vs 原始 score_band")
    lines.append("")
    lines.append(f"发现 **{len(mismatches)}** 条不一致记录（重新分档结果 ≠ 原始 `score_band` 字段）："
                  f"{'符合预期（约2条）。' if len(mismatches) == 2 else '⚠️ 与预期的约2条不符，请复核。'}")
    lines.append("")
    if mismatches:
        lines.append("| review_id | structure_completeness 分数 | 重新分档 | 原始 score_band |")
        lines.append("| --- | --- | --- | --- |")
        for m in mismatches:
            lines.append(
                f"| {m['review_id']} | {m['structure_completeness_score']} | "
                f"{m['rebanded_label']} | {m['original_score_band']} |"
            )
        lines.append("")
        lines.append("解读：这些记录的草稿是按某个目标档位生成的（`score_band` 字段"
                      "记录的是草稿的目标档），但人工复核给出的 `structure_completeness` "
                      "实际分数落在了另一档——说明人工评分与草稿设计目标不一致，"
                      "是人工复核阶段的真实判断，本脚本以人工分数重新分档后的结果为准，"
                      "不回退去用原始 `score_band`。")
    else:
        lines.append("无不一致记录。")
    lines.append("")
    lines.append("**运行本脚本时须人工确认以上不一致记录后才会继续**"
                  "（交互式 `input()` 确认，或显式传 `--yes` 跳过——`--yes` 仅用于"
                  "已经人工确认过一次之后的自动化重跑，不代表跳过校验本身）。")
    lines.append("")
    lines.append("## 4. 题型分布")
    lines.append("")
    lines.append("| 题型 | 数量 |")
    lines.append("| --- | --- |")
    for qtype in sorted(type_counts):
        lines.append(f"| {qtype} | {type_counts[qtype]} |")
    lines.append("")
    lines.append("## 5. 档位分布")
    lines.append("")
    lines.append("| 档位 | 数量 |")
    lines.append("| --- | --- |")
    for band in BAND_LABELS:
        lines.append(f"| {band} | {band_counts.get(band, 0)} |")
    lines.append("")
    lines.append("## 6. 题型 × 档位 联合分布")
    lines.append("")
    lines.append("| 题型 \\ 档位 | " + " | ".join(BAND_LABELS) + " |")
    lines.append("| --- | " + " | ".join(["---"] * len(BAND_LABELS)) + " |")
    for qtype in sorted(type_counts):
        row = [str(joint_counts.get((qtype, band), 0)) for band in BAND_LABELS]
        lines.append(f"| {qtype} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## 7. answer_text 长度分布（字符数）")
    lines.append("")
    lines.append(f"- min: {length_stats['min']}")
    lines.append(f"- max: {length_stats['max']}")
    lines.append(f"- mean: {length_stats['mean']}")
    lines.append(f"- median: {length_stats['median']}")
    lines.append(f"- stdev: {length_stats['stdev']}")
    lines.append("")
    lines.append("## 8. 语言范围")
    lines.append("")
    if non_chinese:
        lines.append(f"⚠️ {len(non_chinese)} 条 answer_text 中文字符占比低于30%："
                      f"{', '.join(non_chinese)}")
    else:
        lines.append(f"150条 `answer_text` 全部为中文（逐条检查中文字符占比 ≥ 30%，"
                      f"实际全部远高于此阈值）。**本次实验范围限定中文**，"
                      f"未覆盖英文或中英混合作答场景，模型/特征工程若涉及分词"
                      f"或语言相关假设，需注意这一限制。")
    lines.append("")
    lines.append("## 9. 产出文件")
    lines.append("")
    lines.append(f"- `ml/data/prepared_samples.json`：{len(samples)}条样本，字段见脚本内"
                  f"`build_samples()`（id / question_id / question_type / answer_text / "
                  f"answer_length / structure_completeness_score / original_score_band / "
                  f"band_label(0-4) / band_range）。")
    lines.append("")

    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true",
                         help="Skip the interactive mismatch-confirmation prompt "
                              "(use only for automated re-runs after a human has "
                              "already confirmed once).")
    args = parser.parse_args()

    samples, mismatches = build_samples()
    confirm_mismatches(mismatches, auto_yes=args.yes)

    stats = summarize(samples)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)

    write_summary(samples, mismatches, stats)

    print(f"\nWrote {len(samples)} samples to {OUT_PATH.relative_to(ROOT)}")
    print(f"Wrote summary to {SUMMARY_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
