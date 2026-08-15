"""Push the final structure_completeness classifier to the Hugging Face Hub.

Run this as a Colab cell (or `python ml/push_to_hub.py` in the Colab runtime
shell) AFTER `ml/train.py --final` has produced
`ml/results/train/distilbert-base-multilingual-cased/final_model/model/`
(config.json / pytorch_model.bin or model.safetensors / tokenizer files) —
this script never trains anything, it only packages and uploads an existing
checkpoint. It's meant to run on the same Colab VM that holds the checkpoint,
not locally, so the ~250MB of model weights never has to round-trip through
your laptop.

Auth: this script does NOT contain a token. Provide one of:
  - a Colab secret named HF_TOKEN (Colab left sidebar -> key icon -> add
    secret -> toggle "Notebook access" on), or
  - just run it and answer the interactive `notebook_login()` / `login()`
    prompt with a token you paste in (get one with "write" scope from
    https://huggingface.co/settings/tokens).
Never hardcode a token in this file or commit one anywhere in the repo.

Before running, edit the two variables in the CONFIG block below:
  - HF_REPO_ID: "<your-hf-username>/<repo-name>", e.g.
    "yourname/structure-completeness-distilbert-zh"
  - MODEL_DIR: local path to the trained checkpoint on the Colab VM
    (default matches what ml/train.py --final writes).
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG — edit these two before running
# ---------------------------------------------------------------------------
HF_REPO_ID = "a1a1a1aaa/structure-completeness-distilbert-zh"  # <-- EDIT
MODEL_DIR = Path("ml/results/train/distilbert-base-multilingual-cased/final_model/model")  # <-- EDIT if different

# ---------------------------------------------------------------------------
# Fixed facts about this run — copied from docs/week7_finetuning_results.md
# and docs/decision_log.md decisions #33/#34. If you retrain and these
# numbers change, update them here before pushing (don't let the model card
# drift from the real numbers).
# ---------------------------------------------------------------------------
BAND_LABELS = ["0-2", "3-4", "5-6", "7-8", "9-10"]

FINAL_TEST_METRICS = {
    "n": 22,
    "exact_accuracy": 0.773,
    "macro_f1": 0.769,
    "qwk": 0.936,
    "within1_accuracy": 1.000,
}

CV_VAL_MEAN_METRICS = {
    "n_folds": 5,
    "cv_pool_n": 128,
    "macro_f1": 0.885,
    "qwk": 0.950,
}

LICENSE_NAME = "polyform-noncommercial-1.0.0"
LICENSE_LINK = "https://polyformproject.org/licenses/noncommercial/1.0.0/"

MODEL_CARD = f"""---
license: other
license_name: {LICENSE_NAME}
license_link: {LICENSE_LINK}
language:
- zh
base_model: distilbert-base-multilingual-cased
pipeline_tag: text-classification
tags:
- interview
- scoring
- structure-completeness
- chinese
---

# structure-completeness-distilbert-zh

**License: [PolyForm Noncommercial 1.0.0]({LICENSE_LINK})** — personal
learning / research / education / non-profit use only, **no commercial use**.
This is a "source-available" model, not an OSI-approved open-source license
(the restriction on commercial use is the reason). See the license link for
the full text before using this model in any product or paid service.

## What this model does

5-class classifier that scores the **structural completeness** of a Chinese
interview answer (does it follow a clear situation/action/result-style
structure vs. being disorganized rambling), as one dimension of an AI mock
interview coaching app's answer-scoring pipeline. It is **not** a general
Chinese text classifier and was not trained for any other task.

Output is one of 5 ordinal bands, each corresponding to a 0-10 structural
completeness score range:

| label id | band | meaning |
| --- | --- | --- |
| 0 | 0-2 | little to no structure |
| 1 | 3-4 | minimal structure |
| 2 | 5-6 | partial structure |
| 3 | 7-8 | mostly complete structure |
| 4 | 9-10 | fully complete, clearly organized structure |

## Training data

- 150 Chinese interview answers, each with a `structure_completeness` score
  (0-10) from a **single** human reviewer (no second independent rater —
  see "Known limitations" below).
- Answers span 3 question types (behavioral / technical / case analysis),
  50 each, balanced.
- Split: 5-fold stratified cross-validation over a 128-sample pool
  (stratified jointly on question type x score band), plus a held-out test
  set of 22 samples (14.7%) that never participated in any training,
  validation, or early-stopping decision.
- The final checkpoint published here was trained on all 128 CV-pool
  samples combined (no validation split left for early stopping), for a
  fixed 14 epochs (no back-translation data augmentation — augmentation was
  tried and did not help this model, see below).

## Final metrics

Held-out test set (n=22, one single `predict()` call, never touched during
training):

| metric | value |
| --- | --- |
| exact_accuracy | {FINAL_TEST_METRICS['exact_accuracy']:.3f} |
| macro_f1 | {FINAL_TEST_METRICS['macro_f1']:.3f} |
| qwk (quadratic-weighted kappa) | {FINAL_TEST_METRICS['qwk']:.3f} |
| within1_accuracy (+/-1 band) | {FINAL_TEST_METRICS['within1_accuracy']:.3f} |

For reference, the 5-fold cross-validation mean on the 128-sample CV pool
(different data split, not directly comparable 1:1 to the 22-sample test
set above) was macro_f1={CV_VAL_MEAN_METRICS['macro_f1']:.3f},
qwk={CV_VAL_MEAN_METRICS['qwk']:.3f}. The test-set macro_f1/exact_accuracy
are noticeably lower than the CV mean, which is expected given n=22 is a
small, high-variance sample; qwk and within1_accuracy stay close to the CV
mean, and every miss on the test set was an adjacent-band miss (no error
was off by 2+ bands).

## Known limitations

- **Test set is small (n=22).** Point-estimate metrics on 22 samples have
  wide, unreported confidence intervals — don't treat these numbers as
  precise beyond +/-1 band roughly.
- **Chinese only.** All 150 training/eval samples are Chinese-language
  interview answers; there is no evaluation on English or code-switched
  input, and it will likely not behave sensibly on non-Chinese text.
- **Single annotator.** Every label came from one human reviewer with no
  second independent rater, so no inter-annotator agreement metric (e.g.
  Cohen's kappa) exists for the labels themselves — some fraction of any
  model "error" against these labels may be label noise, not model error.
- **Back-translation augmentation did not help this model.** A back-
  translation augmented variant (same architecture) scored *slightly worse*
  on every metric (macro_f1 0.885->0.878, qwk 0.950->0.942, exact_accuracy
  0.883->0.876, within1_accuracy 0.985->0.977, all 5-fold CV means) than
  the plain (non-augmented) version this checkpoint is. The published model
  is the non-augmented one.
- **Small overall dataset (150 labeled examples total).** This is a
  small-data fine-tune, not a model trained on a large labeled corpus —
  expect it to be sensitive to answer styles/topics that differ a lot from
  the training distribution (3 question types: behavioral, technical, case
  analysis).
- **One dimension of a multi-dimension rubric.** Structural completeness is
  one of several scoring dimensions (alongside keyword coverage, logical
  coherence, specificity) in the source project's full scoring rubric —
  this model only covers structure, not overall answer quality.

## Usage

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model_id = "{HF_REPO_ID}"
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSequenceClassification.from_pretrained(model_id)
model.eval()

answer = "首先我发现了这个问题，然后评估了几个方案，最后选择了风险最低的一个并推动落地。"
inputs = tokenizer(answer, return_tensors="pt", truncation=True, max_length=512)
with torch.no_grad():
    logits = model(**inputs).logits
band_id = int(torch.argmax(logits, dim=-1))

band_labels = {BAND_LABELS!r}
print(f"predicted band: {{band_labels[band_id]}}")
```

Or with `pipeline`:

```python
from transformers import pipeline

clf = pipeline("text-classification", model="{HF_REPO_ID}")
print(clf("首先我发现了这个问题，然后评估了几个方案，最后选择了风险最低的一个并推动落地。"))
```

## Source project

Trained as part of a 10-week solo AI mock interview coaching app project.
Full training/eval code, data prep, cross-validation splits, and the
decision log documenting model selection reasoning are in the project repo:
https://github.com/Daifanqi/ai-interview-coach (`ml/train.py`,
`ml/common.py`, `docs/week7_finetuning_results.md`, `docs/decision_log.md`
decisions #33-#34).
"""


def main() -> None:
    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"{MODEL_DIR} not found. Run `python ml/train.py --model "
            f"distilbert-base-multilingual-cased --final` first, or edit "
            f"MODEL_DIR at the top of this script to point at your actual "
            f"checkpoint directory."
        )
    if "your-username" in HF_REPO_ID:
        raise ValueError("Edit HF_REPO_ID at the top of this script before running.")

    from huggingface_hub import HfApi, create_repo, login

    token = os.environ.get("HF_TOKEN")
    if token:
        login(token=token)
    else:
        # Interactive prompt — paste a token with "write" scope from
        # https://huggingface.co/settings/tokens. Nothing is written to disk
        # by this script; huggingface_hub caches it under ~/.cache/huggingface
        # on whatever machine you run this on (the Colab VM, in this case).
        login()

    create_repo(repo_id=HF_REPO_ID, repo_type="model", private=False, exist_ok=True)

    (MODEL_DIR / "README.md").write_text(MODEL_CARD, encoding="utf-8")

    api = HfApi()
    api.upload_folder(
        folder_path=str(MODEL_DIR),
        repo_id=HF_REPO_ID,
        repo_type="model",
        commit_message="Upload structure_completeness distilbert checkpoint + model card",
    )

    print(f"Done. Repo: https://huggingface.co/{HF_REPO_ID}")


if __name__ == "__main__":
    main()
