# ml/ 数据准备摘要（Week 7）

自动生成，来源：`ml/prepare_data.py`。此文件由 `prepare_data.py` 整体覆写，`split_data.py` 会在其后追加划分相关章节，不要手工编辑本文件靠上的部分。

## 1. 数据范围

- 来源文件：`data/labeled_answers_human_reviewed.json`
- 样本量：**150** 条（仅 batch1，question_id 命中 `data/sample_questions.json` 30道通用题的记录）
- **不包含** 当前文件里另外50条 batch2 behavioral 记录（来自 `data/question_bank.json` 7个领域题库）。原因见 `docs/decision_log.md` 条目30：数据源不同、题型分布会失衡（50/50/50 变成 100/50/50），本周不采用。
- **不使用** `data/question_bank.json`（200道题的RAG检索题库，与本实验无关）。

## 2. 标签构建

- 真实标签 = `human_scores.structure_completeness`（0-10浮点数），重新分档为 0-4 五档：0-2 / 3-4 / 5-6 / 7-8 / 9-10。
- 分档边界取相邻档位的中点（2.5 / 4.5 / 6.5 / 8.5）；边界值本身归入较高的一档（例如 2.5 归入 "3-4" 而非 "0-2"）。
- `question_type` 通过 `question_id` join `sample_questions.json` 的权威字段得到，不是从 `question_id` 前缀猜测的（batch1 全部能 join 成功）。

## 3. 一致性校验：重新分档 vs 原始 score_band

发现 **2** 条不一致记录（重新分档结果 ≠ 原始 `score_band` 字段）：符合预期（约2条）。

| review_id | structure_completeness 分数 | 重新分档 | 原始 score_band |
| --- | --- | --- | --- |
| behavioral_01__0-2 | 7.0 | 7-8 | 0-2 |
| behavioral_01__3-4 | 8.0 | 7-8 | 3-4 |

解读：这些记录的草稿是按某个目标档位生成的（`score_band` 字段记录的是草稿的目标档），但人工复核给出的 `structure_completeness` 实际分数落在了另一档——说明人工评分与草稿设计目标不一致，是人工复核阶段的真实判断，本脚本以人工分数重新分档后的结果为准，不回退去用原始 `score_band`。

**运行本脚本时须人工确认以上不一致记录后才会继续**（交互式 `input()` 确认，或显式传 `--yes` 跳过——`--yes` 仅用于已经人工确认过一次之后的自动化重跑，不代表跳过校验本身）。

## 4. 题型分布

| 题型 | 数量 |
| --- | --- |
| behavioral | 50 |
| case_analysis | 50 |
| technical | 50 |

## 5. 档位分布

| 档位 | 数量 |
| --- | --- |
| 0-2 | 29 |
| 3-4 | 29 |
| 5-6 | 30 |
| 7-8 | 32 |
| 9-10 | 30 |

## 6. 题型 × 档位 联合分布

| 题型 \ 档位 | 0-2 | 3-4 | 5-6 | 7-8 | 9-10 |
| --- | --- | --- | --- | --- | --- |
| behavioral | 9 | 9 | 10 | 12 | 10 |
| case_analysis | 10 | 10 | 10 | 10 | 10 |
| technical | 10 | 10 | 10 | 10 | 10 |

## 7. answer_text 长度分布（字符数）

- min: 15
- max: 543
- mean: 164.5
- median: 118.5
- stdev: 146.0

## 8. 语言范围

150条 `answer_text` 全部为中文（逐条检查中文字符占比 ≥ 30%，实际全部远高于此阈值）。**本次实验范围限定中文**，未覆盖英文或中英混合作答场景，模型/特征工程若涉及分词或语言相关假设，需注意这一限制。

## 9. 产出文件

- `ml/data/prepared_samples.json`：150条样本，字段见脚本内`build_samples()`（id / question_id / question_type / answer_text / answer_length / structure_completeness_score / original_score_band / band_label(0-4) / band_range）。
<!-- SPLIT_SECTION_START -->

## 10. 数据划分（ml/split_data.py）

- N=150 < 200，主评估方式：5折分层交叉验证；另留出约14%作为封存test集合，全程不参与调参。
- 随机种子固定为 42。
- 实际采用的分层策略：题型×档位联合分层（15个格子，每格样本量足够支撑test+5折）
- 划分结果落盘于 `ml/splits/fold_0.json` ... `ml/splits/fold_4.json`（每折存 train_ids/val_ids）与 `ml/splits/test.json`（存 test_ids）。字段是样本的 `id`（即 review_id），后续Colab训练直接加载这份划分，不重新划分。

### 划分质量检查清单

- test集合与CV pool不重叠：通过
- test集合∪CV pool == 全部150条：通过
- 每折内 train/val 不重叠且并集等于CV pool：通过
- 5折val集合两两不重叠、并集覆盖整个CV pool（每个样本恰好在1折的val中）：通过
- 各折val集合大小：[26, 26, 26, 25, 25]（最大最小差 1，通过（差≤1））
- test集合占比：22/150 = 14.7%（落在10-15%目标区间内）

**每折 val 集合的题型覆盖（人工核查用）：**

| fold | behavioral | case_analysis | technical | val总数 |
| --- | --- | --- | --- | --- |
| 0 | 9 | 9 | 8 | 26 |
| 1 | 10 | 7 | 9 | 26 |
| 2 | 10 | 8 | 8 | 26 |
| 3 | 7 | 9 | 9 | 25 |
| 4 | 7 | 9 | 9 | 25 |

- 每折val集合是否覆盖全部题型：通过

**每折 val 集合的档位覆盖：**

| fold | 0-2 | 3-4 | 5-6 | 7-8 | 9-10 | val总数 |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 6 | 5 | 5 | 5 | 5 | 26 |
| 1 | 5 | 5 | 5 | 5 | 6 | 26 |
| 2 | 6 | 5 | 4 | 5 | 6 | 26 |
| 3 | 4 | 5 | 6 | 6 | 4 | 25 |
| 4 | 4 | 5 | 6 | 6 | 4 | 25 |

- 每折val集合是否覆盖全部档位：通过

**test集合的题型 / 档位分布 vs 整体150条：**

| 题型 | test数量 | test占比 | 整体占比 |
| --- | --- | --- | --- |
| behavioral | 7 | 31.8% | 33.3% |
| case_analysis | 8 | 36.4% | 33.3% |
| technical | 7 | 31.8% | 33.3% |

| 档位 | test数量 | test占比 | 整体占比 |
| --- | --- | --- | --- |
| 0-2 | 4 | 18.2% | 19.3% |
| 3-4 | 4 | 18.2% | 19.3% |
| 5-6 | 4 | 18.2% | 20.0% |
| 7-8 | 5 | 22.7% | 21.3% |
| 9-10 | 5 | 22.7% | 20.0% |

- 固定随机种子（42）复现性检查（重跑一次划分逻辑对比结果）：通过，结果完全一致
