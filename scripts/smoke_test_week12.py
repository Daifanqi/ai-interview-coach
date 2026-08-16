"""
Real end-to-end smoke test for decision #39/week 12 (RAG question bank
wired into the conversation engine + interview_stage fix).

Exercises the actual pipeline a real interview goes through -- no mocks --
against the live Groq API and the real Chroma index over
data/question_bank.json:

  1. session_adapter.start() for a 技术/技术面① scenario, picking topic 1's
     question from the real RAG bank.
  2. Three full rounds of session_adapter.submit_round() with canned
     answers, walking through however many follow-ups each topic's
     scoring_judge actually decides on, until the interview ends at
     MAX_TOPICS.
  3. Asserts every *main-question* QAItem recorded a real
     question_source_id that matches a real data/question_bank.json entry
     for this job_type, in the expected behavioral -> technical ->
     case_analysis rotation order; every follow-up QAItem has
     question_source_id=None.
  4. Saves the session via backend/storage/db.py, reloads it, and confirms
     question_source_id survives the JSON round-trip.
  5. Deletes the test session row afterward -- same cleanup discipline as
     the week-11 voice smoke test.

Run it with:

    python scripts/smoke_test_week12.py

Requires a GROQ_API_KEY (.env or environment) and the real dependency set
in requirements.txt (chromadb, sentence-transformers, groq) -- this cannot
be run inside a sandboxed bridge missing those, only in a real project
environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

from backend.conversation import session_adapter  # noqa: E402
from backend.rag.retriever import retrieve_questions  # noqa: E402
from backend.storage.db import DEFAULT_DB_PATH, load_session, save_session  # noqa: E402
from models.session_schema import (  # noqa: E402
    ExperienceLevel,
    InterviewSession,
    InterviewStage,
    SessionConfig,
)

JOB_TYPE = "技术"
EXPECTED_ROTATION = ["behavioral", "technical", "case_analysis"]

# Answers long/specific enough that scoring_judge is likely to grade them
# HIGH and move on reasonably quickly -- keeps this script's Groq-call
# count (and runtime) bounded rather than following every possible
# follow-up chain to FollowUpState's max depth.
CANNED_ANSWERS = [
    "我之前在一个后端项目里负责性能优化，通过pprof定位到瓶颈在数据库连接池"
    "配置过小，调大连接池并加了慢查询日志之后，P99延迟从800ms降到了120ms，"
    "整个过程和团队同步了每一步的排查思路。",
    "我会先看这个问题的边界条件和数据规模，用哈希表把查找复杂度从O(n)降到"
    "O(1)，再考虑并发场景下需不需要加锁；如果数据量特别大，会进一步考虑分"
    "片存储。",
    "如果是我来设计，我会先梳理清楚各个模块之间的依赖关系，把强一致性要求"
    "的部分放在同一个事务边界内，弱一致性的部分用消息队列异步解耦，同时预"
    "留好监控和降级开关。",
]
MAX_ROUNDS_PER_TOPIC = 6  # safety cap so a stuck topic can't loop forever


def _assert_question_matches_bank(question_source_id: str, expected_question_type: str) -> None:
    candidates = retrieve_questions(JOB_TYPE, question_type=expected_question_type, k=50)
    matching_ids = {q.question_id for q in candidates}
    assert question_source_id in matching_ids, (
        f"question_source_id={question_source_id!r} is not a real "
        f"{JOB_TYPE}/{expected_question_type} bank entry"
    )


def main() -> None:
    interview_session = InterviewSession(
        config=SessionConfig(
            job_type=JOB_TYPE,
            experience_level=ExperienceLevel.MID,
            interview_stage=InterviewStage.TECH_ROUND_1,
            target_company=None,
            difficulty=3,
            interviewer_persona="技术挖掘型",
            language="zh",
        )
    )
    save_session(interview_session)
    print(f"[setup] test session_id = {interview_session.session_id}")

    opening_line, first_question, engine_session, progress = session_adapter.start(
        "技术挖掘型", "zh", JOB_TYPE, InterviewStage.TECH_ROUND_1
    )
    print(f"\n[opening] {opening_line}")
    print(f"[topic 1 question] {first_question}")
    assert progress.current_topic_question_id is not None, "expected topic 1 to be RAG-grounded"
    _assert_question_matches_bank(progress.current_topic_question_id, "behavioral")
    print(f"[ok] topic 1 question_source_id={progress.current_topic_question_id} matches a real behavioral question")

    answer_idx = 0
    interview_should_end = False
    rounds_this_topic = 0
    last_topics_started = progress.topics_started

    while not interview_should_end:
        rounds_this_topic += 1
        assert rounds_this_topic <= MAX_ROUNDS_PER_TOPIC, "topic did not wrap up within the safety cap"

        answer = CANNED_ANSWERS[answer_idx % len(CANNED_ANSWERS)]
        answer_idx += 1

        result, progress, interview_should_end, feedback = session_adapter.submit_round(
            answer, engine_session, progress, interview_session
        )
        recorded = interview_session.qa_items[-1]
        print(f"\n[round] action={result.action} question_source_id={recorded.question_source_id!r}")
        print(f"  Q: {recorded.question_text}")
        print(f"  A: {recorded.answer_text[:60]}...")
        if not interview_should_end:
            print(f"  reply: {result.reply[:120]}...")

        if progress.topics_started != last_topics_started:
            rounds_this_topic = 0
            last_topics_started = progress.topics_started
            expected_type = EXPECTED_ROTATION[(progress.topics_started - 1) % len(EXPECTED_ROTATION)]
            assert progress.current_topic_question_id is not None, (
                f"expected topic {progress.topics_started} to be RAG-grounded"
            )
            _assert_question_matches_bank(progress.current_topic_question_id, expected_type)
            print(
                f"[ok] topic {progress.topics_started} question_source_id="
                f"{progress.current_topic_question_id} matches a real {expected_type} question"
            )

    print(f"\n[ended] interview ended after {len(interview_session.qa_items)} recorded turns")

    # --- verify the main-question vs. follow-up question_source_id split ---
    main_items = [item for item in interview_session.qa_items if item.parent_turn_id is None]
    follow_up_items = [item for item in interview_session.qa_items if item.parent_turn_id is not None]
    assert len(main_items) == 3, f"expected 3 main-topic QAItems, got {len(main_items)}"
    for item in main_items:
        assert item.question_source_id is not None, f"main QAItem {item.turn_id} missing question_source_id"
    for item in follow_up_items:
        assert item.question_source_id is None, f"follow-up QAItem {item.turn_id} unexpectedly has question_source_id"
    print(f"[ok] {len(main_items)} main-topic QAItems all have question_source_id; "
          f"{len(follow_up_items)} follow-ups all have None")

    # --- verify persistence round-trip ---
    session_adapter.end_interview(interview_session)
    reloaded = load_session(interview_session.session_id)
    assert reloaded is not None
    reloaded_main_ids = sorted(item.question_source_id for item in reloaded.qa_items if item.parent_turn_id is None)
    original_main_ids = sorted(item.question_source_id for item in interview_session.qa_items if item.parent_turn_id is None)
    assert reloaded_main_ids == original_main_ids, "question_source_id did not survive save/load round-trip"
    print("[ok] question_source_id survives save_session()/load_session() round-trip")

    # --- cleanup ---
    import sqlite3

    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (interview_session.session_id,))
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (interview_session.session_id,)
    ).fetchone()[0]
    conn.close()
    assert remaining == 0
    print(f"[cleanup] removed test session {interview_session.session_id} from {DEFAULT_DB_PATH}")

    print("\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
