"""
retrieve_questions() is the read path over the Chroma index built by
backend/rag/vector_store.py: given a job_type (required) and an optional
question_type filter, it returns the k most relevant Question objects.

"Most relevant" is computed via a real vector-similarity query rather than
a plain metadata filter in arbitrary order: job_type/question_type are
turned into a short synthetic descriptive query (e.g. "技术岗位的技术题面试题目"),
embedded with the same shared model as the index, and matched against the
Chroma collection restricted to that job_type (and question_type, if given)
via a metadata `where` filter. This keeps "vector retrieval" meaningful
even though the function signature itself takes no free-text query --
see docs/decision_log.md decisions 24-25 for why the question bank is
organized by (job_type, question_type) in the first place.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.rag.vector_store import DEFAULT_PERSIST_DIR, DEFAULT_QUESTION_BANK_PATH, get_or_build_collection
from backend.scoring.embedding import embed_texts
from models.question_schema import Question, QuestionType, load_questions_from_json

_QUESTION_TYPE_LABEL_ZH: dict[QuestionType, str] = {
    "behavioral": "行为题",
    "technical": "技术题",
    "case_analysis": "案例分析题",
}


def _build_query_text(job_type: str, question_type: Optional[QuestionType]) -> str:
    """Synthesize the descriptive query text embedded to rank candidates within the filtered subset."""
    type_label = _QUESTION_TYPE_LABEL_ZH.get(question_type, "") if question_type else ""
    return f"{job_type}岗位的{type_label}面试题目" if type_label else f"{job_type}岗位的面试题目"


class QuestionRetriever:
    """
    Wraps the Chroma collection plus a question_id -> Question lookup, so
    retrieve() can hydrate raw Chroma query results back into full Question
    objects. Chroma's own metadata only carries the filterable
    job_type/question_type fields (see vector_store.py); keyword_clusters
    and reference_points come from re-loading data/question_bank.json once
    here, so the two never need to be kept in sync inside Chroma itself.
    """

    def __init__(
        self,
        question_bank_path: Path | str = DEFAULT_QUESTION_BANK_PATH,
        persist_dir: Path | str = DEFAULT_PERSIST_DIR,
    ) -> None:
        self._collection = get_or_build_collection(question_bank_path, persist_dir)
        self._questions_by_id: dict[str, Question] = {
            q.question_id: q for q in load_questions_from_json(question_bank_path)
        }

    def retrieve(self, job_type: str, question_type: Optional[QuestionType] = None, k: int = 5) -> list[Question]:
        if question_type is not None:
            where = {"$and": [{"job_type": job_type}, {"question_type": question_type}]}
        else:
            where = {"job_type": job_type}

        query_embedding = embed_texts([_build_query_text(job_type, question_type)])[0]
        result = self._collection.query(query_embeddings=[query_embedding.tolist()], n_results=k, where=where)

        ids = result["ids"][0] if result["ids"] else []
        return [self._questions_by_id[qid] for qid in ids if qid in self._questions_by_id]


_default_retriever: Optional[QuestionRetriever] = None


def _get_default_retriever() -> QuestionRetriever:
    """Lazily construct (and cache) the module-level default retriever, mirroring the lazy-singleton
    pattern used for the embedding model / Groq clients elsewhere in backend/ (avoids paying the
    Chroma-load + question-bank-parse cost at import time for callers who never use retrieval)."""
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = QuestionRetriever()
    return _default_retriever


def retrieve_questions(job_type: str, question_type: Optional[QuestionType] = None, k: int = 5) -> list[Question]:
    """
    Retrieve the k most relevant questions for `job_type`, optionally
    filtered to a single `question_type`. See module docstring for how
    "most relevant" is computed against an index with no free-text query
    parameter of its own.
    """
    return _get_default_retriever().retrieve(job_type, question_type, k)


def warm_up_retriever() -> None:
    """
    Force-construct the default QuestionRetriever singleton once (decision
    #39/week 12) -- builds/loads the Chroma collection over all 200 bank
    questions immediately, mirroring backend/speech/tts.py's
    warm_up_voices(), so the first real retrieve_questions() call mid-
    interview (session_adapter._pick_next_question(), when a topic
    transition happens) never pays that cost inline. One call is enough
    for every job_type/question_type combination -- the collection covers
    the whole bank; job_type/question_type are query-time filters, not
    separate collections.
    """
    _get_default_retriever()
