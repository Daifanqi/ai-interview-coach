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


# ---------------------------------------------------------------------------
# question_id -> Question lookup (decision #39/week 13)
#
# backend/report/generator.py needs to score a finished interview's main-
# topic answers, which means turning QAItem.question_source_id (decision
# #39/week 12) back into the Question that was actually asked -- for its
# keyword_clusters/reference_points/question_type, which
# backend/scoring/baseline.py's score_answer_report() requires. This lives
# here rather than in backend/rag/retriever.py -- which already builds an
# equivalent id -> Question dict internally for its own hydration step --
# so that report generation doesn't have to import chromadb (retriever.py's
# module-level dependency, via backend/rag/vector_store.py) just to look up
# a question by id; this lookup only ever touches the plain JSON file.
#
# DEFAULT_QUESTION_BANK_PATH is intentionally duplicated from
# backend/rag/vector_store.py's constant of the same name/value rather than
# imported from there, for the same import-weight reason.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTION_BANK_PATH = _PROJECT_ROOT / "data" / "question_bank.json"

_question_index_cache: dict[str, dict[str, Question]] = {}


def _get_question_index(path: str | Path) -> dict[str, Question]:
    """Lazily load and cache a question_id -> Question index for `path`, keyed by the resolved path
    string so distinct question-bank files (e.g. question_bank.json vs. sample_questions.json) never
    collide in the cache."""
    key = str(Path(path).resolve())
    if key not in _question_index_cache:
        _question_index_cache[key] = {q.question_id: q for q in load_questions_from_json(path)}
    return _question_index_cache[key]


def get_question_by_id(question_id: str, path: str | Path = DEFAULT_QUESTION_BANK_PATH) -> Optional[Question]:
    """
    Look up one Question by id, or None if `question_id` isn't in `path`
    (e.g. it came from a different question bank than the one passed here,
    or the id is stale/malformed) -- callers must treat this as "can't
    score this turn" rather than an error, since a live interview session
    is not proof the question bank hasn't changed since it was recorded.
    """
    return _get_question_index(path).get(question_id)
