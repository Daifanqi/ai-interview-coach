"""
Unit tests for session_adapter._pick_next_question() (decision #39/week 12)
-- the RAG-grounding helper that hands engine.py a candidate question for
each new interview topic. Uses the real retrieve_questions() (and
therefore the real Chroma index over data/question_bank.json), the same
way tests/test_rag_retrieval.py does; only the "retrieval fails" cases
below mock it out, since those are the one path that can't be exercised
against a healthy real index.
"""
from __future__ import annotations

from unittest.mock import patch

from backend.conversation import session_adapter


def test_pick_next_question_rotates_type_by_topic_number():
    # topic 1 -> behavioral, topic 2 -> technical, topic 3 -> case_analysis
    # (decision #39/week 12's MAX_TOPICS=3 "one of each" design).
    q1 = session_adapter._pick_next_question("技术", topic_number=1)
    q2 = session_adapter._pick_next_question("技术", topic_number=2)
    q3 = session_adapter._pick_next_question("技术", topic_number=3)
    assert q1 is not None and q1.question_type == "behavioral"
    assert q2 is not None and q2.question_type == "technical"
    assert q3 is not None and q3.question_type == "case_analysis"


def test_pick_next_question_rotation_wraps_past_max_topics():
    # topic 4 should behave like topic 1 again (modulo rotation), so the
    # helper still returns something sane if MAX_TOPICS is ever raised.
    q1 = session_adapter._pick_next_question("产品", topic_number=1)
    q4 = session_adapter._pick_next_question("产品", topic_number=4)
    assert q1 is not None and q4 is not None
    assert q1.question_type == q4.question_type == "behavioral"


def test_pick_next_question_returns_question_from_requested_job_type():
    q = session_adapter._pick_next_question("金融", topic_number=2)
    assert q is not None
    assert q.job_type == "金融"
    assert q.question_type == "technical"


def test_pick_next_question_varies_across_calls():
    # _CANDIDATE_POOL_SIZE=5 + random.choice() should surface more than one
    # distinct question across repeated calls for the same (job_type,
    # question_type) -- guards against silently regressing to "always the
    # #1 match" (every repeat interview for the same job_type asking the
    # identical 3 questions every time).
    picks = {session_adapter._pick_next_question("咨询", topic_number=1).question_id for _ in range(20)}
    assert len(picks) > 1, "expected some variety across 20 draws from a 5-candidate pool"


def test_pick_next_question_returns_none_on_retrieval_failure():
    # Never let a RAG failure surface as an exception -- callers
    # (start()/submit_round()) must fall back to free generation.
    with patch("backend.conversation.session_adapter.retrieve_questions", side_effect=RuntimeError("boom")):
        assert session_adapter._pick_next_question("技术", topic_number=1) is None


def test_pick_next_question_returns_none_when_bank_has_no_match():
    with patch("backend.conversation.session_adapter.retrieve_questions", return_value=[]):
        assert session_adapter._pick_next_question("技术", topic_number=1) is None
