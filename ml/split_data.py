"""Split the Week 7 dataset (ml/data/prepared_samples.json, 150 samples) for
training on Colab.

N=150 is small, so 5-fold stratified cross-validation is the primary
evaluation method, plus a sealed holdout test set (10-15% of the data) that
is never touched during tuning. Both splits are computed once here and
written to ml/splits/ — the Colab training notebook loads this split
instead of re-splitting, so every experiment run is comparable against the
same folds/test set.

Stratification: primarily by the (question_type, band_range) joint label.
If any cell of that joint grid gets too small to support both the holdout
split and 5-fold CV (a class needs >=2 members for the holdout split and
>=K=5 members in the remaining pool for StratifiedKFold), this script
automatically degrades to stratifying by band_range alone and prints a
question_type coverage table per fold so that can be checked by hand.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedKFold, train_test_split

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_PATH = ROOT / "ml" / "data" / "prepared_samples.json"
SPLITS_DIR = ROOT / "ml" / "splits"
SUMMARY_PATH = ROOT / "ml" / "data_summary.md"

SEED = 42
K_FOLDS = 5
TEST_FRAC = 0.14  # lands at 21/150 = 14% given N=150, inside the 10-15% target

SPLIT_SECTION_MARKER = "<!-- SPLIT_SECTION_START -->"


def load_samples() -> list[dict]:
    with SAMPLES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def joint_label(s: dict) -> str:
    return f"{s['question_type']}|{s['band_range']}"


def band_label(s: dict) -> str:
    return s["band_range"]


def choose_strategy(samples: list[dict]) -> tuple[str, list[str]]:
    """Decide joint vs band-only stratification and return (strategy, labels)."""
    joint_labels = [joint_label(s) for s in samples]
    joint_counts = Counter(joint_labels)
    min_joint = min(joint_counts.values())

    if min_joint < 2:
        return "band_only", [band_label(s) for s in samples]

    # Estimate remaining-pool cell size after holdout removal to see whether
    # StratifiedKFold(n_splits=K_FOLDS) will have enough members per class.
    est_remaining_min = min(
        round(count * (1 - TEST_FRAC)) for count in joint_counts.values()
    )
    if est_remaining_min < K_FOLDS:
        return "band_only", [band_label(s) for s in samples]

    return "joint_type_band", joint_labels


def split(samples: list[dict]) -> dict:
    strategy, labels = choose_strategy(samples)
    ids = [s["id"] for s in samples]
    idx = np.arange(len(samples))

    train_idx, test_idx = train_test_split(
        idx, test_size=TEST_FRAC, random_state=SEED, stratify=labels
    )

    pool_labels = [labels[i] for i in train_idx]
    skf = StratifiedKFold(n_splits=K_FOLDS, shuffle=True, random_state=SEED)
    folds = []
    for fold_i, (fold_train_rel, fold_val_rel) in enumerate(
        skf.split(train_idx, pool_labels)
    ):
        fold_train_idx = train_idx[fold_train_rel]
        fold_val_idx = train_idx[fold_val_rel]
        folds.append(
            {
                "fold": fold_i,
                "train_ids": [ids[i] for i in fold_train_idx],
                "val_ids": [ids[i] for i in fold_val_idx],
            }
        )

    return {
        "strategy": strategy,
        "test_ids": [ids[i] for i in test_idx],
        "cv_pool_ids": [ids[i] for i in train_idx],
        "folds": folds,
    }


def write_splits(result: dict) -> None:
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for fold in result["folds"]:
        payload = {
            "fold": fold["fold"],
            "seed": SEED,
            "strategy": result["strategy"],
            "train_ids": fold["train_ids"],
            "val_ids": fold["val_ids"],
        }
        path = SPLITS_DIR / f"fold_{fold['fold']}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    test_payload = {
        "seed": SEED,
        "strategy": result["strategy"],
        "test_frac_target": TEST_FRAC,
        "test_ids": result["test_ids"],
    }
    with (SPLITS_DIR / "test.json").open("w", encoding="utf-8") as f:
        json.dump(test_payload, f, ensure_ascii=False, indent=2)


def quality_checklist(samples: list[dict], result: dict) -> list[str]:
    by_id = {s["id"]: s for s in samples}
    all_ids = set(by_id)
    test_ids = set(result["test_ids"])
    cv_pool_ids = set(result["cv_pool_ids"])
    folds = result["folds"]

    lines = []

    # 1. test disjoint from CV pool, union covers everything
    disjoint_ok = test_ids.isdisjoint(cv_pool_ids)
    union_ok = (test_ids | cv_pool_ids) == all_ids
    lines.append(f"- test集合与CV pool不重叠：{'通过' if disjoint_ok else '**失败**'}")
    lines.append(f"- test集合∪CV pool == 全部150条：{'通过' if union_ok else '**失败**'}")

    # 2. each fold: train/val disjoint, and for a given fold train+val == cv pool
    fold_partition_ok = True
    for fold in folds:
        tr, va = set(fold["train_ids"]), set(fold["val_ids"])
        if not tr.isdisjoint(va) or (tr | va) != cv_pool_ids:
            fold_partition_ok = False
    lines.append(f"- 每折内 train/val 不重叠且并集等于CV pool：{'通过' if fold_partition_ok else '**失败**'}")

    # 3. val folds partition the cv pool exactly once each
    val_union = set()
    val_overlap = False
    for fold in folds:
        va = set(fold["val_ids"])
        if val_union & va:
            val_overlap = True
        val_union |= va
    val_partition_ok = (not val_overlap) and (val_union == cv_pool_ids)
    lines.append(f"- 5折val集合两两不重叠、并集覆盖整个CV pool（每个样本恰好在1折的val中）："
                 f"{'通过' if val_partition_ok else '**失败**'}")

    # 4. fold size balance
    val_sizes = [len(f["val_ids"]) for f in folds]
    balanced = (max(val_sizes) - min(val_sizes)) <= 1
    lines.append(f"- 各折val集合大小：{val_sizes}（最大最小差 "
                 f"{max(val_sizes) - min(val_sizes)}，{'通过（差≤1）' if balanced else '**差距偏大，请复核**'}）")

    # 5. test set size within 10-15%
    test_frac_actual = len(test_ids) / len(all_ids)
    frac_ok = 0.10 <= test_frac_actual <= 0.15
    lines.append(f"- test集合占比：{len(test_ids)}/{len(all_ids)} = {test_frac_actual:.1%}"
                 f"（{'落在10-15%目标区间内' if frac_ok else '**超出10-15%目标区间**'}）")

    # 6. question_type coverage per fold's val set (manual-check table)
    lines.append("")
    lines.append("**每折 val 集合的题型覆盖（人工核查用）：**")
    lines.append("")
    lines.append("| fold | " + " | ".join(sorted({s["question_type"] for s in samples})) + " | val总数 |")
    qtypes_sorted = sorted({s["question_type"] for s in samples})
    lines.append("| --- | " + " | ".join(["---"] * len(qtypes_sorted)) + " | --- |")
    for fold in folds:
        counts = Counter(by_id[i]["question_type"] for i in fold["val_ids"])
        row = [str(counts.get(qt, 0)) for qt in qtypes_sorted]
        lines.append(f"| {fold['fold']} | " + " | ".join(row) + f" | {len(fold['val_ids'])} |")
    all_types_covered = all(
        set(by_id[i]["question_type"] for i in fold["val_ids"]) == set(qtypes_sorted)
        for fold in folds
    )
    lines.append("")
    lines.append(f"- 每折val集合是否覆盖全部题型：{'通过' if all_types_covered else '**存在题型缺失的折，需人工复核**'}")

    # 7. band coverage per fold's val set
    lines.append("")
    lines.append("**每折 val 集合的档位覆盖：**")
    lines.append("")
    band_order = ["0-2", "3-4", "5-6", "7-8", "9-10"]
    lines.append("| fold | " + " | ".join(band_order) + " | val总数 |")
    lines.append("| --- | " + " | ".join(["---"] * len(band_order)) + " | --- |")
    for fold in folds:
        counts = Counter(by_id[i]["band_range"] for i in fold["val_ids"])
        row = [str(counts.get(b, 0)) for b in band_order]
        lines.append(f"| {fold['fold']} | " + " | ".join(row) + f" | {len(fold['val_ids'])} |")
    all_bands_covered = all(
        set(by_id[i]["band_range"] for i in fold["val_ids"]) == set(band_order)
        for fold in folds
    )
    lines.append("")
    lines.append(f"- 每折val集合是否覆盖全部档位：{'通过' if all_bands_covered else '**存在档位缺失的折，需人工复核**'}")

    # 8. test set distribution vs overall
    lines.append("")
    lines.append("**test集合的题型 / 档位分布 vs 整体150条：**")
    lines.append("")
    overall_type = Counter(s["question_type"] for s in samples)
    test_type = Counter(by_id[i]["question_type"] for i in test_ids)
    lines.append("| 题型 | test数量 | test占比 | 整体占比 |")
    lines.append("| --- | --- | --- | --- |")
    for qt in qtypes_sorted:
        t_n = test_type.get(qt, 0)
        lines.append(
            f"| {qt} | {t_n} | {t_n/len(test_ids):.1%} | {overall_type[qt]/len(samples):.1%} |"
        )
    lines.append("")
    overall_band = Counter(s["band_range"] for s in samples)
    test_band = Counter(by_id[i]["band_range"] for i in test_ids)
    lines.append("| 档位 | test数量 | test占比 | 整体占比 |")
    lines.append("| --- | --- | --- | --- |")
    for b in band_order:
        t_n = test_band.get(b, 0)
        lines.append(
            f"| {b} | {t_n} | {t_n/len(test_ids):.1%} | {overall_band[b]/len(samples):.1%} |"
        )

    # 9. reproducibility check: re-run split() and diff
    rerun = split(samples)
    reproducible = (
        rerun["test_ids"] == result["test_ids"]
        and [f["val_ids"] for f in rerun["folds"]] == [f["val_ids"] for f in result["folds"]]
    )
    lines.append("")
    lines.append(f"- 固定随机种子（{SEED}）复现性检查（重跑一次划分逻辑对比结果）："
                 f"{'通过，结果完全一致' if reproducible else '**失败，两次结果不一致**'}")

    return lines


def append_summary(strategy: str, checklist_lines: list[str]) -> None:
    existing = SUMMARY_PATH.read_text(encoding="utf-8") if SUMMARY_PATH.exists() else ""
    marker_pos = existing.find(SPLIT_SECTION_MARKER)
    if marker_pos != -1:
        existing = existing[:marker_pos]

    section = [SPLIT_SECTION_MARKER]
    section.append("")
    section.append("## 10. 数据划分（ml/split_data.py）")
    section.append("")
    section.append(f"- N=150 < 200，主评估方式：{K_FOLDS}折分层交叉验证；另留出约"
                    f"{TEST_FRAC:.0%}作为封存test集合，全程不参与调参。")
    section.append(f"- 随机种子固定为 {SEED}。")
    strategy_label = {
        "joint_type_band": "题型×档位联合分层（15个格子，每格样本量足够支撑test+5折）",
        "band_only": "**降级为仅按档位分层**（题型×档位联合分层的格子过小，已自动降级，"
                     "见下方题型覆盖表做人工核查）",
    }[strategy]
    section.append(f"- 实际采用的分层策略：{strategy_label}")
    section.append("- 划分结果落盘于 `ml/splits/fold_0.json` ... `ml/splits/fold_4.json`"
                    "（每折存 train_ids/val_ids）与 `ml/splits/test.json`（存 test_ids）。"
                    "字段是样本的 `id`（即 review_id），后续Colab训练直接加载这份划分，"
                    "不重新划分。")
    section.append("")
    section.append("### 划分质量检查清单")
    section.append("")
    section.extend(checklist_lines)
    section.append("")

    SUMMARY_PATH.write_text(existing + "\n".join(section), encoding="utf-8")


def main() -> None:
    samples = load_samples()
    result = split(samples)
    write_splits(result)
    checklist_lines = quality_checklist(samples, result)
    append_summary(result["strategy"], checklist_lines)

    print(f"Strategy: {result['strategy']}")
    print(f"CV pool: {len(result['cv_pool_ids'])} samples across {K_FOLDS} folds")
    print(f"Test set: {len(result['test_ids'])} samples "
          f"({len(result['test_ids'])/len(samples):.1%})")
    print(f"Wrote splits to {SPLITS_DIR.relative_to(ROOT)}/")
    print(f"Appended split section to {SUMMARY_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
