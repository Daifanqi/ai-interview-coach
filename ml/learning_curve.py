"""Learning curve: compare val performance at 25/50/75/100% of a fold's
training data, to see whether more labeled data would plausibly help (vs.
the model having already plateaued at N=150's scale).

Lower priority than train.py per the task spec ("time permitting") — this
defaults to a single representative fold (--fold 0) rather than all 5, to
keep the 4x-the-training-cost of a full learning curve bounded. Pass
--folds to average over more folds if there's time.

Subsampling is stratified by band_label and NESTED across fractions (the
25% subset is a subset of the 50% subset, etc., via one fixed seeded
shuffle per band) — so 25%->50%->75%->100% is a genuine "more of the same
data added", not four independent re-samples with the same fraction of
each band. This makes the resulting curve interpretable rather than noisy
from resampling variance."""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ml.common as common  # noqa: E402
import ml.metrics as metrics  # noqa: E402
from ml.train import build_arg_parser, train_one_fold  # noqa: E402

RESULTS_DIR = ROOT / "ml" / "results" / "learning_curve"
FRACTIONS = (0.25, 0.5, 0.75, 1.0)


def nested_stratified_subsets(
    train_ids: list[str], samples_by_id: dict, fractions: tuple[float, ...] = FRACTIONS, seed: int = 42
) -> dict[float, list[str]]:
    """{fraction: subset_of_train_ids}, nested (subset(0.25) ⊆ subset(0.5) ⊆ ...),
    stratified per band_label so each fraction keeps roughly the fold's band mix."""
    by_band: dict[int, list[str]] = defaultdict(list)
    for i in train_ids:
        by_band[samples_by_id[i]["band_label"]].append(i)

    rng = random.Random(seed)
    for band in by_band:
        rng.shuffle(by_band[band])

    subsets = {}
    for frac in sorted(fractions):
        subset = []
        for band, ids in by_band.items():
            take = max(1, round(len(ids) * frac)) if ids else 0
            subset.extend(ids[:take])
        subsets[frac] = subset
    return subsets


def run_learning_curve(
    fold_indices: list[int],
    model_name: str,
    samples_by_id: dict,
    max_length: int,
    train_kwargs: dict,
    fractions: tuple[float, ...] = FRACTIONS,
) -> dict:
    results_by_fraction: dict[float, list[dict]] = defaultdict(list)

    for fold_i in fold_indices:
        fold = common.load_fold(fold_i)
        subsets = nested_stratified_subsets(fold["train_ids"], samples_by_id, fractions=fractions)
        for frac in fractions:
            print(f"\n=== fold {fold_i}, {frac:.0%} of train ({len(subsets[frac])} samples) ===")
            result = train_one_fold(
                fold_i=fold_i,
                model_name=model_name,
                samples_by_id=samples_by_id,
                max_length=max_length,
                fold=fold,
                train_ids_override=subsets[frac],
                output_root=RESULTS_DIR / f"frac_{frac}",
                **train_kwargs,
            )
            results_by_fraction[frac].append(result["val_metrics"])
            print(metrics.format_metrics(result["val_metrics"], f"fold {fold_i} @ {frac:.0%}"))

    import numpy as np

    summary = {"model_name": model_name, "folds": fold_indices, "fractions": {}}
    for frac in fractions:
        val_list = results_by_fraction[frac]
        summary["fractions"][frac] = {
            "n_folds": len(val_list),
            "mean_macro_f1": float(np.mean([v["macro_f1"] for v in val_list])),
            "mean_qwk": float(np.mean([v["qwk"] for v in val_list])),
            "mean_within1_accuracy": float(np.mean([v["within1_accuracy"] for v in val_list])),
        }
    return summary


def main() -> None:
    parser = build_arg_parser()
    parser.add_argument("--fold", type=int, default=0, help="Single fold to run the curve on (default: fold 0). Ignored if --folds is passed explicitly.")
    args = parser.parse_args()
    if args.folds == list(range(common.K_FOLDS)):
        # build_arg_parser()'s default is "all 5 folds", which is too expensive
        # here by default — learning_curve.py defaults to just --fold instead
        # unless the caller explicitly passed --folds.
        args.folds = [args.fold]

    samples_by_id = common.load_prepared_samples()
    max_length = args.max_length or common.default_max_length(samples_by_id)

    train_kwargs = dict(
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
    )

    summary = run_learning_curve(args.folds, args.model, samples_by_id, max_length, train_kwargs)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.model}_summary.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== learning curve summary ({args.model}) ===")
    for frac, stats in sorted(summary["fractions"].items()):
        print(f"  {float(frac):>5.0%}  macro_f1={stats['mean_macro_f1']:.3f}  "
              f"qwk={stats['mean_qwk']:.3f}  within1_acc={stats['mean_within1_accuracy']:.3f}")
    print(f"Wrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
