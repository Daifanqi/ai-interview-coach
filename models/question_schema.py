"""
AI Interview System -- Core Data Structure Definitions: Question Bank

Shared schema for the two question-bank JSON files the project maintains:

- data/sample_questions.json: 30 questions used to calibrate the Week 5/6
  labeling and baseline-scoring work (see docs/decision_log.md decisions
  22-23). Entries have no job_type -- that set predates job-type
  segmentation and stays reserved for scoring calibration, not RAG
  retrieval (decision 24).
- data/question_bank.json: 200 job-type-segmented questions used for RAG
  retrieval (decision 24-25). Entries carry job_type.

Both backend/scoring (baseline.py) and backend/rag (vector_store.py,
retriever.py) load questions through load_questions_from_json() below, so
the two consumers never end up with two independent parsers for the same
JSON shape drifting out of sync.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

QuestionType = Literal["behavioral", "technical", "case_analysis"]


@dataclass
class KeywordCluster:
    """
    One synonym cluster in a question's keyword bank.

    docs/scoring_rubric.md section 3.2 explicitly calls for synonym-cluster
    matching rather than exact string matching against a single canonical
    term (e.g. "灰度发布" and "canary release" must count as the same hit) --
    that is what this cluster shape exists to represent.
    """

    canonical: str
    synonyms: list[str] = field(default_factory=list)

    def all_terms(self) -> list[str]:
        """The full set of surface forms that count as a hit for this cluster."""
        return [self.canonical, *self.synonyms]


@dataclass
class Question:
    """A single question-bank entry (behavioral / technical / case_analysis)."""

    question_id: str
    question_text: str
    question_type: QuestionType
    keyword_clusters: list[KeywordCluster]
    reference_points: list[str]
    # None for data/sample_questions.json (predates job-type segmentation,
    # see docs/decision_log.md decision 24).
    job_type: Optional[str] = None


def _parse_question(raw: dict) -> Question:
    clusters = [
        KeywordCluster(canonical=c["canonical"], synonyms=list(c["synonyms"]))
        for c in raw["keyword_clusters"]
    ]
    return Question(
        question_id=raw["question_id"],
        question_text=raw["question_text"],
        question_type=raw["question_type"],
        keyword_clusters=clusters,
        reference_points=list(raw["reference_points"]),
        job_type=raw.get("job_type"),
    )


def load_questions_from_json(path: str | Path) -> list[Question]:
    """Load either data/sample_questions.json or data/question_bank.json into Question objects."""
    with open(path, encoding="utf-8") as f:
        raw_list = json.load(f)
    return [_parse_question(raw) for raw in raw_list]
