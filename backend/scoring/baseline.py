"""
Baseline scoring engine: score_answer() implements the four-dimension
rubric in docs/scoring_rubric.md (structure completeness / keyword
coverage / logical coherence / specificity) with embedding-based and
lexical heuristics -- no LLM call, so it is cheap enough to run on every
answer and to run offline in tests.

Signal sources per dimension (rubric section references in parentheses):
- structure_completeness (3.1): for each required structural element (STAR
  for behavioral / problem-solution-tradeoff-conclusion for technical /
  the five-step case framework for case_analysis), embed a canonical
  description of that element and check whether any sentence in the answer
  is semantically close to it. Element-presence count maps to a score band.
- keyword_coverage (3.2): embedding-based semantic matching against
  question.keyword_clusters -- a cluster counts as hit if any answer
  sentence/phrase is semantically close (cosine similarity above
  _KEYWORD_SIMILARITY_THRESHOLD) to any of its terms (canonical or
  synonym), not just an exact substring match. Coverage ratio maps
  directly onto the rubric's own 90/70/50/30% band thresholds.
- logical_coherence (3.3) and specificity (3.4): generic composite
  heuristics blending (a) semantic similarity between the answer and
  question.reference_points, (b) sentence-to-sentence embedding
  similarity as a coherence proxy, and (c) lexical markers (causal
  connectors for coherence, concrete-detail cues + digits for
  specificity).

IMPORTANT -- calibration status: every threshold/weight constant below
(_ELEMENT_PRESENCE_THRESHOLD, _ADJACENCY_MEAN_LOW/HIGH, etc.) is a
reasoned-but-unvalidated placeholder. docs/decision_log.md decision 23
tracks that data/labeled_answers_draft.json has not yet been manually
reviewed; once that review lands, these constants should be recalibrated
against real human-reviewed scores rather than left as first-guess values.
Do not treat this module's output as a validated grader until that pass
happens.

Protective mechanisms (docs/decision_log.md decision 22) are applied in
backend/scoring/report.py's build_score_report(), not here -- this module
only produces the four raw DimensionScores.
"""
from __future__ import annotations

import re
from dataclasses import asdict

import numpy as np

from backend.scoring.embedding import cosine_similarity, embed_texts
from backend.scoring.report import DimensionScore, Highlight, ScoreReport, build_score_report
from models.question_schema import Question, QuestionType

# ---------------------------------------------------------------------------
# Shared ratio -> score-band mapping
# ---------------------------------------------------------------------------

# (cutoff, representative score, band label). Cutoffs mirror the exact
# percentage thresholds docs/scoring_rubric.md section 3.2 defines for
# keyword coverage (90/70/50/30%); the other three dimensions reuse the
# same cutoffs against a composite 0-1 heuristic signal in lieu of the
# rubric's qualitative wording for those dimensions, since this is a
# heuristic baseline rather than an LLM judge (see module docstring).
_BAND_CUTOFFS: list[tuple[float, float, str]] = [
    (0.9, 9.5, "9-10"),
    (0.7, 7.5, "7-8"),
    (0.5, 5.5, "5-6"),
    (0.3, 3.5, "3-4"),
    (0.0, 1.0, "0-2"),
]


def _ratio_to_band(ratio: float) -> tuple[float, str]:
    """Map a 0-1 heuristic ratio to (representative 0-10 score, rubric band label)."""
    ratio = max(0.0, min(1.0, ratio))
    for cutoff, score, label in _BAND_CUTOFFS:
        if ratio >= cutoff:
            return score, label
    return 1.0, "0-2"  # unreachable (cutoff 0.0 always matches), kept for completeness


def _normalize(value: float, lo: float, hi: float) -> float:
    """Min-max normalize `value` into [0, 1] against the [lo, hi] range."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


# ---------------------------------------------------------------------------
# Sentence splitting (shared by structure / coherence / specificity)
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？.!?；;\n])")
_MIN_SENTENCE_CHARS = 4  # fragments shorter than this get merged into the previous sentence


def _split_sentences(text: str) -> list[str]:
    """Split mixed Chinese/English text into sentence-ish units for per-sentence embedding."""
    if not text or not text.strip():
        return []
    raw_pieces = _SENTENCE_SPLIT_PATTERN.split(text)
    pieces = [p.strip() for p in raw_pieces if p.strip()]

    merged: list[str] = []
    for piece in pieces:
        if merged and len(piece) < _MIN_SENTENCE_CHARS:
            merged[-1] = f"{merged[-1]}{piece}"
        else:
            merged.append(piece)
    return merged


def _mean_pool(embeddings: np.ndarray) -> np.ndarray:
    """Mean-pool a set of L2-normalized embeddings into one re-normalized whole-text vector."""
    pooled = embeddings.mean(axis=0)
    norm = np.linalg.norm(pooled)
    return pooled / norm if norm > 0 else pooled


# ---------------------------------------------------------------------------
# Reference-point similarity signal, shared by logical_coherence and
# specificity (both dimensions use it per the task spec, at different
# weights -- see each scorer below).
# ---------------------------------------------------------------------------

_REF_SIM_LOW = 0.15
_REF_SIM_HIGH = 0.55


def _reference_point_signal(sentence_embeddings: np.ndarray, reference_embeddings: np.ndarray) -> tuple[float, float]:
    """
    Mean cosine similarity between the whole answer and each of
    question.reference_points, plus its normalized 0-1 signal.

    Returns (avg_similarity, normalized_signal); (0.0, 0.5) -- a neutral
    signal that neither rewards nor penalizes -- when there are no
    reference points or no answer content to compare.
    """
    if reference_embeddings.size == 0 or sentence_embeddings.size == 0:
        return 0.0, 0.5
    answer_embedding = _mean_pool(sentence_embeddings)
    sims = [cosine_similarity(answer_embedding, ref_emb) for ref_emb in reference_embeddings]
    avg_sim = float(np.mean(sims))
    return avg_sim, _normalize(avg_sim, _REF_SIM_LOW, _REF_SIM_HIGH)


# ---------------------------------------------------------------------------
# Dimension 1: structure_completeness (rubric 3.1)
# ---------------------------------------------------------------------------

# (element label, canonical description embedded and matched against
# answer sentences). Labels/descriptions are paraphrases of
# docs/scoring_rubric.md section 3.1's per-question-type element list.
STRUCTURE_ELEMENTS: dict[QuestionType, list[tuple[str, str]]] = {
    "behavioral": [
        ("情境 (S)", "描述面试问题相关的具体情境、背景或所处的环境"),
        ("任务 (T)", "说明当时需要完成的具体任务或目标"),
        ("行动 (A)", "说明为完成任务采取的具体行动、做法或决策"),
        ("结果 (R)", "说明最终取得的结果、产出或量化效果"),
    ],
    "technical": [
        ("问题描述", "说明要解决的具体技术问题或需求"),
        ("技术方案", "说明采用的具体技术方案、架构设计或实现方式"),
        ("权衡讨论", "讨论了不同方案之间的权衡、取舍或具体对比"),
        ("结论", "给出最终结论、效果或采用的具体方案"),
    ],
    "case_analysis": [
        ("问题界定 (Define)", "澄清问题的具体边界、指标、时间范围或对比基准"),
        ("框架拆解 (Structure)", "给出结构化的拆解框架来穷尽可能的原因"),
        ("验证排查 (Diagnose)", "说明针对假设采用的具体验证或排查方法"),
        ("方案与优先级 (Prioritize)", "给出具体方案并按优先级排序，区分短期和长期"),
        ("结论与验证机制 (Conclude)", "说明如何衡量方案效果、监控哪些指标、如何调整"),
    ],
}

STRUCTURE_LABEL: dict[QuestionType, str] = {
    "behavioral": "STAR四要素",
    "technical": "问题-方案-权衡-结论四部分",
    "case_analysis": "案例分析五环节",
}

# A sentence "counts" for a structural element if their embeddings' cosine
# similarity clears this bar. _ELEMENT_STRONG_THRESHOLD additionally
# distinguishes rubric's 9-10 ("all elements present, clearly delineated")
# from 7-8 ("all present but blurred/imbalanced") when every element is
# present -- see _score_structure_completeness.
_ELEMENT_PRESENCE_THRESHOLD = 0.38
_ELEMENT_STRONG_THRESHOLD = 0.50

# A sentence shorter than this many characters is excluded from structure-
# element matching entirely -- a bare keyword phrase (e.g. "结果达成") can sit
# close enough to an element's description in embedding space to look
# "present" without containing any actual narrative content, which would
# let an answer game this dimension by stringing keyword-cluster terms
# together as fake "sentences" (caught during development: see the
# adversarial keyword-stuffing probe this constant was added to fix).
# Real STAR/problem-solution/five-step clauses run well past this length.
_MIN_SUBSTANTIVE_SENTENCE_CHARS = 12

_structure_element_embedding_cache: dict[QuestionType, np.ndarray] = {}


def _get_structure_element_embeddings(question_type: QuestionType) -> np.ndarray:
    """Lazily embed (and cache) the canonical element descriptions for one question_type."""
    if question_type not in _structure_element_embedding_cache:
        descriptions = [desc for _, desc in STRUCTURE_ELEMENTS[question_type]]
        _structure_element_embedding_cache[question_type] = embed_texts(descriptions)
    return _structure_element_embedding_cache[question_type]


def _score_structure_completeness(
    question_type: QuestionType, sentences: list[str], sentence_embeddings: np.ndarray
) -> DimensionScore:
    elements = STRUCTURE_ELEMENTS[question_type]
    label = STRUCTURE_LABEL[question_type]
    total = len(elements)

    if not sentences:
        return DimensionScore(score=1.0, explanation=f"回答为空或过短，无法识别{label}中的任何要素，对应0-2分档。")

    substantive_idx = [i for i, s in enumerate(sentences) if len(s) >= _MIN_SUBSTANTIVE_SENTENCE_CHARS]
    if not substantive_idx:
        return DimensionScore(
            score=1.0,
            explanation=f"回答只包含零散的短语片段，没有完整语句描述{label}中的任何要素，对应0-2分档。",
        )

    element_embeddings = _get_structure_element_embeddings(question_type)
    substantive_embeddings = sentence_embeddings[substantive_idx]
    # (elements x substantive sentences) cosine similarity matrix -- both
    # sides are L2-normalized, so a plain matmul is the cosine similarity.
    sims = element_embeddings @ substantive_embeddings.T
    max_sim_per_element = sims.max(axis=1)
    best_sentence_per_element = sims.argmax(axis=1)  # index into substantive_idx/substantive_embeddings
    present = max_sim_per_element >= _ELEMENT_PRESENCE_THRESHOLD
    present_count = int(present.sum())
    present_labels = [elements[i][0] for i in range(total) if present[i]]
    missing_labels = [elements[i][0] for i in range(total) if not present[i]]

    # One positive highlight per present element, pointing at the sentence
    # that matched it best (week 13, decision #14 item 2 / #39).
    highlights = [
        Highlight(
            sentence_index=(sent_idx := substantive_idx[best_sentence_per_element[i]]),
            sentence_text=sentences[sent_idx],
            polarity="positive",
            reason=f"体现了{label}中的「{elements[i][0]}」要素",
        )
        for i in range(total)
        if present[i]
    ]

    ratio = present_count / total
    score, band = _ratio_to_band(ratio)

    if present_count == total:
        avg_strength = float(max_sim_per_element.mean())
        if avg_strength < _ELEMENT_STRONG_THRESHOLD:
            # All elements technically detected, but only weakly -- matches
            # rubric's 7-8 band ("四要素齐全但轻微混淆/失衡"), not 9-10.
            score, band = 7.5, "7-8"
            detail = f"识别到全部 {total}/{total} 个{label}（{'、'.join(present_labels)}），但要素信号偏弱、区分度不高"
        else:
            detail = f"识别到全部 {total}/{total} 个{label}，且要素区分清晰（{'、'.join(present_labels)}）"
    else:
        detail = f"识别到 {present_count}/{total} 个{label}（缺失：{'、'.join(missing_labels) if missing_labels else '无'}）"

    return DimensionScore(score=score, explanation=f"{detail}，对应{band}分档。", highlights=highlights)


# ---------------------------------------------------------------------------
# Dimension 2: keyword_coverage (rubric 3.2)
# ---------------------------------------------------------------------------

# A cluster counts as hit if any answer sentence/phrase's embedding is at
# least this cosine-similar to any of the cluster's terms (canonical or
# synonym) -- semantic matching instead of exact substring matching, so a
# natural paraphrase (e.g. "砍掉了三分之一的非核心功能" for the "优先级排序"
# cluster) is credited even though it contains none of the cluster's exact
# strings.
#
# Value picked by grid search against all 150 records in
# data/labeled_answers_human_reviewed.json (coarse sweep 0.20-0.64 in 0.02
# steps, then refined to 0.01 steps around the peak; see
# docs/decision_log.md decision 29 and results/baseline_accuracy.md for the
# full before/after comparison). 0.37 gives the best combination of MAE
# (1.84, vs. 3.59 for the old exact-substring matcher) and +/-1-point
# tolerance accuracy (38.7%, vs. 23%), and sits in a flat plateau (0.35-0.37
# all score within 0.1 points of MAE and within 1 point of accuracy of each
# other) rather than a knife-edge single-point peak. Thresholds below ~0.30
# over-match (average cluster-hit ratio climbs above 0.80, collapsing the
# dimension's discriminative power -- most answers score full coverage
# regardless of content); thresholds above ~0.45 under-match almost as
# badly as the old exact-substring approach did, since a keyword's signal
# gets diluted once it is embedded inside a full sentence rather than
# standing alone.
_KEYWORD_SIMILARITY_THRESHOLD = 0.37

_keyword_cluster_embedding_cache: dict[str, list[np.ndarray]] = {}


def _get_keyword_cluster_term_embeddings(question: Question) -> list[np.ndarray]:
    """Lazily embed (and cache) each keyword cluster's term list (canonical + synonyms) for one question.

    Returns one array per cluster, in cluster order, each shaped (n_terms_in_cluster, embedding_dim).
    """
    if question.question_id not in _keyword_cluster_embedding_cache:
        clusters = question.keyword_clusters
        all_terms = [term for cluster in clusters for term in cluster.all_terms()]
        all_term_embeddings = embed_texts(all_terms)

        per_cluster: list[np.ndarray] = []
        offset = 0
        for cluster in clusters:
            n_terms = len(cluster.all_terms())
            per_cluster.append(all_term_embeddings[offset : offset + n_terms])
            offset += n_terms
        _keyword_cluster_embedding_cache[question.question_id] = per_cluster
    return _keyword_cluster_embedding_cache[question.question_id]


def _score_keyword_coverage(
    question: Question, sentences: list[str], sentence_embeddings: np.ndarray
) -> DimensionScore:
    clusters = question.keyword_clusters
    total = len(clusters)
    if total == 0:
        return DimensionScore(score=5.5, explanation="该题未配置关键词库，关键词覆盖率维度不参与实际评分，给出中性分。")

    if not sentences:
        return DimensionScore(score=1.0, explanation="回答为空或过短，无法计算关键词覆盖率，对应0-2分档。")

    cluster_term_embeddings = _get_keyword_cluster_term_embeddings(question)
    hit_labels: list[str] = []
    highlights: list[Highlight] = []
    _MAX_KEYWORD_HIGHLIGHTS = 5  # mirrors hit_preview's own display cap below
    for cluster, term_embeddings in zip(clusters, cluster_term_embeddings):
        # (sentences x cluster terms) cosine similarity matrix -- both sides
        # are L2-normalized, so a plain matmul is the cosine similarity.
        sims = sentence_embeddings @ term_embeddings.T
        per_sentence_max = sims.max(axis=1)  # best term-match per sentence
        max_sim = float(per_sentence_max.max())
        if max_sim >= _KEYWORD_SIMILARITY_THRESHOLD:
            hit_labels.append(cluster.canonical)
            if len(highlights) < _MAX_KEYWORD_HIGHLIGHTS:
                best_sentence_idx = int(per_sentence_max.argmax())
                highlights.append(
                    Highlight(
                        sentence_index=best_sentence_idx,
                        sentence_text=sentences[best_sentence_idx],
                        polarity="positive",
                        reason=f"命中关键词簇「{cluster.canonical}」",
                    )
                )

    ratio = len(hit_labels) / total
    score, band = _ratio_to_band(ratio)
    pct = round(ratio * 100)

    hit_preview = "、".join(hit_labels[:5]) + ("等" if len(hit_labels) > 5 else "")
    explanation = (
        f"语义匹配命中关键词簇 {len(hit_labels)}/{total}（覆盖率 {pct}%"
        f"{'：' + hit_preview if hit_labels else ''}），"
        f"对应{band}分档（docs/scoring_rubric.md 第3.2节覆盖率区间，"
        f"相似度阈值{_KEYWORD_SIMILARITY_THRESHOLD}）。"
    )
    return DimensionScore(score=score, explanation=explanation, highlights=highlights)


# ---------------------------------------------------------------------------
# Dimension 3: logical_coherence (rubric 3.3, generic across question types)
# ---------------------------------------------------------------------------

_CONNECTOR_WORDS = (
    "因为", "所以", "因此", "由于", "从而", "导致", "于是", "结果",
    "但是", "然而", "不过", "虽然", "尽管", "首先", "其次", "最后", "另外", "接着",
    "because", "therefore", "thus", "as a result", "however", "although",
    "first", "second", "finally", "in addition", "consequently",
)
_EXPECTED_CONNECTOR_HITS_FOR_FULL_SIGNAL = 3

# Adjacent-sentence embedding similarity is used two ways, per empirical
# probing of this model on hand-written zh/en samples during development
# (a coherent 5-sentence narrative: mean~0.41/min~0.21; three deliberately
# unrelated sentences: mean~0.08/min~0.02):
#   - mean similarity: overall topical continuity across the answer.
#   - min similarity (the weakest single transition): catches one abrupt
#     "logical jump" even inside an otherwise-coherent answer, which is
#     closer to how rubric 3.3 actually talks about coherence ("存在2处
#     及以上逻辑跳跃") than a plain average would be on its own.
# Note these bounds intentionally do NOT reward high similarity beyond
# their high end -- very high adjacent-sentence similarity usually means
# the sentences are restating the same point (a specificity problem, not a
# coherence one; see rubric 3.4 / decision 22's floor mechanism, which is
# what actually catches vague-but-"coherent" answers, not this dimension).
_ADJACENCY_MEAN_LOW = 0.15
_ADJACENCY_MEAN_HIGH = 0.50
_ADJACENCY_MIN_LOW = 0.05
_ADJACENCY_MIN_HIGH = 0.30

# Weights for combining the coherence signals when there are >=2 sentences
# to compare. Adjacency (does each sentence flow into the next) is the
# primary signal per rubric 3.3's "前后是否有清晰的因果/递进关系";
# connector words and reference-point alignment are supporting signals.
_LOGICAL_ADJACENCY_WEIGHT = 0.55
_LOGICAL_CONNECTOR_WEIGHT = 0.20
_LOGICAL_REF_WEIGHT = 0.25


def _score_logical_coherence(
    answer: str,
    sentences: list[str],
    sentence_embeddings: np.ndarray,
    reference_embeddings: np.ndarray,
) -> DimensionScore:
    if not sentences:
        return DimensionScore(score=1.0, explanation="回答为空，无法判断逻辑连贯性，对应0-2分档。")

    lowered = answer.lower()
    connector_hits = [w for w in _CONNECTOR_WORDS if w in lowered]
    connector_signal = min(len(connector_hits), _EXPECTED_CONNECTOR_HITS_FOR_FULL_SIGNAL) / _EXPECTED_CONNECTOR_HITS_FOR_FULL_SIGNAL
    avg_ref_sim, ref_signal = _reference_point_signal(sentence_embeddings, reference_embeddings)

    if len(sentences) < 2:
        # A single fragment can't demonstrate a reasoning chain *between*
        # sentences -- fall back to the weaker connector/reference signals
        # alone, capped below "fully coherent" (rubric 3.3 frames coherence
        # around relationships *across* parts of the answer).
        combined = min(0.5 * connector_signal + 0.5 * ref_signal, 0.6)
        score, band = _ratio_to_band(combined)
        explanation = (
            f"回答仅有单个语句片段，无法评估句间逻辑关系，"
            f"按连接词信号（{len(connector_hits)}个）和参考要点相似度（{avg_ref_sim:.2f}）给出保守评分，对应{band}分档。"
        )
        return DimensionScore(score=score, explanation=explanation)

    adjacent_sims = [
        cosine_similarity(sentence_embeddings[i], sentence_embeddings[i + 1]) for i in range(len(sentences) - 1)
    ]
    mean_adjacent_sim = float(np.mean(adjacent_sims))
    min_adjacent_sim = float(np.min(adjacent_sims))
    mean_signal = _normalize(mean_adjacent_sim, _ADJACENCY_MEAN_LOW, _ADJACENCY_MEAN_HIGH)
    min_signal = _normalize(min_adjacent_sim, _ADJACENCY_MIN_LOW, _ADJACENCY_MIN_HIGH)
    adjacency_signal = 0.5 * mean_signal + 0.5 * min_signal

    combined = (
        _LOGICAL_ADJACENCY_WEIGHT * adjacency_signal
        + _LOGICAL_CONNECTOR_WEIGHT * connector_signal
        + _LOGICAL_REF_WEIGHT * ref_signal
    )
    score, band = _ratio_to_band(combined)

    # One negative highlight at the single weakest adjacent-sentence
    # transition (week 13) -- the sentence AFTER the weakest transition is
    # the one that reads as the "jump", since it's the one that fails to
    # follow naturally from what came before it.
    weakest_transition_idx = int(np.argmin(adjacent_sims))
    jump_sentence_idx = weakest_transition_idx + 1
    highlights = [
        Highlight(
            sentence_index=jump_sentence_idx,
            sentence_text=sentences[jump_sentence_idx],
            polarity="negative",
            reason="与上一句的衔接是全文中最弱的一处，读起来像是逻辑跳跃",
        )
    ]

    explanation = (
        f"句间语义衔接信号 {adjacency_signal:.2f}（相邻句平均相似度 {mean_adjacent_sim:.2f}，"
        f"最弱一处转折相似度 {min_adjacent_sim:.2f}），"
        f"命中逻辑连接词 {len(connector_hits)} 个，与参考要点相似度 {avg_ref_sim:.2f}，"
        f"综合对应{band}分档。"
    )
    return DimensionScore(score=score, explanation=explanation, highlights=highlights)


# ---------------------------------------------------------------------------
# Dimension 4: specificity (rubric 3.4, generic across question types)
# ---------------------------------------------------------------------------

# Covers rubric 3.4's own enumerated marker categories -- "数字、时间、场景、
# 工具/方法名称、具体角色分工" -- not just the numeric/data-report words the
# first pass of this list had (that omission under-counted answers that
# were concrete via role/method descriptions rather than digits, e.g.
# "给每个人做了分工" -- found via the KEYWORD_RICH probe during development).
#
# Week 16 (docs/decision_log.md decision #45) expansion: decision #27's
# accuracy evaluation flagged specificity as the second-worst dimension
# (MAE 2.27, +/-1 accuracy 36%) after keyword_coverage, which decision #29
# fixed by moving off exact lexical matching entirely. Specificity can't
# take the same "switch to embeddings" fix -- concreteness genuinely *is*
# a lexical/pattern property (a digit, a named tool, a time span), not a
# topical-similarity one an embedding model captures well -- so this
# round's fix instead (a) widens the fixed word list to cover categories
# the original list missed (time spans, quantifiers, scale/growth
# metrics) and (b) adds a regex-based signal for proper nouns (tool/
# product names like "Kafka"/"React"), which no fixed word list can ever
# enumerate. See _count_proper_noun_markers() below.
_DETAIL_MARKER_WORDS = (
    "具体", "数据", "指标", "比如", "例如", "百分比", "占比", "小时", "分钟",
    "第一", "第二", "大概", "约", "结果显示", "同比", "环比", "提升了", "降低了",
    "分工", "流程", "机制", "方法", "工具",
    # Time spans / scheduling (rubric 3.4's "时间" category was previously
    # only covered by bare digits, missing spelled-out spans like "三个月").
    "年", "月", "周", "季度", "天", "小时后", "半年", "两周", "三个月", "一年",
    # Quantifiers that convey scale without a literal digit.
    "多个", "几个", "若干", "一半", "三分之一", "四分之一", "翻了一倍", "成倍",
    # Scale / growth / product metrics common in technical and case-analysis answers.
    "用户量", "日活", "月活", "转化率", "留存率", "点击率", "版本", "迭代",
    "上线", "灰度", "复盘",
    "specifically", "for example", "e.g.", "data", "metric", "percent",
    "weeks", "months", "version", "users", "conversion", "iteration",
)
_DIGIT_PATTERN = re.compile(r"\d")

# Standalone capitalized English tokens (2+ letters) as a proxy for named
# tools/products/technologies (e.g. "Kafka", "Redis", "React", "AWS") --
# these are exactly the kind of concrete detail rubric 3.4 calls out under
# "工具/方法名称" that a fixed Chinese/English word list can never fully
# enumerate, since new tool names appear constantly. Deliberately excludes
# common English sentence-starters/pronouns that would otherwise fire on
# ordinary capitalization rather than a real proper noun.
#
# Uses lookaround on [A-Za-z] rather than \b: Python's \b treats any
# Unicode word character as a boundary participant, and CJK ideographs
# ARE \w in Unicode mode, so "用Kafka做" would have no \b between "用"
# and "K" at all and silently never match -- exactly the common case here
# (a tool name embedded directly in Chinese text with no surrounding
# spaces). Confirmed by direct regex testing during development; caught
# before it shipped as a not-actually-firing feature.
_PROPER_NOUN_PATTERN = re.compile(r"(?<![A-Za-z])[A-Z][a-zA-Z]{1,}(?![A-Za-z])")
_PROPER_NOUN_STOPWORDS = frozenset(
    {"I", "The", "This", "That", "We", "It", "They", "He", "She", "You", "My", "Our", "In", "For", "So", "But", "And"}
)


def _count_proper_noun_markers(text: str) -> int:
    """Count capitalized English tokens in `text` that look like a proper noun (tool/product
    name) rather than ordinary sentence-initial capitalization or a common pronoun."""
    return sum(1 for m in _PROPER_NOUN_PATTERN.finditer(text) if m.group(0) not in _PROPER_NOUN_STOPWORDS)


# Marker density (matches per sentence) at which the marker signal saturates to 1.0.
# Reasoned-but-unvalidated starting point for the widened marker list above --
# scripts/calibrate_specificity.py grid-searches this alongside
# _SPECIFICITY_MARKER_WEIGHT against the 150 human-reviewed records the same
# way decision #29 grid-searched _KEYWORD_SIMILARITY_THRESHOLD; the values
# below are placeholders pending that run (see decision #45).
_EXPECTED_MARKER_DENSITY = 0.5

_SPECIFICITY_MARKER_WEIGHT = 0.5
_SPECIFICITY_REF_WEIGHT = 0.5

# Rubric 3.4's 0-2 band is literally defined by "没有任何可验证的具体信息" (zero
# verifiable concrete detail) -- so zero detail markers must hard-cap the
# combined signal regardless of how semantically on-topic the answer reads
# (topical relevance to reference_points is not the same thing as
# concreteness; see decision 22's keyword-stuffing mechanism, which this
# cap exists to keep effective -- caught during development: an answer
# built entirely out of bare keyword-cluster terms had zero detail markers
# but still scored a mid-band specificity purely from reference-point
# similarity, which would have suppressed the stuffing warning).
_ZERO_MARKER_SIGNAL_CAP = 0.2


_MAX_SPECIFICITY_HIGHLIGHTS = 3


def _count_sentence_markers(sentence: str) -> int:
    """Per-sentence version of the digit/detail-marker count below, used only to pick which
    sentences to highlight (week 13) -- the whole-answer counts driving the actual score stay
    as they were, computed over `answer` directly."""
    digit_hits = len(_DIGIT_PATTERN.findall(sentence))
    lowered = sentence.lower()
    word_hits = sum(1 for w in _DETAIL_MARKER_WORDS if w in lowered)
    proper_noun_hits = _count_proper_noun_markers(sentence)
    return digit_hits + word_hits + proper_noun_hits


def _score_specificity(
    answer: str,
    sentences: list[str],
    sentence_embeddings: np.ndarray,
    reference_embeddings: np.ndarray,
) -> DimensionScore:
    if not sentences:
        return DimensionScore(score=1.0, explanation="回答为空，没有任何可验证的具体信息，对应0-2分档。")

    digit_hits = len(_DIGIT_PATTERN.findall(answer))
    lowered = answer.lower()
    word_hits = sum(1 for w in _DETAIL_MARKER_WORDS if w in lowered)
    proper_noun_hits = _count_proper_noun_markers(answer)
    marker_count = digit_hits + word_hits + proper_noun_hits
    marker_density = marker_count / len(sentences)
    marker_signal = min(marker_density / _EXPECTED_MARKER_DENSITY, 1.0)

    avg_ref_sim, ref_signal = _reference_point_signal(sentence_embeddings, reference_embeddings)

    combined = _SPECIFICITY_MARKER_WEIGHT * marker_signal + _SPECIFICITY_REF_WEIGHT * ref_signal
    if marker_count == 0:
        combined = min(combined, _ZERO_MARKER_SIGNAL_CAP)
    score, band = _ratio_to_band(combined)

    # Positive highlights on the top sentences by marker density (week 13) --
    # only sentences that actually contain a marker are eligible, so a
    # zero-detail answer correctly gets zero highlights here.
    per_sentence_counts = [_count_sentence_markers(s) for s in sentences]
    ranked_idx = sorted(range(len(sentences)), key=lambda i: per_sentence_counts[i], reverse=True)
    highlights = [
        Highlight(
            sentence_index=i,
            sentence_text=sentences[i],
            polarity="positive",
            reason=f"包含 {per_sentence_counts[i]} 处具体细节标记（数字/数据/具体用词）",
        )
        for i in ranked_idx[:_MAX_SPECIFICITY_HIGHLIGHTS]
        if per_sentence_counts[i] > 0
    ]

    explanation = (
        f"具体细节标记 {marker_count} 处（数字 {digit_hits} 处，细节用词 {word_hits} 处，"
        f"工具/产品专名 {proper_noun_hits} 处），"
        f"与参考要点的语义相似度 {avg_ref_sim:.2f}，综合对应{band}分档。"
    )
    return DimensionScore(score=score, explanation=explanation, highlights=highlights)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def score_answer_report(answer: str, question: Question) -> ScoreReport:
    """
    Score `answer` against `question` on all four rubric dimensions and
    return the structured ScoreReport (see backend/scoring/report.py),
    including the decision-22 protective mechanisms applied on top of the
    four raw dimension scores.
    """
    if not answer or not answer.strip():
        empty = DimensionScore(score=1.0, explanation="回答为空，无法评分，对应0-2分档。")
        return build_score_report(question, empty, empty, empty, empty)

    sentences = _split_sentences(answer)
    sentence_embeddings = embed_texts(sentences) if sentences else np.empty((0, 0), dtype=np.float32)
    reference_embeddings = (
        embed_texts(question.reference_points) if question.reference_points else np.empty((0, 0), dtype=np.float32)
    )

    structure_score = _score_structure_completeness(question.question_type, sentences, sentence_embeddings)
    keyword_score = _score_keyword_coverage(question, sentences, sentence_embeddings)
    logical_score = _score_logical_coherence(answer, sentences, sentence_embeddings, reference_embeddings)
    specificity_score = _score_specificity(answer, sentences, sentence_embeddings, reference_embeddings)

    return build_score_report(question, structure_score, keyword_score, logical_score, specificity_score)


def score_answer(answer: str, question: Question) -> dict:
    """score_answer_report(), flattened to a plain JSON-serializable dict (nested dataclasses included)."""
    return asdict(score_answer_report(answer, question))
