"""
Functional sanity tests for backend/scoring/baseline.py -- these check
that score_answer() runs end to end (real embedding model, no mocking) and
behaves sensibly on hand-written answers of deliberately different
quality, plus that the three decision-22 protective mechanisms actually
trigger. This is NOT an accuracy evaluation: it never touches
data/labeled_answers_draft.json, whose scores are still unreviewed
placeholders (see docs/decision_log.md decision 23). All answer texts
here are written fresh for this test file.
"""
from __future__ import annotations

import pytest

from backend.scoring.baseline import score_answer
from models.question_schema import load_questions_from_json

SAMPLE_QUESTIONS_PATH = "data/sample_questions.json"

_DIMENSIONS = ("structure_completeness", "keyword_coverage", "logical_coherence", "specificity")


@pytest.fixture(scope="module")
def questions() -> dict:
    return {q.question_id: q for q in load_questions_from_json(SAMPLE_QUESTIONS_PATH)}


def test_sample_questions_load_and_cover_all_three_types(questions):
    types = {q.question_type for q in questions.values()}
    assert types == {"behavioral", "technical", "case_analysis"}
    assert len(questions) == 30


def test_score_answer_shape_and_ranges(questions):
    question = questions["behavioral_01"]
    result = score_answer("我在项目里主要负责带团队，大家配合得都挺好，最后项目也顺利完成了。", question)

    assert result["question_id"] == "behavioral_01"
    assert result["question_type"] == "behavioral"
    assert "cross_question_type_note" in result and result["cross_question_type_note"]

    for dim in _DIMENSIONS:
        assert dim in result
        assert set(result[dim].keys()) == {"score", "explanation", "highlights"}
        assert 0.0 <= result[dim]["score"] <= 10.0
        assert isinstance(result[dim]["explanation"], str) and result[dim]["explanation"]
        assert isinstance(result[dim]["highlights"], list)

    assert 0.0 <= result["overall_score"] <= 10.0
    assert isinstance(result["score_ceiling_applied"], bool)
    assert isinstance(result["keyword_stuffing_warning"], bool)


def test_detailed_answer_scores_higher_than_vague_answer(questions):
    question = questions["behavioral_01"]

    vague_answer = "我在项目里主要负责带团队，大家配合得都挺好，最后项目也顺利完成了。"
    detailed_answer = (
        "去年双十一前，公司要在4周内上线一个支撑大促预热的优惠券和实时库存模块，我是这个4人小组的负责人。"
        "目标是保证预热期券核销率和库存准确率都达标。我把任务拆成前端页面、后端接口、数据埋点三条线，"
        "按各自专长分配给3位同事，并建立每周三次的进度同步机制。项目进行到第2周，负责后端的同事因病请假两周，"
        "我评估后把接口联调工作拆一部分给自己、另一部分临时借调另一个组的同事补位，同时和产品经理沟通调整了优先级。"
        "最终项目提前2天完成，大促期间优惠券核销率比上次提升了18%，库存准确率保持在99.5%以上。"
    )

    vague_result = score_answer(vague_answer, question)
    detailed_result = score_answer(detailed_answer, question)

    assert detailed_result["overall_score"] > vague_result["overall_score"]
    assert detailed_result["specificity"]["score"] > vague_result["specificity"]["score"]
    assert detailed_result["structure_completeness"]["score"] > vague_result["structure_completeness"]["score"]


def test_keyword_coverage_detects_synonym_cluster_hits(questions):
    """Answer literally contains several of behavioral_01's cluster canonical terms -- coverage must reflect that,
    not stay at zero (this is the direct "does synonym-cluster matching actually work" check)."""
    question = questions["behavioral_01"]
    answer = (
        "这次经历很好地体现了我的领导力。项目一开始我先做了目标拆解，把大目标拆成几个子任务，"
        "然后给每个人做了分工。过程中我也做了跨团队沟通，协调了另一个小组的资源。"
        "最终项目按期交付，也算是达成了目标。"
    )
    result = score_answer(answer, question)
    assert result["keyword_coverage"]["score"] > 1.0
    assert "领导力" in result["keyword_coverage"]["explanation"]


def test_empty_answer_returns_lowest_band_without_crashing(questions):
    question = questions["technical_01"]
    result = score_answer("   ", question)

    for dim in _DIMENSIONS:
        assert result[dim]["score"] == 1.0
    assert result["overall_score"] <= 1.0
    assert result["score_ceiling_applied"] is True  # specificity(1.0) < 3.0 floor


def test_specificity_floor_caps_overall_score(questions):
    """A structurally-complete, keyword-dense but zero-detail answer must trip decision-22 mechanism 1:
    overall capped at 50% of the 0-10 scale."""
    question = questions["behavioral_01"]
    stuffed_answer = "领导力。目标拆解。授权。激励团队。跨部门协作。决策。复盘总结。结果达成。"

    result = score_answer(stuffed_answer, question)

    assert result["specificity"]["score"] < 3.0
    assert result["score_ceiling_applied"] is True
    assert result["overall_score"] <= 5.0
    assert result["overall_score"] <= result["overall_score_raw"]


def test_keyword_stuffing_warning_fires_on_high_coverage_low_specificity(questions):
    """decision-22 mechanism 2: high keyword coverage + low specificity together must flag for manual review."""
    question = questions["behavioral_01"]
    stuffed_answer = "领导力。目标拆解。授权。激励团队。跨部门协作。决策。复盘总结。结果达成。"

    result = score_answer(stuffed_answer, question)

    assert result["keyword_coverage"]["score"] >= 7.0
    assert result["specificity"]["score"] <= 4.0
    assert result["keyword_stuffing_warning"] is True


def test_keyword_stuffing_warning_does_not_fire_on_genuine_detailed_answer(questions):
    """A real, substantive answer with decent keyword coverage should NOT be flagged as suspected stuffing."""
    question = questions["behavioral_01"]
    detailed_answer = (
        "去年双十一前，公司要在4周内上线一个支撑大促预热的优惠券和实时库存模块，我是这个4人小组的负责人。"
        "目标是保证预热期券核销率和库存准确率都达标。我把任务拆成前端页面、后端接口、数据埋点三条线，"
        "按各自专长分配给3位同事，并建立每周三次的进度同步机制。最终项目提前2天完成，"
        "大促期间优惠券核销率比上次提升了18%，库存准确率保持在99.5%以上。"
    )
    result = score_answer(detailed_answer, question)
    assert result["keyword_stuffing_warning"] is False


@pytest.mark.parametrize(
    "question_id,answer",
    [
        ("technical_01", "用发号器生成自增ID再做Base62编码，读多写少的场景加一层Redis缓存，数据库分库分表。"),
        (
            "case_analysis_01",
            "首先要确认下滑的具体口径，然后按渠道和新老用户拆解，验证是否是某次版本发布导致的，"
            "最后针对验证结果给出短期止血和长期优化方案，并持续跟踪指标恢复情况。",
        ),
    ],
)
def test_score_answer_works_across_question_types(questions, question_id, answer):
    """Runs score_answer() on one technical and one case_analysis question to confirm the
    per-question-type structure elements / weights path (not just behavioral) executes cleanly."""
    question = questions[question_id]
    result = score_answer(answer, question)
    assert result["question_type"] == question.question_type
    for dim in _DIMENSIONS:
        assert 0.0 <= result[dim]["score"] <= 10.0


def test_detailed_answer_produces_real_sentence_highlights(questions):
    """Week 13 (decision #14 item 2 / #39): a real multi-sentence answer with known synonym-cluster
    hits (same answer as test_keyword_coverage_detects_synonym_cluster_hits) should carry real
    Highlight entries pointing at real sentences from the answer, not just prose explanations."""
    question = questions["behavioral_01"]
    answer = (
        "这次经历很好地体现了我的领导力。项目一开始我先做了目标拆解，把大目标拆成几个子任务，"
        "然后给每个人做了分工。过程中我也做了跨团队沟通，协调了另一个小组的资源。"
        "最终项目按期交付，也算是达成了目标。"
    )
    result = score_answer(answer, question)
    sentence_count = len(_split_sentences_for_test(answer))

    # keyword_coverage and logical_coherence always produce highlights whenever there's at
    # least one cluster hit / at least two sentences (both true here, see
    # test_keyword_coverage_detects_synonym_cluster_hits for the cluster-hit guarantee).
    for dim in ("keyword_coverage", "specificity", "structure_completeness"):
        highlights = result[dim]["highlights"]
        assert isinstance(highlights, list)
        for h in highlights:
            assert isinstance(h["sentence_index"], int)
            assert 0 <= h["sentence_index"] < sentence_count
            assert h["sentence_text"]
            assert h["polarity"] in ("positive", "negative")
            assert h["reason"]
    assert len(result["keyword_coverage"]["highlights"]) > 0

    # logical_coherence always emits exactly one highlight (the weakest transition) for a
    # multi-sentence answer, and it must be negative by construction.
    coherence_highlights = result["logical_coherence"]["highlights"]
    assert len(coherence_highlights) == 1
    assert coherence_highlights[0]["sentence_index"] < sentence_count
    assert coherence_highlights[0]["polarity"] == "negative"


def test_empty_answer_has_no_highlights(questions):
    """An empty answer can't drive any real sentence highlight in any dimension."""
    question = questions["technical_01"]
    result = score_answer("   ", question)
    for dim in _DIMENSIONS:
        assert result[dim]["highlights"] == []


def test_specificity_credits_tool_names_embedded_in_chinese_text(questions):
    """Week 16 (decision #45): _count_proper_noun_markers() must fire on a capitalized tool/product
    name even with no surrounding whitespace (e.g. "用Kafka做" with no space before/after "Kafka") --
    this is the exact case a naive \\b-based regex silently fails on, since CJK characters count as
    \\w in Python's default Unicode regex mode and so never produce a \\b next to Latin letters."""
    question = questions["technical_01"]
    answer_with_tool_names = "用Kafka做异步解耦，缓存用Redis，接口层用Nginx做限流。"
    answer_without_markers = "做了一些消息处理和缓存和限流方面的优化工作。"

    with_result = score_answer(answer_with_tool_names, question)
    without_result = score_answer(answer_without_markers, question)

    assert "工具/产品专名" in with_result["specificity"]["explanation"]
    assert with_result["specificity"]["score"] >= without_result["specificity"]["score"]


def test_specificity_credits_widened_time_span_and_metric_markers(questions):
    """Week 16 (decision #45): the widened _DETAIL_MARKER_WORDS list should count spelled-out time
    spans ("三个月") and product metrics ("转化率") as detail markers, not just bare digits."""
    from backend.scoring.baseline import _count_sentence_markers

    assert _count_sentence_markers("我们花了三个月把转化率提升了一大截") > 0
    assert _count_sentence_markers("这个方案还不错") == 0


def _split_sentences_for_test(text: str) -> list[str]:
    """Local re-import of baseline.py's own sentence splitter, so this test can validate
    sentence_index bounds without duplicating the splitting regex."""
    from backend.scoring.baseline import _split_sentences

    return _split_sentences(text)
