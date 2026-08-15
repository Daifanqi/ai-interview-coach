"""Interactive CLI tool for human review of the candidate-answer labels.

Walks through the candidate-answer drafts one answer at a time, showing the
question, the full answer text, and (when available) the simplified
calibration checklist from docs/scoring_calibration_checklist.md (keyword
hit list + structure element list) so the reviewer does not have to count
anything by hand.

Two draft batches are loaded and reviewed as one combined queue:
  - batch 1: data/labeled_answers_draft.json (150 items, questions sourced
    from data/sample_questions.json). This batch is already fully reviewed;
    its scored records in labeled_answers_human_reviewed.json are left
    untouched and simply skipped on every run.
  - batch 2: data/labeled_answers_draft_batch2.json (300 items, questions
    sourced from data/question_bank.json). Its questions are not covered by
    the calibration checklist doc (that doc only covers the original 30
    sample questions), so the reviewer will see a "no calibration checklist
    found" notice for these items — the question text, AI-suggested scores,
    and reference_points are still shown to score against.

Because (question_id, score_band) is unique within each batch and the two
batches use disjoint question_id prefixes, both batches share a single
review_id namespace and a single output file without collisions.

The reviewer types four scores (0-10) per answer, or presses Enter on the
first score to skip the item (it is saved with status "pending" and can be
revisited on a later run). Progress is written to
data/labeled_answers_human_reviewed.json after every single item, so the
tool can be interrupted (Ctrl+C, "q", or SIGTERM) and resumed later without
losing work or re-reviewing already-scored items.

Usage:
    python scripts/review_labels.py            # resume / start review
    python scripts/review_labels.py --reset    # discard existing progress
    python scripts/review_labels.py --edit 42            # jump to serial number 42 (as shown in [N/total])
    python scripts/review_labels.py --edit beh_003       # jump to a question_id (prompts if it has multiple score bands)
    python scripts/review_labels.py --edit beh_003:6-7   # jump to a specific question_id + score_band
--edit re-shows that single item, lets you enter new scores, and overwrites
any previously saved record for it (whether it was "scored" or "pending").
Pressing Enter on the first score cancels the edit and leaves the existing
record untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRAFT_PATH = PROJECT_ROOT / "data" / "labeled_answers_draft.json"
DRAFT_BATCH2_PATH = PROJECT_ROOT / "data" / "labeled_answers_draft_batch2.json"
QUESTIONS_PATH = PROJECT_ROOT / "data" / "sample_questions.json"
QUESTION_BANK_PATH = PROJECT_ROOT / "data" / "question_bank.json"
CHECKLIST_PATH = PROJECT_ROOT / "docs" / "scoring_calibration_checklist.md"
OUTPUT_PATH = PROJECT_ROOT / "data" / "labeled_answers_human_reviewed.json"

# (draft file path, human-readable batch label) — reviewed as one combined
# queue, see module docstring for why this is safe (disjoint question_id
# prefixes between batches).
DRAFT_BATCHES = [
    (DRAFT_PATH, "batch1"),
    (DRAFT_BATCH2_PATH, "batch2"),
]

# (field name in the saved record, human-readable prompt label)
DIMENSIONS = [
    ("structure_completeness", "Structure completeness / 结构完整度"),
    ("keyword_coverage", "Keyword coverage / 关键词覆盖率"),
    ("logical_coherence", "Logical coherence / 逻辑连贯性"),
    ("specificity", "Specificity / 具体性"),
]

QUESTION_TYPE_LABELS = {
    "behavioral": "Behavioral / 行为题",
    "technical": "Technical / 技术题",
    "case_analysis": "Case analysis / 案例分析题",
}

# Sentinels returned by the score prompt in place of a float score.
QUIT = object()
SKIP_ITEM = object()


def load_json(path: Path) -> list:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def make_review_id(question_id: str, score_band: str) -> str:
    # (question_id, score_band) is unique across the 150 draft entries, so it
    # makes a stable identity that survives re-ordering of the draft file.
    return f"{question_id}__{score_band}"


def parse_checklist(path: Path) -> dict:
    """Parse the per-question calibration checklist markdown file.

    Returns {question_id: {"keywords": [...], "structure_elements": [...]}}.
    """
    text = path.read_text(encoding="utf-8")

    section_starts = list(re.finditer(r"^## (\S+) \(", text, flags=re.MULTILINE))
    checklist = {}
    checkbox_re = re.compile(r"^- \[ \] (.+)$", flags=re.MULTILINE)

    for i, match in enumerate(section_starts):
        question_id = match.group(1)
        block_start = match.end()
        block_end = section_starts[i + 1].start() if i + 1 < len(section_starts) else len(text)
        block = text[block_start:block_end]

        keyword_start = block.find("### Keyword hit count")
        structure_start = block.find("### Structure element checklist")
        reference_start = block.find("### Reference points")

        keyword_block = block[keyword_start:structure_start] if keyword_start != -1 else ""
        structure_block = (
            block[structure_start:reference_start] if structure_start != -1 else ""
        )

        checklist[question_id] = {
            "keywords": checkbox_re.findall(keyword_block),
            "structure_elements": checkbox_re.findall(structure_block),
        }

    return checklist


def load_draft_batches() -> list:
    """Load every draft batch in DRAFT_BATCHES and concatenate them into one
    list, tagging each entry with its source batch label (an in-memory-only
    "_batch" key — build_record() below only copies named fields out of the
    draft entry, so this tag never ends up in the saved review records).

    A missing batch file is skipped with a warning rather than raising, so
    the tool still works before batch 2 has been generated.
    """
    draft_list = []
    for path, label in DRAFT_BATCHES:
        if not path.exists():
            print(f"Note: {path.relative_to(PROJECT_ROOT)} not found, skipping {label}.")
            continue
        for entry in load_json(path):
            entry["_batch"] = label
            draft_list.append(entry)
    return draft_list


def load_existing_reviews(path: Path) -> dict:
    if not path.exists():
        return {}
    records = load_json(path)
    return {record["review_id"]: record for record in records}


def atomic_write_json(path: Path, data: list) -> None:
    # Write to a temp file in the same directory and rename, so a crash or
    # Ctrl+C mid-write never leaves labeled_answers_human_reviewed.json
    # truncated or invalid.
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def save_reviews(path: Path, review_map: dict) -> None:
    atomic_write_json(path, list(review_map.values()))


def print_divider() -> None:
    print("-" * 78)


def print_item(
    position: int,
    total: int,
    draft_entry: dict,
    question: Optional[dict],
    checklist_entry: Optional[dict],
) -> None:
    print_divider()
    print(f"[{position}/{total}] question_id={draft_entry['question_id']}  "
          f"score_band(AI)={draft_entry['score_band']}")
    print_divider()

    if question is None:
        print("WARNING: no matching entry found in sample_questions.json.")
    else:
        job_type = question.get("job_type", "N/A (not defined in sample_questions.json)")
        print(f"Question: {question['question_text']}")
        print(f"Type: {QUESTION_TYPE_LABELS.get(question['question_type'], question['question_type'])}")
        print(f"Job type: {job_type}")

    print()
    print("Candidate answer:")
    print(draft_entry["answer_text"])

    ai_scores = draft_entry.get("ai_suggested_scores", {})
    if ai_scores:
        print()
        print("AI-suggested scores (for reference only, judge independently):")
        for field, label in DIMENSIONS:
            print(f"  {label}: {ai_scores.get(field, 'N/A')}")

    if checklist_entry is not None:
        print()
        n_kw = len(checklist_entry["keywords"])
        print(f"Keyword checklist ({n_kw} clusters, canonical / synonyms — "
              f"check off any that appear in the answer):")
        for kw in checklist_entry["keywords"]:
            print(f"  [ ] {kw}")

        n_struct = len(checklist_entry["structure_elements"])
        print()
        print(f"Structure element checklist ({n_struct} elements):")
        for element in checklist_entry["structure_elements"]:
            print(f"  [ ] {element}")
    else:
        print()
        print("WARNING: no calibration checklist found for this question_id.")

    if question is not None and question.get("reference_points"):
        print()
        print("Reference points:")
        for point in question["reference_points"]:
            print(f"  - {point}")

    print()


def prompt_score(label: str, is_first: bool):
    hint = ", Enter=skip this item, q=quit" if is_first else ", q=quit"
    while True:
        raw = input(f"{label} [0-10{hint}]: ").strip()
        if raw.lower() in ("q", "quit"):
            return QUIT
        if raw == "":
            if is_first:
                return SKIP_ITEM
            print("A value is required once you've started scoring this item "
                  "(skip-the-whole-item only works on the first score).")
            continue
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number between 0 and 10.")
            continue
        if not (0 <= value <= 10):
            print("Score must be between 0 and 10.")
            continue
        return value


def review_one_item(draft_entry: dict) -> Optional[dict]:
    """Prompt the reviewer for one item. Returns the score dict, SKIP_ITEM,
    or QUIT."""
    scores = {}
    for i, (field, label) in enumerate(DIMENSIONS):
        result = prompt_score(label, is_first=(i == 0))
        if result is QUIT:
            return QUIT
        if result is SKIP_ITEM:
            return SKIP_ITEM
        scores[field] = result
    return scores


def build_record(draft_entry: dict, review_id: str, status: str, human_scores: dict) -> dict:
    return {
        "review_id": review_id,
        "question_id": draft_entry["question_id"],
        "score_band": draft_entry["score_band"],
        "answer_text": draft_entry["answer_text"],
        "ai_suggested_scores": draft_entry.get("ai_suggested_scores", {}),
        "human_scores": human_scores,
        "status": status,
        "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def print_summary(draft_list: list, review_map: dict, questions_by_id: dict) -> None:
    total = len(draft_list)
    scored = sum(1 for e in draft_list
                 if review_map.get(make_review_id(e["question_id"], e["score_band"]), {}).get("status") == "scored")
    pending = sum(1 for e in draft_list
                  if review_map.get(make_review_id(e["question_id"], e["score_band"]), {}).get("status") == "pending")
    not_touched = total - scored - pending

    print()
    print("=" * 78)
    print("Review progress summary")
    print("=" * 78)
    print(f"Scored: {scored}/{total}   Pending: {pending}   Not yet touched: {not_touched}")

    # Distribution by question type.
    type_totals = Counter()
    type_scored = Counter()
    for entry in draft_list:
        qtype = questions_by_id.get(entry["question_id"], {}).get("question_type", "unknown")
        type_totals[qtype] += 1
        review_id = make_review_id(entry["question_id"], entry["score_band"])
        if review_map.get(review_id, {}).get("status") == "scored":
            type_scored[qtype] += 1

    print()
    print("By question type:")
    for qtype in sorted(type_totals):
        label = QUESTION_TYPE_LABELS.get(qtype, qtype)
        print(f"  {label}: {type_scored[qtype]}/{type_totals[qtype]} scored")

    # Distribution by AI-suggested score band.
    band_totals = Counter()
    band_scored = Counter()
    for entry in draft_list:
        band_totals[entry["score_band"]] += 1
        review_id = make_review_id(entry["question_id"], entry["score_band"])
        if review_map.get(review_id, {}).get("status") == "scored":
            band_scored[entry["score_band"]] += 1

    print()
    print("By score band (AI-suggested):")
    for band in sorted(band_totals, key=lambda b: [int(x) for x in b.split("-")]):
        print(f"  {band}: {band_scored[band]}/{band_totals[band]} scored")

    # Distribution by source batch.
    batch_totals = Counter()
    batch_scored = Counter()
    for entry in draft_list:
        batch = entry.get("_batch", "unknown")
        batch_totals[batch] += 1
        review_id = make_review_id(entry["question_id"], entry["score_band"])
        if review_map.get(review_id, {}).get("status") == "scored":
            batch_scored[batch] += 1

    print()
    print("By batch:")
    for batch in sorted(batch_totals):
        print(f"  {batch}: {batch_scored[batch]}/{batch_totals[batch]} scored")

    print()
    print(f"Progress saved to {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


def resolve_edit_target(value: str, draft_list: list) -> Optional[int]:
    """Resolve an --edit argument to an index into draft_list, or None if it
    could not be resolved (an error/cancellation message is already printed)."""
    if value.isdigit():
        idx = int(value)
        if 1 <= idx <= len(draft_list):
            return idx - 1
        print(f"Error: serial number {idx} is out of range (1-{len(draft_list)}).")
        return None

    qid, _, band = value.partition(":")
    matches = [
        i for i, e in enumerate(draft_list)
        if e["question_id"] == qid and (not band or e["score_band"] == band)
    ]
    if not matches:
        where = f"question_id={qid!r}" + (f", score_band={band!r}" if band else "")
        print(f"Error: no draft entry found for {where}.")
        return None
    if len(matches) == 1:
        return matches[0]

    print(f"Multiple entries found for question_id={qid!r}:")
    for i in matches:
        print(f"  [{i + 1}] score_band={draft_list[i]['score_band']}")
    while True:
        raw = input("Enter the serial number to edit (or 'q' to cancel): ").strip()
        if raw.lower() in ("q", "quit"):
            return None
        if raw.isdigit() and (int(raw) - 1) in matches:
            return int(raw) - 1
        print("Invalid selection.")


def run_edit(
    value: str,
    draft_list: list,
    review_map: dict,
    questions_by_id: dict,
    checklist_by_id: dict,
) -> None:
    idx = resolve_edit_target(value, draft_list)
    if idx is None:
        return

    draft_entry = draft_list[idx]
    review_id = make_review_id(draft_entry["question_id"], draft_entry["score_band"])
    existing = review_map.get(review_id)

    question = questions_by_id.get(draft_entry["question_id"])
    checklist_entry = checklist_by_id.get(draft_entry["question_id"])
    print_item(idx + 1, len(draft_list), draft_entry, question, checklist_entry)

    if existing is not None:
        print("Existing saved record:")
        print(f"  status: {existing.get('status')}")
        if existing.get("status") == "scored":
            for field, label in DIMENSIONS:
                print(f"  {label}: {existing.get('human_scores', {}).get(field, 'N/A')}")
        print(f"  reviewed_at: {existing.get('reviewed_at')}")
    else:
        print("No existing saved record for this item yet.")
    print()
    print("Re-scoring this item. Enter on the first score cancels the edit "
          "(existing record unchanged).")

    result = review_one_item(draft_entry)

    if result is QUIT:
        print("\nQuitting without saving the edit.")
        return
    if result is SKIP_ITEM:
        print("Edit cancelled, existing record unchanged.")
        return

    review_map[review_id] = build_record(draft_entry, review_id, "scored", result)
    save_reviews(OUTPUT_PATH, review_map)
    print("Overwritten and saved.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Human review tool for candidate-answer labels.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", action="store_true",
                        help="Discard existing progress in labeled_answers_human_reviewed.json and start over.")
    group.add_argument("--edit", metavar="QUESTION_ID_OR_INDEX",
                        help="Jump to one existing record to re-score and overwrite it. Accepts a "
                             "1-based serial number (the [N/total] shown during review), a question_id, "
                             "or 'question_id:score_band' if that question_id has multiple bands.")
    args = parser.parse_args()

    draft_list = load_draft_batches()
    # Merge question metadata from both sources; sample_questions.json (the
    # original 30) takes priority in the unlikely event of an id collision.
    questions_by_id = {q["question_id"]: q for q in load_json(QUESTION_BANK_PATH)}
    questions_by_id.update({q["question_id"]: q for q in load_json(QUESTIONS_PATH)})
    checklist_by_id = parse_checklist(CHECKLIST_PATH)

    if args.reset or not OUTPUT_PATH.exists():
        review_map = {}
    else:
        review_map = load_existing_reviews(OUTPUT_PATH)

    if args.edit is not None:
        run_edit(args.edit, draft_list, review_map, questions_by_id, checklist_by_id)
        print_summary(draft_list, review_map, questions_by_id)
        return

    total = len(draft_list)
    batch_counts = Counter(entry.get("_batch", "unknown") for entry in draft_list)
    batch_summary = ", ".join(f"{count} {label}" for label, count in sorted(batch_counts.items()))
    print(f"Loaded {total} candidate answers ({batch_summary}). "
          f"{sum(1 for r in review_map.values() if r.get('status') == 'scored')} already scored, "
          f"{sum(1 for r in review_map.values() if r.get('status') == 'pending')} pending from a previous run.")
    print("Commands: Enter on the first score = skip this item (marked pending). "
          "'q' at any prompt = save progress and quit.")

    quit_requested = False
    for position, draft_entry in enumerate(draft_list, start=1):
        review_id = make_review_id(draft_entry["question_id"], draft_entry["score_band"])
        existing = review_map.get(review_id)
        if existing is not None and existing.get("status") == "scored":
            continue  # already fully reviewed, nothing to do

        question = questions_by_id.get(draft_entry["question_id"])
        checklist_entry = checklist_by_id.get(draft_entry["question_id"])
        print_item(position, total, draft_entry, question, checklist_entry)

        result = review_one_item(draft_entry)

        if result is QUIT:
            quit_requested = True
            break
        if result is SKIP_ITEM:
            review_map[review_id] = build_record(draft_entry, review_id, "pending", {})
            save_reviews(OUTPUT_PATH, review_map)
            print("Marked as pending, moving on.")
            continue

        review_map[review_id] = build_record(draft_entry, review_id, "scored", result)
        save_reviews(OUTPUT_PATH, review_map)
        print("Saved.")

    if quit_requested:
        print("\nQuitting, progress has been saved.")

    print_summary(draft_list, review_map, questions_by_id)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted, progress up to the last completed item has been saved.")
        sys.exit(0)
