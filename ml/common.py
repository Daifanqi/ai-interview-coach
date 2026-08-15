"""Shared, dependency-light helpers for the Week 7+ ml/ scripts.

Deliberately import only the stdlib (plus numpy, already in
ml/requirements.txt) at module level, so this module — and anything that
only needs it (metrics.py, baselines.py's data plumbing, self_test.py) —
can be imported without torch/transformers installed. train.py imports
those heavy libraries lazily inside its own functions for the same reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_PATH = ROOT / "ml" / "data" / "prepared_samples.json"
SPLITS_DIR = ROOT / "ml" / "splits"
K_FOLDS = 5


def load_prepared_samples(samples_path: Path = SAMPLES_PATH) -> dict[str, dict]:
    """Returns {id: sample_dict}. Raises if the file is missing (run prepare_data.py first)."""
    if not samples_path.exists():
        raise FileNotFoundError(
            f"{samples_path} not found — run ml/prepare_data.py first to generate it."
        )
    with samples_path.open(encoding="utf-8") as f:
        samples = json.load(f)
    return {s["id"]: s for s in samples}


def load_fold(fold_i: int, splits_dir: Path = SPLITS_DIR) -> dict:
    """Returns the raw fold_{fold_i}.json payload: fold/seed/strategy/train_ids/val_ids."""
    path = splits_dir / f"fold_{fold_i}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — run ml/split_data.py first, or check fold_i is in "
            f"range(0, {K_FOLDS})."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_test(splits_dir: Path = SPLITS_DIR) -> dict:
    """Returns the raw test.json payload: seed/strategy/test_frac_target/test_ids."""
    path = splits_dir / "test.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run ml/split_data.py first.")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ids_to_labels(ids: list[str], samples_by_id: dict[str, dict]) -> list[int]:
    """band_label (0-4) for each id, in the same order as `ids`."""
    return [samples_by_id[i]["band_label"] for i in ids]


def ids_to_texts(ids: list[str], samples_by_id: dict[str, dict]) -> list[str]:
    return [samples_by_id[i]["answer_text"] for i in ids]


# Standard transformer sequence-length buckets. Picking from this list
# (rather than an arbitrary round-to-multiple-of-8 value) keeps max_length
# aligned with lengths people actually benchmark/tune tokenizer batching
# against, and caps at 512 (xlm-roberta-base's / distilbert's position
# embedding limit).
_LENGTH_BUCKETS = (64, 128, 192, 256, 320, 384, 448, 512)


def compute_max_length(
    lengths: list[int], coverage: float = 0.95, buckets: tuple[int, ...] = _LENGTH_BUCKETS
) -> int:
    """Smallest bucket size covering `coverage` fraction of `lengths`.

    NOTE: `lengths` here are *character* counts (answer_length in
    prepared_samples.json), not tokenizer subword-token counts — this is a
    deliberate simplification per the task spec (derive max_length from the
    character-length distribution in ml/data_summary.md). For Chinese text
    tokenized by a sentencepiece model, token count tracks character count
    reasonably closely (often close to 1:1, sometimes a bit higher), so this
    likely UNDER-covers `coverage` slightly on token count. train.py logs
    the actual truncation rate against real tokenizer output at run time so
    this approximation's error is visible rather than silently assumed away.
    """
    if not lengths:
        raise ValueError("compute_max_length: lengths is empty")
    target = float(np.percentile(np.array(lengths), coverage * 100))
    for bucket in buckets:
        if bucket >= target:
            return bucket
    return buckets[-1]


def default_max_length(samples_by_id: dict[str, dict] | None = None, coverage: float = 0.95) -> int:
    """compute_max_length() over the full 150-sample prepared dataset (all folds + test)."""
    if samples_by_id is None:
        samples_by_id = load_prepared_samples()
    lengths = [s["answer_length"] for s in samples_by_id.values()]
    return compute_max_length(lengths, coverage=coverage)
