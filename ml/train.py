"""Fine-tune a transformer classifier for structure_completeness (5 bands)
on the Week 7 dataset, evaluated via the 5-fold CV split in ml/splits/.

Primary backbone: xlm-roberta-base. Fallback (if xlm-roberta-base shows
clear overfitting — see the train/val macro-F1 gap this script prints after
each run): distilbert-base-multilingual-cased, a smaller model, via
--model.

Recipe (all CLI-configurable, defaults are the middle of each range in the
task spec):
- embeddings + bottom N encoder layers frozen (--freeze-layers, 6-8)
- discriminative learning rates: encoder --encoder-lr (1e-5~2e-5),
  classifier head --head-lr (5e-4~1e-3)
- classifier head dropout --dropout (0.3-0.5)
- label smoothing --label-smoothing (0.1)
- up to --max-epochs (20-30) with early stopping, --patience (3-5),
  monitoring --monitor (macro_f1 or qwk)
- --batch-size (8-16)
- max sequence length: ml.common.default_max_length() (95th-percentile
  character length from ml/data_summary.md, rounded up to a standard
  bucket — currently 512)

Only imports torch/transformers *inside* functions (never at module level)
so this module stays importable — and its pure-Python pieces (arch
metadata, CLI, hyperparameter defaults, overfit-gap check) stay testable —
on a machine without those installed. ml/self_test.py exercises the actual
torch/transformers path too, but with a tiny random-initialized config
(no real pretrained-weight download) standing in for the real backbone.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ml.common as common  # noqa: E402
import ml.metrics as metrics  # noqa: E402

RESULTS_DIR = ROOT / "ml" / "results" / "train"
AUGMENTED_DIR = ROOT / "ml" / "data" / "augmented"

# Architecture-specific attribute paths, used by freeze_layers() and
# build_model()'s dropout config field — the two things that differ enough
# between model families that a single generic code path can't cover both.
MODEL_ARCH_INFO = {
    "xlm-roberta-base": {
        "family": "roberta",
        "num_layers": 12,
        "dropout_config_field": "classifier_dropout",
    },
    "distilbert-base-multilingual-cased": {
        "family": "distilbert",
        "num_layers": 6,
        "dropout_config_field": "seq_classif_dropout",
    },
}

NUM_LABELS = 5
OVERFIT_GAP_THRESHOLD = 0.15  # train_macro_f1 - val_macro_f1 above this -> suggest switching model


# ---------------------------------------------------------------------------
# Pure-Python pieces (no torch/transformers) — covered directly by self_test.py
# ---------------------------------------------------------------------------


def resolve_arch(model_name: str) -> dict:
    if model_name not in MODEL_ARCH_INFO:
        raise ValueError(f"Unsupported model {model_name!r}; add it to MODEL_ARCH_INFO first.")
    return MODEL_ARCH_INFO[model_name]


def effective_freeze_count(model_name: str, requested: int) -> int:
    """Clamp the requested freeze-layer count to the model's actual layer count,
    leaving at least 1 encoder layer trainable (freezing every layer would
    leave the encoder unable to adapt at all, only the head would train)."""
    arch = resolve_arch(model_name)
    return max(0, min(requested, arch["num_layers"] - 1))


def overfit_gap(train_macro_f1: float, val_macro_f1: float) -> float:
    return train_macro_f1 - val_macro_f1


def check_overfit_and_suggest(model_name: str, train_macro_f1: float, val_macro_f1: float) -> str | None:
    gap = overfit_gap(train_macro_f1, val_macro_f1)
    if gap <= OVERFIT_GAP_THRESHOLD:
        return None
    suggestion = (
        f"Overfitting signal: mean train macro-F1 ({train_macro_f1:.3f}) exceeds mean val "
        f"macro-F1 ({val_macro_f1:.3f}) by {gap:.3f} (> {OVERFIT_GAP_THRESHOLD} threshold)."
    )
    if model_name == "xlm-roberta-base":
        suggestion += " Consider re-running with --model distilbert-base-multilingual-cased."
    return suggestion


# ---------------------------------------------------------------------------
# Dataset (plain torch.utils.data.Dataset — avoids an extra `datasets` dep)
# ---------------------------------------------------------------------------


def _build_dataset(texts: list[str], labels: list[int], tokenizer, max_length: int):
    import torch

    encodings = tokenizer(
        texts, truncation=True, padding="max_length", max_length=max_length, return_tensors="pt"
    )

    class _EncodedDataset(torch.utils.data.Dataset):
        def __len__(self_inner):
            return len(labels)

        def __getitem__(self_inner, idx):
            item = {k: v[idx] for k, v in encodings.items()}
            item["labels"] = torch.tensor(labels[idx], dtype=torch.long)
            return item

    return _EncodedDataset()


# ---------------------------------------------------------------------------
# Model construction, freezing, discriminative optimizer
# ---------------------------------------------------------------------------


def build_model_and_tokenizer(model_name: str, dropout: float, from_pretrained: bool = True):
    """from_pretrained=False builds a tiny random-initialized model of the same
    architecture class instead of downloading real pretrained weights — used
    by ml/self_test.py for a fast, network-light smoke test of everything
    *except* the pretrained weights themselves."""
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

    arch = resolve_arch(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    config_kwargs = {"num_labels": NUM_LABELS, arch["dropout_config_field"]: dropout}
    config = AutoConfig.from_pretrained(model_name, **config_kwargs)

    if from_pretrained:
        model = AutoModelForSequenceClassification.from_pretrained(model_name, config=config)
    else:
        config.num_hidden_layers = min(config.num_hidden_layers, 2)
        config.hidden_size = 32
        config.intermediate_size = 64
        config.num_attention_heads = 2
        if hasattr(config, "dim"):  # distilbert names these differently
            config.dim = 32
            config.hidden_dim = 64
            config.n_heads = 2
            config.n_layers = min(config.n_layers, 2)
        model = AutoModelForSequenceClassification.from_config(config)

    return model, tokenizer


def freeze_layers(model, model_name: str, n_layers_to_freeze: int) -> int:
    """Freezes the base model's embeddings + its bottom `n_layers_to_freeze`
    encoder layers (clamped via effective_freeze_count). Returns the actual
    number of layers frozen."""
    arch = resolve_arch(model_name)
    n = effective_freeze_count(model_name, n_layers_to_freeze)
    base_model = getattr(model, model.base_model_prefix)

    if arch["family"] == "roberta":
        for param in base_model.embeddings.parameters():
            param.requires_grad = False
        for layer in base_model.encoder.layer[:n]:
            for param in layer.parameters():
                param.requires_grad = False
    elif arch["family"] == "distilbert":
        for param in base_model.embeddings.parameters():
            param.requires_grad = False
        for layer in base_model.transformer.layer[:n]:
            for param in layer.parameters():
                param.requires_grad = False
    else:
        raise ValueError(f"Unhandled arch family {arch['family']!r}")

    return n


def build_discriminative_optimizer(model, encoder_lr: float, head_lr: float):
    """Two param groups: base-model (encoder) params at encoder_lr, everything
    else (the classification head) at head_lr. Frozen params (requires_grad
    False, from freeze_layers()) are excluded — Trainer/AdamW never touch them."""
    import torch

    prefix = model.base_model_prefix
    encoder_params, head_params = [], []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        (encoder_params if name.startswith(prefix + ".") else head_params).append(param)

    if not head_params:
        raise RuntimeError(
            "build_discriminative_optimizer: no trainable classifier-head params found — "
            "check base_model_prefix / freeze_layers didn't accidentally freeze the head."
        )

    param_groups = [{"params": encoder_params, "lr": encoder_lr}, {"params": head_params, "lr": head_lr}]
    return torch.optim.AdamW(param_groups)


# ---------------------------------------------------------------------------
# Per-fold training
# ---------------------------------------------------------------------------


def compute_metrics_fn(eval_pred):
    import numpy as np

    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    result = metrics.compute_metrics(labels.tolist(), preds.tolist())
    # Trainer logs this dict as-is; keep it flat/numeric (drop the nested
    # confusion matrix here, it's recomputed separately after training).
    return {k: v for k, v in result.items() if k not in ("confusion_matrix", "confusion_matrix_labels")}


def train_one_fold(
    fold_i: int,
    model_name: str,
    samples_by_id: dict,
    max_length: int,
    encoder_lr: float,
    head_lr: float,
    dropout: float,
    freeze_layers_n: int,
    max_epochs: int,
    patience: int,
    batch_size: int,
    monitor: str,
    label_smoothing: float,
    seed: int,
    use_augmented: bool = False,
    from_pretrained: bool = True,
    output_root: Path | None = None,
    fold: dict | None = None,
    train_ids_override: list[str] | None = None,
    use_cpu: bool = False,  # force CPU; needed on Apple Silicon (MPS) dev machines, where
    # scaled_dot_product_attention doesn't support dropout>0 as of this transformers
    # version. Leave False on Colab so it uses the GPU.
    run_name: str | None = None,  # results/checkpoint subdir; defaults to model_name.
    # Pass something like f"{model_name}__augmented" so a --augment run doesn't
    # silently overwrite the non-augmented run's results at the same path.
) -> dict:
    from transformers import EarlyStoppingCallback, Trainer, TrainingArguments, set_seed

    set_seed(seed)

    fold = fold or common.load_fold(fold_i)
    train_ids = list(train_ids_override) if train_ids_override is not None else list(fold["train_ids"])
    val_ids = list(fold["val_ids"])

    train_samples = [dict(samples_by_id[i], id=i) for i in train_ids]
    if use_augmented:
        aug_path = AUGMENTED_DIR / f"fold_{fold_i}_train_augmented.json"
        if not aug_path.exists():
            raise FileNotFoundError(f"{aug_path} not found — run ml/augment.py first (or drop --augment).")
        train_samples.extend(json.loads(aug_path.read_text(encoding="utf-8")))

    train_texts = [s["answer_text"] for s in train_samples]
    train_labels = [s["band_label"] for s in train_samples]
    val_texts = common.ids_to_texts(val_ids, samples_by_id)
    val_labels = common.ids_to_labels(val_ids, samples_by_id)

    model, tokenizer = build_model_and_tokenizer(model_name, dropout, from_pretrained=from_pretrained)
    frozen_n = freeze_layers(model, model_name, freeze_layers_n)
    optimizer = build_discriminative_optimizer(model, encoder_lr, head_lr)

    train_dataset = _build_dataset(train_texts, train_labels, tokenizer, max_length)
    val_dataset = _build_dataset(val_texts, val_labels, tokenizer, max_length)

    run_name = run_name or model_name
    output_dir = (output_root or RESULTS_DIR) / run_name / f"fold_{fold_i}" / "checkpoints"
    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=max_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=max(batch_size * 2, batch_size),
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model=f"eval_{monitor}",
        greater_is_better=True,
        label_smoothing_factor=label_smoothing,
        logging_strategy="epoch",
        report_to=[],
        seed=seed,
        disable_tqdm=True,
        use_cpu=use_cpu,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics_fn,
        optimizers=(optimizer, None),
        callbacks=[EarlyStoppingCallback(early_stopping_patience=patience)],
    )
    trainer.train()

    import numpy as np

    val_pred_logits = trainer.predict(val_dataset).predictions
    val_preds = np.argmax(val_pred_logits, axis=-1).tolist()
    val_metrics = metrics.compute_metrics(val_labels, val_preds)

    train_pred_logits = trainer.predict(train_dataset).predictions
    train_preds = np.argmax(train_pred_logits, axis=-1).tolist()
    train_metrics = metrics.compute_metrics(train_labels, train_preds)

    per_sample_val = [{"id": i, "true": t, "pred": p} for i, t, p in zip(val_ids, val_labels, val_preds)]

    return {
        "fold": fold_i,
        "model_name": model_name,
        "frozen_encoder_layers": frozen_n,
        "n_train": len(train_samples),
        "n_val": len(val_ids),
        "used_augmented": use_augmented,
        "val_metrics": val_metrics,
        "train_metrics": train_metrics,
        "per_sample_val": per_sample_val,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="xlm-roberta-base", choices=list(MODEL_ARCH_INFO))
    parser.add_argument("--folds", type=int, nargs="*", default=list(range(common.K_FOLDS)))
    parser.add_argument("--augment", action="store_true", help="Append ml/data/augmented/fold_{i}_train_augmented.json to each fold's training set.")
    parser.add_argument("--max-epochs", type=int, default=25)
    parser.add_argument("--patience", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--encoder-lr", type=float, default=1.5e-5)
    parser.add_argument("--head-lr", type=float, default=7e-4)
    parser.add_argument("--dropout", type=float, default=0.4)
    parser.add_argument("--freeze-layers", type=int, default=7)
    parser.add_argument("--monitor", choices=["macro_f1", "qwk"], default="macro_f1")
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-length", type=int, default=None, help="Default: ml.common.default_max_length().")
    return parser


def resolve_run_name(model_name: str, augment: bool) -> str:
    """Results/checkpoint subdir name. A --augment run must NOT share a path with
    the plain run of the same model — otherwise one silently overwrites the
    other's results, and there's nothing left to feed augment.py's before/after
    comparison."""
    return f"{model_name}__augmented" if augment else model_name


def main() -> None:
    args = build_arg_parser().parse_args()
    run_name = resolve_run_name(args.model, args.augment)

    samples_by_id = common.load_prepared_samples()
    max_length = args.max_length or common.default_max_length(samples_by_id)

    fold_results = []
    for fold_i in args.folds:
        print(f"\n=== fold {fold_i} ({run_name}) ===")
        result = train_one_fold(
            fold_i=fold_i,
            model_name=args.model,
            samples_by_id=samples_by_id,
            max_length=max_length,
            encoder_lr=args.encoder_lr,
            head_lr=args.head_lr,
            dropout=args.dropout,
            freeze_layers_n=args.freeze_layers,
            max_epochs=args.max_epochs,
            patience=args.patience,
            batch_size=args.batch_size,
            monitor=args.monitor,
            label_smoothing=args.label_smoothing,
            seed=args.seed,
            use_augmented=args.augment,
            run_name=run_name,
        )
        fold_results.append(result)
        print(metrics.format_metrics(result["val_metrics"], f"fold {fold_i} val"))

        out_dir = RESULTS_DIR / run_name
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / f"fold_{fold_i}_metrics.json").open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    if len(fold_results) == common.K_FOLDS:
        _write_summary(args.model, run_name, fold_results, args)


def _write_summary(model_name: str, run_name: str, fold_results: list[dict], args: argparse.Namespace) -> None:
    import numpy as np

    val_macro_f1s = [r["val_metrics"]["macro_f1"] for r in fold_results]
    train_macro_f1s = [r["train_metrics"]["macro_f1"] for r in fold_results]

    summary = {
        "model_name": model_name,
        "run_name": run_name,
        "hyperparams": vars(args),
        "per_fold": [
            {
                "fold": r["fold"],
                "val_macro_f1": r["val_metrics"]["macro_f1"],
                "val_qwk": r["val_metrics"]["qwk"],
                "val_within1_accuracy": r["val_metrics"]["within1_accuracy"],
                "train_macro_f1": r["train_metrics"]["macro_f1"],
            }
            for r in fold_results
        ],
        "mean_val_macro_f1": float(np.mean(val_macro_f1s)),
        "std_val_macro_f1": float(np.std(val_macro_f1s)),
        "mean_val_qwk": float(np.mean([r["val_metrics"]["qwk"] for r in fold_results])),
        "mean_val_within1_accuracy": float(np.mean([r["val_metrics"]["within1_accuracy"] for r in fold_results])),
        "mean_train_macro_f1": float(np.mean(train_macro_f1s)),
    }

    overfit_msg = check_overfit_and_suggest(model_name, summary["mean_train_macro_f1"], summary["mean_val_macro_f1"])
    summary["overfit_warning"] = overfit_msg

    # Out-of-fold predictions across all 5 val folds, for ml/error_analysis.py.
    oof = [sample for r in fold_results for sample in r["per_sample_val"]]

    out_dir = RESULTS_DIR / run_name
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with (out_dir / "oof_predictions.json").open("w", encoding="utf-8") as f:
        json.dump(oof, f, ensure_ascii=False, indent=2)

    print(f"\n=== summary ({run_name}) ===")
    print(f"mean val macro_f1={summary['mean_val_macro_f1']:.3f} (+/-{summary['std_val_macro_f1']:.3f})  "
          f"mean val qwk={summary['mean_val_qwk']:.3f}  mean val within1_acc={summary['mean_val_within1_accuracy']:.3f}")
    if overfit_msg:
        print(f"WARNING: {overfit_msg}")
    print(f"Wrote {out_dir.relative_to(ROOT)}/summary.json and oof_predictions.json")


if __name__ == "__main__":
    main()
