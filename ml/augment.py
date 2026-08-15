"""Back-translation data augmentation (zh -> en -> zh) for the CV training folds.

Only ever applied to a fold's train_ids — ml/splits/fold_{i}.json's val_ids
(and ml/splits/test.json's test_ids) are never touched, and check_no_leakage()
below verifies that after the fact rather than just by construction, in case
a future edit to augment_fold() breaks that invariant.

The label is carried over unchanged from the source answer: back-translation
is assumed to preserve structure_completeness (STAR/problem-solution/five-step
element presence survives a round-trip translation reasonably well — it's a
paraphrase, not a rewrite), which is why this augmentation targets that label
specifically. This assumption is not verified here; if augmented-vs-baseline
metrics in train.py look off, spot-check a few augmented pairs by eye first.

Default translator: local Helsinki-NLP MarianMT models (opus-mt-zh-en /
opus-mt-en-zh) run directly via transformers, batched, on whatever device
torch.cuda.is_available() picks. Originally this called the project's Groq
LLM client instead; that was dropped after a real Colab run showed Groq's
free-tier daily token quota (shared with backend/conversation/llm_client.py's
interview-dialogue usage of the same llama-3.3-70b-versatile model) getting
exhausted mid-run, which no amount of retry/backoff tuning fixes -- see
docs/decision_log.md's entry on this switch for the full reasoning. A local
model has no external rate limit or quota to run into, and this is a batch
job with no per-request latency budget, so batching for GPU throughput
instead of a call-per-item loop is a straightforward win here (unlike
backend/conversation/llm_client.py's real-time call sites, which can't batch
across independent users' turns).

A translation failure (OOM even after retrying at a smaller sub-batch size,
or the model failing to load at all) is treated exactly like the old
Groq-failure case: the affected sample is skipped, not silently dropped --
see augment_fold()'s and main()'s skip-accounting, which persists the skip
list to fold_{i}_train_augmented.skip_report.json regardless of which
translator produced the skip.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ml.common as common  # noqa: E402

AUGMENTED_DIR = ROOT / "ml" / "data" / "augmented"

TranslateFn = Callable[[str, str], Optional[str]]


# ---------------------------------------------------------------------------
# Default translator: local MarianMT models (opus-mt-zh-en / opus-mt-en-zh)
# ---------------------------------------------------------------------------

# Keyed by target_lang, matching default_translate(text, target_lang)'s
# existing signature: target_lang="en" means "translate INTO English" (the
# zh->en hop), target_lang="zh" means "translate INTO Chinese" (the en->zh
# hop back).
_MARIAN_MODEL_NAMES = {
    "en": "Helsinki-NLP/opus-mt-zh-en",
    "zh": "Helsinki-NLP/opus-mt-en-zh",
}

# Answers in prepared_samples.json run up to 543 chars (ml/data_summary.md);
# generous margins on both ends so a long answer doesn't get silently
# truncated going in, or cut off coming out.
_MAX_INPUT_TOKENS = 512
_MAX_NEW_TOKENS = 512

_DEFAULT_BATCH_SIZE = 16

# tokenizer/model per target_lang, loaded lazily on first use so importing
# this module (e.g. just for compare_metrics()) doesn't pay the
# torch/transformers import + model download cost. A failed load is cached
# as None so a persistently broken environment (e.g. no network to fetch
# weights) fails fast on every subsequent item instead of retrying a slow
# download every time.
_marian_cache: dict[str, Optional[tuple]] = {}
_device = None


def _get_device():
    """cuda if available, else cpu -- picked once and cached."""
    global _device
    if _device is None:
        import torch

        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _device


def _load_marian(target_lang: str) -> Optional[tuple]:
    """Lazily load+cache the tokenizer/model that translates INTO target_lang.

    Returns None (rather than raising) on any load failure -- missing
    sentencepiece/sacremoses, no network to fetch weights, etc. -- so a
    load failure degrades to "every item in this direction is skipped" via
    the normal None-means-skip convention, instead of crashing the whole
    fold and losing every sample's progress.
    """
    if target_lang in _marian_cache:
        return _marian_cache[target_lang]

    model_name = _MARIAN_MODEL_NAMES[target_lang]
    try:
        from transformers import MarianMTModel, MarianTokenizer

        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name).to(_get_device())
        model.eval()
    except Exception as exc:  # noqa: BLE001 -- any load failure must degrade, not crash the fold
        print(f"WARNING: failed to load local translation model {model_name!r}: {exc!r} "
              f"-- every sample needing this direction will be skipped.")
        _marian_cache[target_lang] = None
        return None

    _marian_cache[target_lang] = (tokenizer, model)
    return _marian_cache[target_lang]


def _translate_chunk(chunk: list[str], tokenizer, model, device, depth: int = 0) -> list[Optional[str]]:
    """Translate one batch. On CUDA OOM, halve and retry recursively (down to
    batch size 1) to salvage whatever the GPU can actually fit rather than
    failing the whole chunk; a batch size of 1 that still OOMs, or any
    non-OOM failure, marks just that item(s) as skipped (None).
    """
    import torch

    try:
        inputs = tokenizer(
            chunk, return_tensors="pt", padding=True, truncation=True, max_length=_MAX_INPUT_TOKENS
        ).to(device)
        with torch.no_grad():
            generated = model.generate(**inputs, max_new_tokens=_MAX_NEW_TOKENS)
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        return [(d.strip() or None) for d in decoded]
    except RuntimeError as exc:
        is_oom = "out of memory" in str(exc).lower()
        if is_oom and device.type == "cuda":
            torch.cuda.empty_cache()
        if not is_oom or len(chunk) == 1:
            print(f"WARNING: local translation failed for {len(chunk)} item(s), skipping: {exc!r}")
            return [None] * len(chunk)
        half = max(1, len(chunk) // 2)
        print(f"WARNING: local translation OOM on a batch of {len(chunk)}, retrying as "
              f"{half}+{len(chunk) - half} sub-batches...")
        return (
            _translate_chunk(chunk[:half], tokenizer, model, device, depth + 1)
            + _translate_chunk(chunk[half:], tokenizer, model, device, depth + 1)
        )
    except Exception as exc:  # noqa: BLE001 -- any other failure must degrade, not crash the fold
        print(f"WARNING: local translation failed for {len(chunk)} item(s) (non-OOM): {exc!r}, skipping.")
        return [None] * len(chunk)


def _marian_translate_batch(
    texts: list[str], target_lang: str, batch_size: int = _DEFAULT_BATCH_SIZE
) -> list[Optional[str]]:
    """Translate `texts` INTO target_lang ("en" or "zh"), batched for GPU
    throughput. One result per input text, in the same order; None where
    that item failed (model load failure, OOM even at batch size 1, or an
    empty completion).
    """
    if target_lang not in _MARIAN_MODEL_NAMES:
        raise ValueError(f"target_lang must be 'en' or 'zh', got {target_lang!r}")
    if not texts:
        return []

    loaded = _load_marian(target_lang)
    if loaded is None:
        return [None] * len(texts)
    tokenizer, model = loaded
    device = _get_device()

    results: list[Optional[str]] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        results.extend(_translate_chunk(chunk, tokenizer, model, device))
    return results


def default_translate(text: str, target_lang: str) -> Optional[str]:
    """target_lang: "en" or "zh". Returns None if translation failed.

    Single-item convenience wrapper around _marian_translate_batch() so this
    keeps the same TranslateFn interface as before (and stays usable
    standalone, e.g. via back_translate()) -- augment_fold()'s production
    path below calls _marian_translate_batch()/back_translate_batch()
    directly instead, since batching across the whole fold is what actually
    speeds this up on GPU.
    """
    return _marian_translate_batch([text], target_lang)[0]


# ---------------------------------------------------------------------------
# Back-translation + fold augmentation
# ---------------------------------------------------------------------------


def back_translate(text: str, translate_fn: TranslateFn = default_translate) -> Optional[str]:
    """zh -> en -> zh round trip for a single text. Returns None if either
    hop fails. Not used by augment_fold()'s production path (see
    back_translate_batch()) -- kept for standalone use and for the
    translate_fn-override path tests rely on.
    """
    en = translate_fn(text, "en")
    if en is None:
        return None
    zh = translate_fn(en, "zh")
    if zh is None:
        return None
    return zh


def back_translate_batch(texts: list[str]) -> list[Optional[str]]:
    """zh -> en -> zh round trip for a whole batch, via the local MarianMT
    models directly (bypasses the single-text TranslateFn interface entirely
    so both hops actually batch). None per item where either hop failed;
    an item that fails the first hop is simply not sent through the second.
    """
    en_texts = _marian_translate_batch(texts, "en")

    hop2_indices = [i for i, t in enumerate(en_texts) if t is not None]
    hop2_inputs = [en_texts[i] for i in hop2_indices]
    hop2_results = _marian_translate_batch(hop2_inputs, "zh") if hop2_inputs else []

    results: list[Optional[str]] = [None] * len(texts)
    for pos, i in enumerate(hop2_indices):
        results[i] = hop2_results[pos]
    return results


def augment_fold(
    fold_i: int,
    samples_by_id: dict[str, dict] | None = None,
    translate_fn: TranslateFn = default_translate,
    fold: dict | None = None,
) -> list[dict]:
    """Back-translate every train_id in fold_{fold_i}.json (or the given `fold`
    dict, for testing with fabricated splits instead of the real ml/splits/).
    Returns the list of augmented sample dicts (same shape as
    prepared_samples.json entries, plus source_id/augmented fields). Samples
    where back-translation failed are skipped (printed, not silently dropped).
    """
    if samples_by_id is None:
        samples_by_id = common.load_prepared_samples()

    fold = fold or common.load_fold(fold_i)
    train_ids = fold["train_ids"]

    if translate_fn is default_translate:
        # Production path: batch the whole fold through the local MarianMT
        # models directly, instead of looping back_translate() once per
        # item -- batching is what actually gets GPU throughput here; a
        # call-per-item loop leaves the GPU mostly idle between tiny
        # single-sentence forward passes.
        print(f"fold {fold_i}: batch back-translating {len(train_ids)} train samples "
              f"on {_get_device()}...", flush=True)
        texts = [samples_by_id[source_id]["answer_text"] for source_id in train_ids]
        translations = back_translate_batch(texts)
    else:
        # A translate_fn override (e.g. self_test.py's fakes, or any other
        # custom single-text translator) -- keep the original per-item path,
        # unchanged, so injected translators keep working exactly as before.
        translations = []
        for i, source_id in enumerate(train_ids, start=1):
            source = samples_by_id[source_id]
            print(f"  [{i}/{len(train_ids)}] fold {fold_i}: back-translating {source_id}...", flush=True)
            translations.append(back_translate(source["answer_text"], translate_fn=translate_fn))

    augmented = []
    skipped = []
    for source_id, translated in zip(train_ids, translations):
        if translated is None:
            skipped.append(source_id)
            continue
        source = samples_by_id[source_id]
        augmented.append(
            {
                "id": f"{source_id}__bt",
                "source_id": source_id,
                "question_id": source["question_id"],
                "question_type": source["question_type"],
                "answer_text": translated,
                "answer_length": len(translated),
                "band_label": source["band_label"],
                "band_range": source["band_range"],
                "augmented": True,
                "augmentation_method": "back_translation_zh_en_zh",
            }
        )

    if skipped:
        print(f"fold {fold_i}: back-translation failed for {len(skipped)}/{len(train_ids)} "
              f"train samples, skipped: {skipped}")

    return augmented


def check_no_leakage(
    augmented_samples: list[dict],
    fold_i: int,
    samples_by_id: dict[str, dict] | None = None,
    fold: dict | None = None,
    test_ids: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Verify augmented_samples only derive from fold_{fold_i}'s train_ids, and
    that no augmented answer_text exactly duplicates a val/test answer_text
    (which would otherwise let a near-identical example leak across the
    train/val or train/test boundary). `fold`/`test_ids` can be injected
    directly (for testing with fabricated splits instead of ml/splits/).
    """
    if samples_by_id is None:
        samples_by_id = common.load_prepared_samples()

    fold = fold or common.load_fold(fold_i)
    train_ids = set(fold["train_ids"])
    val_ids = set(fold["val_ids"])
    test_ids = set(test_ids if test_ids is not None else common.load_test()["test_ids"])

    issues = []

    source_ids = {s["source_id"] for s in augmented_samples}
    not_from_train = source_ids - train_ids
    if not_from_train:
        issues.append(f"{len(not_from_train)} augmented sample(s) have source_id outside "
                       f"fold {fold_i}'s train_ids: {sorted(not_from_train)}")

    overlap_with_eval = source_ids & (val_ids | test_ids)
    if overlap_with_eval:
        issues.append(f"{len(overlap_with_eval)} augmented sample(s) derive from ids that are "
                       f"in val/test: {sorted(overlap_with_eval)}")

    eval_texts = {samples_by_id[i]["answer_text"] for i in (val_ids | test_ids)}
    exact_dupes = [s["id"] for s in augmented_samples if s["answer_text"] in eval_texts]
    if exact_dupes:
        issues.append(f"{len(exact_dupes)} augmented sample(s) exactly duplicate a val/test "
                       f"answer_text (back-translation round-tripped to identical text): {exact_dupes}")

    return (len(issues) == 0, issues)


def compare_metrics(before: dict, after: dict, keys: tuple[str, ...] = ("macro_f1", "qwk", "within1_accuracy")) -> str:
    """Small before/after diff table for two ml.metrics.compute_metrics() outputs."""
    lines = [f"{'metric':<16}{'before':>10}{'after':>10}{'delta':>10}"]
    for key in keys:
        b, a = before[key], after[key]
        lines.append(f"{key:<16}{b:>10.3f}{a:>10.3f}{a - b:>+10.3f}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold", type=int, default=None,
                         help="Augment only this fold (0-4). Default: all 5 folds.")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE_JSON", "AFTER_JSON"),
                         help="Skip augmentation; just print a before/after metrics diff "
                              "from two ml.metrics.compute_metrics()-shaped JSON files.")
    parser.add_argument("--force", action="store_true",
                         help="Re-run and overwrite a fold even if its augmented file already "
                              "exists (default: skip folds already done — each item is 2 "
                              "local-model translation passes, re-running a finished fold for "
                              "nothing just burns several minutes of GPU/CPU time).")
    args = parser.parse_args()

    if args.compare:
        before = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
        after = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        print(compare_metrics(before, after))
        return

    samples_by_id = common.load_prepared_samples()
    fold_range = [args.fold] if args.fold is not None else range(common.K_FOLDS)

    AUGMENTED_DIR.mkdir(parents=True, exist_ok=True)
    for fold_i in fold_range:
        out_path = AUGMENTED_DIR / f"fold_{fold_i}_train_augmented.json"
        skip_report_path = AUGMENTED_DIR / f"fold_{fold_i}_train_augmented.skip_report.json"
        if out_path.exists() and not args.force:
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = None
            if isinstance(existing, list) and existing:
                print(f"fold {fold_i}: {out_path.relative_to(ROOT)} already exists "
                      f"({len(existing)} samples) — skipping (pass --force to redo).")
                if skip_report_path.exists():
                    try:
                        prior_report = json.loads(skip_report_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        prior_report = None
                    if isinstance(prior_report, dict) and prior_report.get("skipped_count"):
                        print(f"  WARNING: this existing file was produced with "
                              f"{prior_report['skipped_count']} skipped sample(s) "
                              f"(see {skip_report_path.relative_to(ROOT)}) — training data for "
                              f"this fold is short {prior_report['skipped_count']} augmented "
                              f"sample(s). Re-run with --force once the cause (e.g. a local "
                              f"model OOM) is resolved.")
                continue
            print(f"fold {fold_i}: existing {out_path.relative_to(ROOT)} is missing/empty/corrupt, re-running.")

        fold = common.load_fold(fold_i)
        train_ids = fold["train_ids"]
        augmented = augment_fold(fold_i, samples_by_id=samples_by_id, fold=fold)
        ok, issues = check_no_leakage(augmented, fold_i, samples_by_id=samples_by_id, fold=fold)
        if not ok:
            raise SystemExit(f"fold {fold_i}: leakage check FAILED:\n" + "\n".join(f"  - {i}" for i in issues))

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(augmented, f, ensure_ascii=False, indent=2)

        # Persist the skip outcome to disk, not just stdout: a Colab cell's
        # printed "skipped: [...]" line scrolls away or is lost with the
        # runtime, which is exactly how failed samples end up silently
        # missing from the training set instead of being visibly flagged.
        succeeded_source_ids = {s["source_id"] for s in augmented}
        skipped_ids = [tid for tid in train_ids if tid not in succeeded_source_ids]
        skip_report = {
            "fold": fold_i,
            "train_ids_total": len(train_ids),
            "succeeded_count": len(augmented),
            "skipped_count": len(skipped_ids),
            "skipped_ids": skipped_ids,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with skip_report_path.open("w", encoding="utf-8") as f:
            json.dump(skip_report, f, ensure_ascii=False, indent=2)

        if skipped_ids:
            print(f"fold {fold_i}: WARNING — {len(skipped_ids)}/{len(train_ids)} train sample(s) "
                  f"FAILED translation and are MISSING from the augmented set (see "
                  f"{skip_report_path.relative_to(ROOT)} for the id list). This is not a full "
                  f"success — re-run with --force after fixing the underlying failure (e.g. a "
                  f"local model OOM) to recover them.")
        print(f"fold {fold_i}: wrote {len(augmented)}/{len(train_ids)} augmented samples to "
              f"{out_path.relative_to(ROOT)} (leakage check passed)")


if __name__ == "__main__":
    main()
