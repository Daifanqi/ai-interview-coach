"""
Week 13 real end-to-end smoke test: builds a real InterviewSession against
real data/question_bank.json entries, scores it through the real embedding
model (backend/scoring/baseline.py, no mocking) and a real Groq call for the
highlight pick (backend/report/highlight_picker.py), persists the resulting
ReviewReport through backend/storage/db.py's real SQLite round-trip
(including the new detailed_scores field), and verifies list_sessions_by_user()
surfaces a second session in the first session's history_trend.

Run with: python scripts/smoke_test_week13.py
Requires: GROQ_API_KEY set (.env or environment), real chromadb/sentence-
transformers/groq dependencies installed -- same requirements as
scripts/smoke_test_week12.py.

Cleans up every session row it creates from data/sessions.db afterward,
same pattern as smoke_test_week12.py.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.report.generator import generate_review_report  # noqa: E402
from backend.storage.db import DEFAULT_DB_PATH, load_session, save_session  # noqa: E402
from models.question_schema import load_questions_from_json  # noqa: E402
from models.session_schema import (  # noqa: E402
    ExperienceLevel,
    InterviewSession,
    InterviewStage,
    QAItem,
    SessionConfig,
)

QUESTION_BANK_PATH = "data/question_bank.json"
TEST_JOB_TYPE = "技术"
TEST_USER_ID = "smoke-test-week13-user"

ANSWERS = {
    "technical": (
        "先明确投递语义：需要保证消息至少送达一次，客户端按消息序列号去重。在线状态用长连接网关维护，"
        "每个用户连接到一个网关节点，状态写入Redis并设置心跳过期时间，其他服务通过订阅Redis的状态变更来感知上下线。"
        "消息投递上，在线用户直接通过网关长连接推送，离线用户先落库再走推送通知，用户上线后拉取离线消息补齐。"
        "为了保证顺序性，同一会话的消息按递增的seq_id写入，客户端按seq_id排序展示，出现空洞时主动拉取补齐。"
    ),
    "case_analysis": (
        "首先确认延迟突增的具体时间点、影响范围（是否所有接口还是某个接口、是否所有实例还是部分实例），"
        "然后按维度拆解：应用层看GC耗时和线程池排队情况，中间件层看数据库慢查询和连接池水位，基础设施层看是否有节点资源打满或网络抖动。"
        "接着结合最近的变更记录，判断是否有新发布、配置变更或流量突增导致。"
        "定位到具体原因后，先做止血：比如临时扩容、回滚变更或降级非核心依赖，恢复P99到正常水平；"
        "之后再做根因修复，并补充监控告警和压测用例，防止同类问题复现，持续观察P99一周确认稳定。"
    ),
}


def _pick_questions():
    questions = [q for q in load_questions_from_json(QUESTION_BANK_PATH) if q.job_type == TEST_JOB_TYPE]
    assert questions, f"No questions found for job_type={TEST_JOB_TYPE!r} in {QUESTION_BANK_PATH}"
    by_type = {}
    for q in questions:
        by_type.setdefault(q.question_type, q)
    picked = [by_type["technical"], by_type["case_analysis"]]
    assert all(picked), f"Expected both a technical and case_analysis question for job_type={TEST_JOB_TYPE!r}"
    return picked


def build_test_session(user_id: str = TEST_USER_ID) -> InterviewSession:
    technical_q, case_q = _pick_questions()
    qa_items = [
        QAItem(question_text=technical_q.question_text, answer_text=ANSWERS["technical"], question_source_id=technical_q.question_id),
        QAItem(question_text=case_q.question_text, answer_text=ANSWERS["case_analysis"], question_source_id=case_q.question_id),
        # A follow-up (no question_source_id) mixed in -- must be skipped by scoring, not crash it.
        QAItem(question_text="能展开讲讲降级策略吗？", answer_text="核心链路保留，非核心依赖直接熔断返回默认值。", question_source_id=None),
    ]
    return InterviewSession(
        user_id=user_id,
        config=SessionConfig(
            job_type=TEST_JOB_TYPE,
            experience_level=ExperienceLevel.MID,
            interview_stage=InterviewStage.TECH_ROUND_1,
            target_company=None,
            difficulty=3,
            interviewer_persona="technical",
            language="zh",
        ),
        qa_items=qa_items,
    )


def cleanup(session_ids: list[str]) -> None:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    try:
        for session_id in session_ids:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    session = build_test_session()
    main_topic_turn_ids = {item.turn_id for item in session.qa_items if item.question_source_id}
    print(f"Built test session {session.session_id} with {len(main_topic_turn_ids)} main-topic answers (+1 follow-up)")

    report = generate_review_report(session)
    assert set(report.detailed_scores.keys()) == main_topic_turn_ids
    assert set(report.per_answer_scores.keys()) == main_topic_turn_ids
    assert 0.0 <= report.overall_score <= 10.0
    assert report.highlight_turn_id in main_topic_turn_ids
    assert report.highlight_reason
    assert report.voice_summary
    print(f"generate_review_report: overall_score={report.overall_score}, highlight_turn_id={report.highlight_turn_id}")
    print(f"highlight_reason: {report.highlight_reason}")

    total_highlights = 0
    for turn_id, detail in report.detailed_scores.items():
        n_highlights = sum(
            len(dim.highlights)
            for dim in (detail.structure_completeness, detail.keyword_coverage, detail.logical_coherence, detail.specificity)
        )
        total_highlights += n_highlights
        print(f"  turn {turn_id}: overall={detail.overall_score}, sentence highlights={n_highlights}")
    assert total_highlights > 0, "Expected at least one sentence highlight across a detailed, non-empty session"

    session.report = report
    save_session(session)
    print("Saved session with report to sessions.db")

    reloaded = load_session(session.session_id)
    assert reloaded is not None and reloaded.report is not None
    assert set(reloaded.report.detailed_scores.keys()) == set(report.detailed_scores.keys())
    for turn_id in report.detailed_scores:
        original = report.detailed_scores[turn_id]
        round_tripped = reloaded.report.detailed_scores[turn_id]
        assert round_tripped.overall_score == original.overall_score
        assert round_tripped.question_id == original.question_id
        original_highlight_texts = [h.sentence_text for h in original.structure_completeness.highlights]
        round_tripped_highlight_texts = [h.sentence_text for h in round_tripped.structure_completeness.highlights]
        assert round_tripped_highlight_texts == original_highlight_texts
    print("load_session round-trip preserved detailed_scores (highlights included)")

    # A second, slightly-later session for the same user, to exercise history_trend / list_sessions_by_user.
    second_session = build_test_session()
    second_report = generate_review_report(second_session)
    second_session.report = second_report
    save_session(second_session)
    print(f"Saved a second session {second_session.session_id} for the same user")

    trend_report = generate_review_report(session)
    trend_session_ids = {tp.session_id for tp in trend_report.history_trend}
    assert second_session.session_id in trend_session_ids, "Expected the second session to appear in history_trend"
    assert session.session_id not in trend_session_ids, "A session must not appear in its own history_trend"
    print(f"history_trend: {len(trend_report.history_trend)} past session(s) found for user {TEST_USER_ID}")

    cleanup([session.session_id, second_session.session_id])
    print("Cleaned up test session rows from sessions.db")
    print("\nAll Week 13 smoke test checks passed.")


if __name__ == "__main__":
    main()
