"""
Functional sanity tests for backend/rag/retriever.py -- confirm
retrieve_questions() actually filters by job_type/question_type and
respects k against the real, built data/question_bank.json index (see
docs/decision_log.md decisions 24-25). No accuracy claims here, just "does
retrieval behave the way its contract says it should."
"""
from __future__ import annotations

from backend.rag.retriever import retrieve_questions

ALL_JOB_TYPES = ("技术", "产品", "市场营销", "运营", "设计", "咨询", "金融")


def test_retrieve_questions_respects_k():
    results = retrieve_questions("技术", k=5)
    assert len(results) == 5


def test_retrieve_questions_filters_by_job_type():
    results = retrieve_questions("金融", k=10)
    assert len(results) > 0
    for q in results:
        assert q.job_type == "金融"


def test_retrieve_questions_filters_by_question_type_when_given():
    results = retrieve_questions("技术", question_type="technical", k=10)
    assert len(results) > 0
    for q in results:
        assert q.job_type == "技术"
        assert q.question_type == "technical"


def test_retrieve_questions_no_type_filter_can_mix_question_types():
    """Without a question_type filter, results are ranked purely by relevance to job_type and
    may span more than one question_type -- this just confirms the filter is optional, not required."""
    results = retrieve_questions("产品", k=10)
    assert len(results) == 10
    assert all(q.job_type == "产品" for q in results)


def test_retrieve_questions_all_job_types_return_results():
    for job_type in ALL_JOB_TYPES:
        results = retrieve_questions(job_type, k=3)
        assert len(results) == 3, f"expected 3 results for job_type={job_type!r}"
        assert all(q.job_type == job_type for q in results)


def test_retrieve_questions_unknown_job_type_returns_empty():
    results = retrieve_questions("不存在的岗位", k=5)
    assert results == []


def test_retrieve_questions_k_larger_than_available_does_not_crash():
    # Each (job_type, question_type) combination has only 9-10 questions
    # (docs/decision_log.md decision 25); asking for more than exist should
    # just return everything that matches, not raise.
    results = retrieve_questions("技术", question_type="case_analysis", k=50)
    assert 0 < len(results) <= 10


def test_retrieved_questions_carry_full_schema():
    results = retrieve_questions("咨询", question_type="behavioral", k=1)
    assert len(results) == 1
    q = results[0]
    assert q.question_id.startswith("consulting_behavioral_")
    assert q.question_text
    assert len(q.keyword_clusters) > 0
    assert len(q.reference_points) > 0
