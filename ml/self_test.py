"""Lightweight local self-test for the ml/ pipeline — NOT a training run.

Uses a handful of fabricated small samples (not the real 150) to exercise:
  1. ml/common.py's split/sample loading logic
  2. ml/metrics.py's metric computation
  3. ml/baselines.py's majority-class + existing-app-scoring baseline logic
  4. ml/augment.py's back-translation + leakage-check logic
  5. ml/train.py's actual torch/transformers wiring (model building, layer
     freezing, discriminative-LR optimizer groups, Trainer + label
     smoothing + early stopping) using a tiny RANDOM-INITIALIZED config of
     each supported architecture — same class as the real backbone, but
     2 layers / hidden_size 32, so no large pretrained-weight download and
     each run takes seconds, not GPU time.

Point of this script: catch wiring bugs (wrong config field name, wrong
param-group split, Trainer args that don't parse, tokenizer/dataset shape
mismatches, ...) on a laptop CPU, before spending real Colab GPU time on
xlm-roberta-base with the actual 150-sample dataset. It proves the plumbing
runs end-to-end; it says nothing about real accuracy, since both the data
and the model weights here are fake.

Run: python ml/self_test.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ml.augment as augment  # noqa: E402
import ml.baselines as baselines  # noqa: E402
import ml.common as common  # noqa: E402
import ml.error_analysis as error_analysis  # noqa: E402
import ml.learning_curve as learning_curve  # noqa: E402
import ml.metrics as metrics  # noqa: E402

_FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        _FAILURES.append(message)
        print(f"  FAIL: {message}")


# ---------------------------------------------------------------------------
# Fabricated data (small, not the real 150)
# ---------------------------------------------------------------------------

FAKE_ANSWERS = {
    "behavioral": [
        ("我上次带团队做了一个项目，情况比较复杂，最后也算完成了，大家都还满意。", 0),
        ("当时团队要在两周内上线一个新功能，我先拆解了任务分给三个人，中途发现进度落后，"
         "我协调了另一个组的两个人临时支援，最后提前一天上线，转化率提升了12%。", 3),
        ("背景是季度目标压力大，我组织了每日站会，明确分工，遇到阻碍及时协调资源，"
         "最终目标达成，复盘时团队也总结了经验用于下个季度。", 4),
        ("我们做了一个事情，结果还行。", 0),
    ],
    "technical": [
        ("这个问题可以用缓存解决。", 0),
        ("需求是接口响应慢，我分析发现是N+1查询，方案是引入批量加载和二级缓存，"
         "权衡了一致性和性能后选择了最终一致性方案，上线后P99延迟从800ms降到120ms。", 4),
        ("问题是接口偶尔超时，排查后发现是连接池不够，调大了连接池，问题缓解了。", 2),
    ],
    "case_analysis": [
        ("这个问题需要先看数据再下结论，大概是获客成本上升导致的。", 1),
        ("首先明确问题边界是过去一个月次日留存下降5个点，然后从渠道质量、产品改动、"
         "竞品动作三个方向拆解，通过分渠道数据验证发现是某个渠道量激增拉低了整体质量，"
         "短期建议收紧该渠道投放，长期建议优化归因模型，并设置周度留存监控作为验证机制。", 4),
    ],
}
BAND_RANGE = ["0-2", "3-4", "5-6", "7-8", "9-10"]


def build_fake_samples() -> dict[str, dict]:
    samples = {}
    for qtype, answers in FAKE_ANSWERS.items():
        for i, (text, band) in enumerate(answers):
            sample_id = f"fake_{qtype}_{i:02d}"
            samples[sample_id] = {
                "id": sample_id,
                "question_id": f"fake_{qtype}_q{i % 2}",
                "question_type": qtype,
                "answer_text": text,
                "answer_length": len(text),
                "structure_completeness_score": band * 2.0 + 1.0,
                "original_score_band": BAND_RANGE[band],
                "band_label": band,
                "band_range": BAND_RANGE[band],
            }
    return samples


def build_fake_fold(samples: dict[str, dict], val_ids: list[str], test_ids: list[str] = ()) -> dict:
    all_ids = list(samples)
    excluded = set(val_ids) | set(test_ids)
    train_ids = [i for i in all_ids if i not in excluded]
    return {"fold": 0, "seed": 42, "strategy": "fake", "train_ids": train_ids, "val_ids": val_ids}


def build_fake_questions():
    from models.question_schema import KeywordCluster, Question

    questions = {}
    for qtype in FAKE_ANSWERS:
        for i in range(2):
            qid = f"fake_{qtype}_q{i}"
            questions[qid] = Question(
                question_id=qid,
                question_text=f"一道假的{qtype}测试题 {i}",
                question_type=qtype,
                keyword_clusters=[KeywordCluster(canonical="目标", synonyms=["目的"])],
                reference_points=["说明背景", "说明具体做法", "说明结果"],
            )
    return questions


# ---------------------------------------------------------------------------
# 1. common.py
# ---------------------------------------------------------------------------


def test_common(tmp_dir: Path, samples: dict[str, dict]) -> None:
    print("\n[1/7] ml/common.py — split/sample loading")

    samples_path = tmp_dir / "prepared_samples.json"
    samples_path.write_text(json.dumps(list(samples.values()), ensure_ascii=False), encoding="utf-8")

    loaded = common.load_prepared_samples(samples_path)
    check(loaded == samples, "load_prepared_samples round-trips the fabricated samples")

    splits_dir = tmp_dir / "splits"
    splits_dir.mkdir()
    val_ids = list(samples)[:2]
    fold = build_fake_fold(samples, val_ids)
    (splits_dir / "fold_0.json").write_text(json.dumps(fold), encoding="utf-8")
    test_payload = {"seed": 42, "strategy": "fake", "test_frac_target": 0.15, "test_ids": list(samples)[2:4]}
    (splits_dir / "test.json").write_text(json.dumps(test_payload), encoding="utf-8")

    loaded_fold = common.load_fold(0, splits_dir=splits_dir)
    check(loaded_fold["val_ids"] == val_ids, "load_fold returns the written val_ids")
    loaded_test = common.load_test(splits_dir=splits_dir)
    check(loaded_test["test_ids"] == test_payload["test_ids"], "load_test returns the written test_ids")

    labels = common.ids_to_labels(val_ids, samples)
    check(labels == [samples[i]["band_label"] for i in val_ids], "ids_to_labels order matches input ids")

    import numpy as np

    lengths = [100] * 19 + [500]
    expected_target = float(np.percentile(lengths, 95))
    ml_val = common.compute_max_length(lengths, coverage=0.95)
    check(ml_val in (64, 128, 192, 256, 320, 384, 448, 512), f"compute_max_length returns a valid bucket, got {ml_val}")
    check(ml_val >= expected_target, f"compute_max_length bucket ({ml_val}) covers the 95th-pct value ({expected_target})")
    check(common.compute_max_length([10000], coverage=0.95) == 512, "compute_max_length caps at 512 when the target exceeds every bucket")
    check(common.compute_max_length([10, 20, 30], coverage=1.0) == 64, "compute_max_length picks the smallest sufficient bucket, not always the max")

    print("  done")


# ---------------------------------------------------------------------------
# 2. metrics.py
# ---------------------------------------------------------------------------


def test_metrics() -> None:
    print("\n[2/7] ml/metrics.py — metric computation")

    perfect = metrics.compute_metrics([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
    check(perfect["macro_f1"] == 1.0, f"perfect predictions -> macro_f1=1.0, got {perfect['macro_f1']}")
    check(perfect["qwk"] == 1.0, f"perfect predictions -> qwk=1.0, got {perfect['qwk']}")
    check(perfect["exact_accuracy"] == 1.0, "perfect predictions -> exact_accuracy=1.0")
    check(sum(sum(row) for row in perfect["confusion_matrix"]) == 5, "confusion matrix sums to n=5")

    off_by_one = metrics.compute_metrics([0, 1, 2, 3], [1, 2, 3, 4])
    check(off_by_one["exact_accuracy"] == 0.0, "all off-by-1 -> exact_accuracy=0.0")
    check(off_by_one["within1_accuracy"] == 1.0, "all off-by-1 -> within1_accuracy=1.0")

    random_ish = metrics.compute_metrics([0, 0, 4, 4], [4, 4, 0, 0])
    check(random_ish["within1_accuracy"] == 0.0, "maximally-wrong predictions -> within1_accuracy=0.0")

    print("  done")


# ---------------------------------------------------------------------------
# 3. baselines.py
# ---------------------------------------------------------------------------


def test_baselines(samples: dict[str, dict]) -> None:
    print("\n[3/7] ml/baselines.py — majority-class + existing-app-scoring baselines")

    all_ids = list(samples)
    train_ids, eval_ids = all_ids[:6], all_ids[6:]

    train_labels = common.ids_to_labels(train_ids, samples)
    pred = baselines.majority_class_baseline(train_labels, eval_ids)
    check(len(pred) == len(eval_ids), "majority_class_baseline returns one prediction per eval id")
    check(len(set(pred)) == 1, "majority_class_baseline predicts a single constant label")
    check(pred[0] in range(5), "majority_class_baseline's predicted label is a valid band index")

    questions_by_id = build_fake_questions()
    existing_pred = baselines.existing_scoring_baseline(eval_ids, samples, questions_by_id)
    check(len(existing_pred) == len(eval_ids), "existing_scoring_baseline returns one prediction per eval id")
    check(all(p in range(5) for p in existing_pred), "existing_scoring_baseline predictions are all valid band indices (0-4)")

    print("  done")


# ---------------------------------------------------------------------------
# 4. augment.py
# ---------------------------------------------------------------------------


def test_augment(samples: dict[str, dict]) -> None:
    print("\n[4/7] ml/augment.py — back-translation + leakage check")

    all_ids = list(samples)
    val_ids = all_ids[:2]
    test_ids = all_ids[2:3]
    fold = build_fake_fold(samples, val_ids, test_ids)

    def fake_translate_ok(text: str, target_lang: str) -> str:
        return text + f"[{target_lang}]"

    aug = augment.augment_fold(0, samples_by_id=samples, translate_fn=fake_translate_ok, fold=fold)
    check(len(aug) == len(fold["train_ids"]), "augment_fold produces one augmented sample per train_id when translation always succeeds")
    check(all(a["band_label"] == samples[a["source_id"]]["band_label"] for a in aug), "augmented samples keep the source's band_label unchanged")

    ok, issues = augment.check_no_leakage(aug, 0, samples_by_id=samples, fold=fold, test_ids=test_ids)
    check(ok and not issues, f"check_no_leakage passes for correctly-sourced augmented data, issues={issues}")

    def fake_translate_fail(text: str, target_lang: str):
        return None

    aug_fail = augment.augment_fold(0, samples_by_id=samples, translate_fn=fake_translate_fail, fold=fold)
    check(aug_fail == [], "augment_fold skips (not fabricates) samples when translation fails")

    # Fabricate a leak: an augmented sample whose source_id is actually a val id.
    leaked = [dict(aug[0], source_id=val_ids[0], id="leaked__bt")]
    ok2, issues2 = augment.check_no_leakage(leaked, 0, samples_by_id=samples, fold=fold, test_ids=test_ids)
    check(not ok2 and issues2, "check_no_leakage correctly flags a fabricated val->train leak")

    print("  done")


# ---------------------------------------------------------------------------
# 5. learning_curve.py — nested stratified subsampling (pure logic, no training)
# ---------------------------------------------------------------------------


def test_learning_curve(samples: dict[str, dict]) -> None:
    print("\n[5/7] ml/learning_curve.py — nested stratified subsampling")

    train_ids = list(samples)
    subsets = learning_curve.nested_stratified_subsets(train_ids, samples, fractions=(0.25, 0.5, 0.75, 1.0), seed=42)

    check(set(subsets[1.0]) == set(train_ids), "the 100% subset contains every train id")
    check(set(subsets[0.25]) <= set(subsets[0.5]) <= set(subsets[0.75]) <= set(subsets[1.0]),
          "subsets are nested (25% subset of 50% subset of 75% subset of 100%)")
    check(len(subsets[0.25]) <= len(subsets[0.5]) <= len(subsets[0.75]) <= len(subsets[1.0]),
          "subset sizes are non-decreasing with fraction")

    subsets_again = learning_curve.nested_stratified_subsets(train_ids, samples, fractions=(0.25, 0.5, 0.75, 1.0), seed=42)
    check(subsets == subsets_again, "same seed -> identical subsets (reproducible)")

    print("  done")


# ---------------------------------------------------------------------------
# 6. error_analysis.py — pure summarization/report logic
# ---------------------------------------------------------------------------


def test_error_analysis(samples: dict[str, dict]) -> None:
    print("\n[6/7] ml/error_analysis.py — error summarization")

    ids = list(samples)
    # Fabricate predictions: one major miss (|pred-true|>=2), one near miss, one exact hit.
    true_labels = {i: samples[i]["band_label"] for i in ids}
    predictions = []
    for idx, sample_id in enumerate(ids):
        true = true_labels[sample_id]
        if idx == 0:
            pred = min(4, true + 3)  # force a major miss regardless of true band
        elif idx == 1:
            pred = true
        else:
            pred = true
        predictions.append({"id": sample_id, "true": true, "pred": pred})

    major = error_analysis.find_major_misses(predictions, threshold=2)
    check(len(major) == 1 and major[0]["id"] == ids[0], "find_major_misses catches exactly the fabricated |pred-true|>=3 case")

    summary = error_analysis.summarize_errors(predictions, samples, threshold=2)
    check(summary["n_total"] == len(predictions), "summarize_errors n_total matches input size")
    check(summary["n_major_miss"] == 1, "summarize_errors n_major_miss matches find_major_misses")
    check(sum(v["total"] for v in summary["by_question_type"].values()) == len(predictions),
          "by_question_type totals sum to n_total")

    report = error_analysis.render_report("fake-model", summary)
    check("单一标注者" in report, "report includes the single-annotator caveat")
    check("kappa" in report.lower(), "report explicitly names the inter-annotator metric it's refusing to fabricate")
    check(ids[0] in report, "report lists the major-miss sample by id")

    # Length-artifact cross-check (compare_length_bias / length_error_correlation):
    # fabricate a "before" run with a constant error, and an "after" run where
    # ONLY the 3 longest-answer ids improve — this is exactly the shape a
    # length-shortcut artifact would produce, so the tool should detect a
    # clearly negative length-vs-delta correlation and a much-more-negative
    # mean_delta_abs_error in the "长" tertile than in "短"/"中".
    ids_by_len = sorted(ids, key=lambda i: samples[i]["answer_length"])
    before_preds = [{"id": i, "true": 2, "pred": 0} for i in ids_by_len]  # abs_error=2 for everyone
    after_preds = [
        {"id": i, "true": 2, "pred": 2} if rank >= 6 else {"id": i, "true": 2, "pred": 0}
        for rank, i in enumerate(ids_by_len)
    ]  # top-3-longest now exact (abs_error=0), rest unchanged (abs_error=2)

    corr = error_analysis.length_error_correlation(after_preds, samples)
    check(corr == corr, f"length_error_correlation returns a real number (not NaN) when length/error both vary, got {corr}")  # NaN != NaN

    comparison = error_analysis.compare_length_bias(before_preds, after_preds, samples)
    check(comparison["n_common"] == len(ids), "compare_length_bias uses every id present in both before/after")
    check(comparison["length_vs_delta_abs_error_correlation"] < -0.5,
          f"fabricated 'only long answers improved' case yields a clearly negative length-vs-delta correlation, got {comparison['length_vs_delta_abs_error_correlation']}")
    long_tertile = comparison["length_tertiles"][-1]
    short_tertile = comparison["length_tertiles"][0]
    check(long_tertile["mean_delta_abs_error"] < short_tertile["mean_delta_abs_error"],
          "the long-answer tertile shows more improvement (more negative delta) than the short-answer tertile, matching the fabricated artifact")
    check(abs(long_tertile["mean_delta_abs_error"] - (-2.0)) < 1e-9, "long tertile's mean delta matches the fabricated -2 improvement exactly")
    check(abs(short_tertile["mean_delta_abs_error"] - 0.0) < 1e-9, "short tertile's mean delta matches the fabricated 0 (unchanged) exactly")

    length_report = error_analysis.render_length_bias_report("fake-before", "fake-after", comparison)
    check("长度伪影" in length_report, "length-bias report is labeled as a length-artifact check")
    check("不是因果证明" in length_report or "排查线索" in length_report, "length-bias report caveats that this is correlational, not proof")

    print("  done")


# ---------------------------------------------------------------------------
# 7. train.py — real torch/transformers wiring, tiny random-config model
# ---------------------------------------------------------------------------


def test_train_smoke(samples: dict[str, dict], tmp_dir: Path) -> None:
    print("\n[7/7] ml/train.py — real Trainer smoke test (tiny random-init model, no pretrained weights)")
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        print("  SKIPPED: torch/transformers not installed locally. This is fine for the "
              "data/metrics/baseline logic above, but the actual training wiring is only "
              "verified on Colab in that case — flagging so it isn't mistaken for a pass.")
        return

    import ml.train as train

    all_ids = list(samples)
    val_ids = all_ids[:2]
    fold = build_fake_fold(samples, val_ids)
    check(len(fold["train_ids"]) >= 4, "fake dataset has enough train samples for a 2-epoch/batch-2 smoke run")

    for model_name in train.MODEL_ARCH_INFO:
        print(f"  training {model_name} for 1 epoch on {len(fold['train_ids'])} fake samples...")
        result = train.train_one_fold(
            fold_i=0,
            model_name=model_name,
            samples_by_id=samples,
            max_length=32,
            encoder_lr=1e-5,
            head_lr=5e-4,
            dropout=0.3,
            freeze_layers_n=1,
            max_epochs=1,
            patience=1,
            batch_size=2,
            monitor="macro_f1",
            label_smoothing=0.1,
            seed=42,
            from_pretrained=False,
            output_root=tmp_dir / "train_smoke",
            fold=fold,
            use_cpu=True,  # avoid MPS's scaled_dot_product_attention-with-dropout limitation on Apple Silicon
        )
        check(result["val_metrics"]["n"] == len(val_ids), f"{model_name}: val_metrics n matches val set size")
        check(len(result["val_metrics"]["confusion_matrix"]) == 5, f"{model_name}: confusion matrix is 5x5")
        check(len(result["per_sample_val"]) == len(val_ids), f"{model_name}: per_sample_val has one entry per val id")
        check(result["frozen_encoder_layers"] == train.effective_freeze_count(model_name, 1),
              f"{model_name}: frozen_encoder_layers matches effective_freeze_count")
        check(0.0 <= result["train_metrics"]["macro_f1"] <= 1.0, f"{model_name}: train macro_f1 is a valid ratio")

    print("  done")


# ---------------------------------------------------------------------------


def main() -> None:
    samples = build_fake_samples()
    print(f"Fabricated {len(samples)} fake samples across {len(FAKE_ANSWERS)} question types for self-test.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        test_common(tmp_dir, samples)
        test_metrics()
        test_baselines(samples)
        test_augment(samples)
        test_learning_curve(samples)
        test_error_analysis(samples)
        test_train_smoke(samples, tmp_dir)

    print()
    if _FAILURES:
        print(f"SELF-TEST FAILED: {len(_FAILURES)} check(s) failed:")
        for f in _FAILURES:
            print(f"  - {f}")
        raise SystemExit(1)
    print("SELF-TEST PASSED: all checks green. Safe to move this to Colab.")


if __name__ == "__main__":
    main()
