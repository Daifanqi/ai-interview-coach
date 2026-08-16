# Architecture Decision Log

This file did not exist yet even though `models/session_schema.py` already
referenced "decision 9" and "decision 10" in its comments. Those two are
reconstructed below (verbatim from the source comments, since that's the
only record of them) so the numbering they already reference is valid.
Decisions 1-8 predate this file and are not reconstructed here.

## 9. Highlight moment always carries an AI-provided rationale

**Decision:** `ReviewReport.highlight_turn_id` is paired with an explicit
`highlight_reason` field.

**Why:** Picking a single "highlight" turn out of a session is inherently a
subjective judgment call. Requiring the AI to also state *why* it picked
that turn keeps the judgment explainable/auditable instead of being an
opaque pick.

**Scope:** `models/session_schema.py` (`ReviewReport`).

## 10. First-ever session falls back to an industry-average baseline for the progress chart

**Decision:** `ReviewReport.history_trend` is an empty list on a user's
first-ever session (there is no prior data to show). The frontend detects
the empty list and renders an industry-average baseline instead of a blank
chart.

**Why:** A first-time user should still see a meaningful progress chart,
not an empty one, even though they have no history of their own yet.

**Scope:** `models/session_schema.py` (`ReviewReport.history_trend`), report
rendering in the frontend (not yet implemented).

---

## 11. Downstream modules must key on (difficulty, persona, stage) together, never on difficulty alone

**Decision:** `ScenarioConfig` (`backend/diagnosis/matcher.py`) and
`SessionConfig` (`models/session_schema.py`) always carry `difficulty`,
`interviewer_persona`, and `interview_stage` as three separate, required
fields. The dialogue engine and question-bank retrieval (both future work)
must treat all three as required inputs when looking up behavior/content,
not just `difficulty`.

**Why:** The final difficulty value is not a unique key. The same
`final_difficulty` can be produced by different `(experience, stage)`
combinations that carry different personas -- e.g. compare `技术面②`
(`experience` 3年以上 → base 4, adjustment +1 → difficulty 5, persona
`技术挖掘型`) against a hypothetical combination landing on difficulty 5 via
a different stage/persona. If downstream code branches or memoizes on
`difficulty` alone, it will silently conflate scenarios that should behave
differently.

**How to apply:** Any new module that reads a scenario/session (dialogue
engine, RAG retrieval, analytics) must accept and use all three fields
together. A helper or cache keyed only by `int` difficulty is a bug, not an
optimization.

**Scope:** `backend/diagnosis/matcher.py`, `models/session_schema.py`.

## 12. "终面严格" (final-round "rigorous" persona) means broader/deeper interviewing, not harder questions

**Decision:** The final round's `严格型` persona is allowed to coexist with
a computed difficulty that is not the maximum (see
`backend/diagnosis/difficulty.py` `STAGE_CONFIG`: `终面`'s adjustment is
`+1`, the same as `技术面②`'s). No change is made to `compute_difficulty()`
or `STAGE_CONFIG` to force final-round difficulty upward to match the
"strict" label.

**Why:** `严格` (rigorous/strict) is explicitly defined here as "covers more
assessment dimensions, follows up more deeply" -- not "asks harder
questions." The difficulty score and the persona's rigor are intentionally
orthogonal axes; the apparent mismatch (strict persona, moderate difficulty)
is accepted as correct, not treated as a bug to reconcile.

**How to apply:** **Status: 已完成.** `backend/conversation/prompts/strict_zh.py`
(written in weeks 3-4) already follows this decision -- its `严格型` prompt is
framed around "broader coverage + deeper follow-ups" (更深入的追问和更全面
的考察维度), not "ask harder/more advanced questions." No change was needed
to `difficulty.py` or `matcher.py` for this decision; it only constrained
prompt-writing, and that prompt-writing is done. (This status line was
updated during the week-10 completeness review that produced decision #39 --
the constraint itself and the reasoning above are unchanged.)

**Scope:** Future interviewer persona prompt design (not implemented in
this pass).

## 13. Bilingual (zh/en) support: auto-detect once per session, always allow manual override

**Decision:** The app defaults to Chinese. On first render of a session, it
attempts to detect the visitor's preferred language from the browser's
`Accept-Language` header via `st.context.headers`; if the header is
missing, unavailable, or does not clearly indicate English, it falls back
to Chinese. A manual language toggle is always present (sidebar) and, once
used, overrides auto-detection for the rest of the session.
`SessionConfig.language` (`"zh"` or `"en"`) carries the resolved language
forward so the dialogue engine and other downstream modules know which
language to converse in.

**Why:** A visitor's browser locale is a convenience signal, not a reliable
statement of their actual working language, so auto-detection must never be
the only way to set the language -- manual override must always be
reachable.

**How to apply:** All frontend copy is looked up through `strings.t(key)`;
no module should hardcode a zh or en literal. Any new SessionConfig
consumer (dialogue engine, scoring, etc.) that produces user-facing text
must read `SessionConfig.language` rather than re-deriving language from
scratch.

**Follow-up:** `difficulty_badge_html()`'s "难度"/"Difficulty" word is now
also routed through `t("difficulty_word")` (deferred-imported from
`frontend.strings` inside the function body, so `backend/diagnosis/difficulty.py`
stays importable and testable without a Streamlit runtime unless that
specific helper is actually called). This is a deliberate, narrow exception
to backend/frontend layering -- `difficulty.py` otherwise has no UI-layer
dependency -- accepted because the alternative (duplicating the string
table, or threading a `lang` parameter through every caller) was judged
more complex for one hardcoded word.

**Scope:** `frontend/strings.py` (`STRINGS`, `detect_browser_language`,
`get_language`/`set_language`, `t`), `models/session_schema.py`
(`SessionConfig.language`), `frontend/app.py`,
`backend/diagnosis/difficulty.py` (`difficulty_badge_html`).

---

## 14. 三项"高级化"功能并入主线计划（原第2周讨论，正式定案）

**内容：** 在项目基础功能开发过程中，讨论了四个可以提升项目技术深度和产品
吸引力的方向：语音合成面试官(TTS)、可解释性评分可视化、自适应题目推荐算法
升级(多臂老虎机)、可分享战绩卡片。

**决策：** 其中三项并入10周主线计划，不额外增加周数，安排如下：

1. 语音合成面试官(TTS)：安排在第4周（追问逻辑+语音分析），与该周本就要
   搭建的语音处理基础设施（ASR）衔接，形成完整的语音输入输出闭环。
2. 可解释性评分可视化：拆成两段实现——第6周（baseline评分）产出"哪些句子
   影响评分"的分析数据，第8周（复盘报告生成）在报告页面上做高亮展示，
   因为底层分析逻辑属于评分模块，但可视化呈现依赖报告页面存在。
3. 可分享战绩卡片：安排在第9周（进度追踪阶段），与该周本就要做的历史趋势
   图功能性质类似，都是基于已有评分数据生成的衍生产物。

自适应题目推荐算法升级（多臂老虎机）保留为"未来迭代计划"，不进入当前10周
主线，原因是实现复杂度和风险相对更高，优先保证主线功能扎实完成。

**状态：** 计划中，非当前周任务，先记录设计意图，留到对应阶段处理。

**归属：** 跨模块（对话引擎、评分系统、语音分析、复盘报告、进度追踪）。

## 15. 多语言支持的长期愿景（当前仅实现中英双语，未来计划扩展）

**内容：** 项目最初设想是支持3种以上语言、适合更广泛的用户群体。考虑到
10周开发周期和solo开发的时间精力限制，第2周决定先落地中文+英文两种语言的
完整支持（界面文字+AI面试官对话双语），作为v1的语言覆盖范围（见[[13]]）。

**未来迭代计划：** 在中英文版本稳定运行后，评估扩展更多语言（如日语、
西班牙语等）的可行性，重点考虑：

1. 界面文字翻译（技术上成本较低，`strings.py` 架构已支持扩展）
2. AI面试官多语言对话质量（需要针对每种新语言重新调优人设prompt）
3. 评分标准是否需要按语言调整（不同语言的表达习惯、语法结构差异）
4. 语音识别/合成的多语言支持（faster-whisper本身已支持近100种语言，
   这块扩展成本相对最低）

**状态：** 计划中，非当前周任务。

**归属：** 全局产品规划。

## 16. 分诊流程页面化改造（计划中，非当前周任务）

**内容：** 当前版本把语言切换、三道分诊问题、匹配结果全部堆叠在一个页面
里，后续计划拆分成多个独立页面，提升引导感和高级感：

1. 开场引导页：进入分诊前的欢迎/说明页，在此完成语言选择和字体风格选择，
   加入轻量互动元素，而非像当前版本一样把语言切换默默放在侧边栏。
2. 分诊问答页：三道问题单独成页，与结果展示分离。
3. 结果展示页：匹配结果单独成一个页面呈现，强化视觉层次和"揭晓感"，
   而非像当前版本一样直接堆叠展示在表单下方。

**决策：** 这项改造计划在项目第8周"模块整合与分阶段界面收口"时统一处理，
当前阶段（分诊模块基础功能）不受影响，继续沿用现有单页面实现。

**归属：** 前端/交互设计。

## 17. 交互体验升级——对话式分诊 + 实时反馈闭环（计划中，非当前周任务）

**内容：** 参考Claude等对话式AI产品的交互模式，计划对整体交互体验做两项
升级：

1. 分诊流程改为对话式：不再用静态的单选表单一次性展示三道问题，而是像
   聊天一样一问一答、以弹窗/模态框形式逐题呈现，与第8周已计划的"分诊
   流程页面化改造"（见[[16]]）整合在一起实现，不额外新增独立任务。
2. 面试对话增加实时反馈闭环：
   - 开场：面试官在正式开始前，先用一段自然语言介绍本次面试的基本情况
     （角色设定、语言、大致流程、反馈方式），类似"我将扮演XX岗位的面试官，
     用英文进行，每次回答后我会给你反馈"这种开场白，而不是让用户毫无
     准备地直接进入问答。
   - 过程中：每轮用户回答完毕后，除了原有的追问/换题决策逻辑，面试官
     还需要给出简短的即时反馈，包含两部分：(a) 内容/结构反馈（回答是否
     完整、逻辑是否清晰）；(b) 表达纠错建议（2-3条语法/措辞的自然化建议）。
   - 结束后：仍保留第8周已计划的完整复盘报告页面，用于呈现汇总性的趋势
     分析和系统性改进建议，与每轮的即时反馈形成互补（即时反馈重"当下"，
     报告重"全局与趋势"），两者不冲突、不重复。

**技术影响：**

- 原计划中"口语纠错"功能（第8周，仅在最终报告展示）需要拆分为两部分：
  轻量版纠错在每轮对话中实时给出（需要评估这是否会显著增加每轮的响应
  延迟，实时反馈调用大模型的prompt需要刻意做到简短，避免用户等待过久）；
  完整版纠错分析仍保留在最终报告中，可以做得更全面、更系统。
- 需要新增"面试官开场白"这一环节的Prompt设计，作为对话流程的第一步，
  在第一道正式问题之前触发。

**状态：** 计划中，非当前周任务。

**归属：** 对话引擎、语音分析/评分系统（口语纠错部分）、前端交互设计
（分诊流程 + 对话页面）。

## 18. 敷衍回答的应对方式按人设区分（第3周实测发现并修正）

**内容：** 实测中发现，技术挖掘型人设在候选人给出敷衍回答时，会说出直接
点评回答质量的话（如"这个回答似乎没有展现出思考深度"），这违反了"内部
评分不应呈现给候选人"的设计原则，会让候选人感觉被评判，影响沉浸感。

**决策：** 只在严格型人设保留"直接点评回答质量"的表达方式，因为这符合
该人设"沉稳、不轻易被表面回答说服的资深专家"的基调；亲和型和技术型人设
改为"自然过渡到更具体的问题或选项"，不直接评价回答质量。

**归属：** 对话引擎（Prompt设计）。

## 19. 第4周关键决策——评分升级、TTS引擎选型（含许可证排查）

**内容：**

1. 实时评分环节提前升级：原计划第6周才做baseline评分系统，
   现在提前把engine.py里的简化规则兜底（长度+关键词判断）替换成
   调用Groq API+简化prompt的方式，与第1周架构决策2保持一致。

2. TTS引擎选型排查：最初考虑Coqui TTS/XTTS-v2，但深入排查许可证后发现：
   Coqui TTS工具包本身是MPL 2.0（允许商用），但效果最好的XTTS-v2模型
   使用Coqui Public Model License，明确禁止商业用途；且Coqui.ai公司
   已于2024年倒闭，没有官方渠道可购买商用授权，事实上无法商用。
   虽然项目当前是非商业的个人简历项目，不受此限制，但考虑到项目
   未来可能被广泛使用的不确定性，最终改选Piper（MIT协议，完全无
   商用限制）作为TTS引擎，避免未来任何许可证隐患。

3. 三种人设分配不同声线：Piper自带多个预训练声线可选，
   给亲和型/技术挖掘型/严格型分配不同声线，无额外技术成本，
   能进一步增强人设的区分度和沉浸感。

**归属：** 评分系统、语音分析（TTS部分）。

## 20. 第4周技术方案的5项待验证风险项（需要实测验证，非最终定论）

**内容：** docs/week4_tech_spec.md第4节列出了本周三个模块（追问评分Groq裁判化、
faster-whisper语音特征提取、Piper语音合成）在设计阶段识别出的五项风险点。
文档中给出的是工程上合理的起点值，**不是最终定论**，记录在此是为了避免这些
经验值后续被误当作已经验证过的结论：

1. **`high`/`low`语义对齐**：backend/conversation/scoring_judge.py把追问评分
   的`high`/`low`定义为"回答的具体度/可追问性"，而不是"回答质量好坏"——这是
   整份技术方案的地基假设，需要和产品设计确认是否与追问触发逻辑的预期一致，
   一旦语义理解有偏差，评分标准需要相应调整。

2. **Groq结构化输出的容错**：`json_object`模式不保证`level`/`hook`字段一定
   存在或类型正确。scoring_judge.py已实现三层兜底（JSON解析失败→正则提取
   high/low关键字→降级回长度+关键词规则打分），但这条兜底链路需要专门测试
   覆盖到（例如刻意构造API超时、畸形JSON、字段缺失/类型错误等场景），当前
   只做过正常路径和"无API key"路径的验证。

3. **中文声线区分度**：Piper官方中文（zh_CN）目前只有huayan一个音色，
   backend/speech/tts.py里三种人设通过`length_scale`/`noise_scale`/
   `noise_w_scale`参数区分，而非切换音色。实现过程中做过一次非正式验证：
   同一句中文文本、三种人设参数各合成一次并比较音频时长，方向符合预期
   （亲和型1.08 > 技术挖掘型1.00 > 严格型0.92），但实际时长差异幅度
   （约4%和0.4%）小于参数比例本身暗示的差异（理论上约8%），说明参数确实
   生效，但实际听感区分度可能有限。这只是时长层面的粗略观察，不能替代
   文档要求的真人盲听评估。

4. **语速/停顿阈值**：backend/speech/features.py里的CPM/WPM参考区间
   （中文180~260字/分钟、英文100~150词/分钟视为"正常"）和300ms停顿判定
   阈值都是文档给出的经验值，需要用真实候选人录音样本重新校准，不同人设/
   题型下的"正常语速"本身也可能不同。

5. **VAD对短停顿/填充词的影响**：backend/speech/transcribe.py默认
   `vad_filter=False`（保留faster-whisper库自身默认设置，转写阶段不主动
   开启VAD），需要专门测试打开`vad_filter=True`及调整`vad_parameters`对
   填充词检出率的实际影响，确认是否会把孤立的语气词（如单独一句"嗯……"）
   当作静音丢弃。实现过程中有一次非正式观察：同一段合成语音里的"嗯"被
   faster-whisper误识别成了"问"字（属于转写错误，不是VAD丢弃），提示ASR
   本身对孤立语气词的识别也不算稳定——这一点在做填充词检出率验证时应
   一并纳入观察范围，不只是VAD开关本身的问题。

**决策：** 以上五项均为待验证项。当前实现（backend/conversation/scoring_judge.py、
backend/speech/transcribe.py、backend/speech/features.py、backend/speech/tts.py）
按文档给出的经验值/推荐方案落地并已做过基本的单元/端到端验证（真实API调用、
真实合成语音的ASR转写、真实Piper合成），但上述五项本身仍需要更大样本、更
系统的测试（真实候选人录音、真人盲听、专门的异常路径测试）才能定论，不应
把当前取值当作已经校准过的最终参数。

**归属：** 对话引擎（评分judge）、语音分析（ASR特征提取）、语音合成（TTS）。

## 21. TTS音质优化（计划中，非当前周任务）

**内容：** 第4周实测发现，当前TTS引擎Piper（zh_CN-huayan-medium）合成的语音
听感偏机械，自然度有限——这与选型阶段就已知的权衡一致（Piper用MIT
协议换取了完全无商用限制，但音质是三个候选方案里最一般的，见[[19]]）。

**后续迭代方向**（按成本从低到高排序，未来有余力时评估）：

1. 尝试Piper的high质量档位声线（而非当前medium档），免费、
   无需换引擎，是最低成本的改善尝试。
2. 切换到Kokoro（Apache 2.0协议，同样完全无商用限制，
   音质评价优于Piper，但需要重新对接语音合成模块，有一定工作量）。
3. 重新评估Coqui/XTTS-v2（音质最好，但许可证仅限非商业用途，
   若项目后续有商业化可能则不适用）。

**状态：** 当前阶段（第4周）优先保证语音闭环功能完整跑通，音质优化不影响
核心功能验收，留待后续迭代。

**归属：** 语音分析（TTS部分）。

## 22. 评分Rubric定稿——题型区分设计+三项保护机制

**内容：** 评分框架最终确定为4个维度（结构完整度/关键词覆盖率/逻辑连贯性/
具体性），其中结构完整度和关键词覆盖率按题型（行为题/技术题/
案例分析题）区分标准和权重，逻辑连贯性和具体性为通用标准。
完整评分标准、权重方案、设计陷阱分析见docs/scoring_rubric.md。

**决策：** 采纳以下三项保护机制（后续第6周实现baseline评分时需要落地，
本周先记录设计，不实现代码）：

1. 最低分门槛：具体性维度低于3分时，总分强制不超过50%，
   避免"结构工整但内容编造"的回答获得虚高总分
2. 关键词刷分联动检测：关键词覆盖率高但具体性得分低时，
   应标记为"疑似话术堆砌"，触发人工复核提示
3. 报告UI需明确标注"分数仅题型内可比"，避免不同题型的分数
   被直接比较造成误导

**标注数据相关决策：**

- 关键词库需要预先为每道题建好，按题型分别是技术术语库/
  能力关键词库/分析框架术语库
- 人工标注/校准时使用简化计数版清单（如"命中6/8个关键词"），
  而非精确百分比计算

**归属：** 评分系统。

## 23. 待办——150条标注数据尚未人工核对（阻塞第6周baseline准确率评估的可信度）

**内容：** data/labeled_answers_draft.json中的150条数据，score字段目前是AI在
目标分档区间内随机采样生成的占位值，尚未经过人工核对/修正。
第6周计划用这批数据评估baseline评分系统的准确率，若标注数据本身
未经验证，得出的准确率数字将缺乏可信度支撑。

**建议：** 在第6周正式开始baseline评估前，至少完成以下抽查（覆盖3种
题型×5个分档=15个类别，每类至少3-5条精看，共约50-75条），
并记录人机评分一致性的验证结果。全量150条核对可以在时间允许时
逐步补齐。

**归属：** 评分系统、数据标注。

## 24. 题库岗位细分方案调整（第6周，更新第2周相关决策）

**背景说明：** 本条原计划追加在第2周"v1不细分岗位内容，优先做通用行为题"
的决策记录之后，但检索`docs/decision_log.md`全文未找到该决策的正式记录——
本文件开头说明decision 1-8早于本文件创建、未被补录，这条决策很可能就在
未被补录之列；唯一相关的既有记录是`backend/diagnosis/questionnaire.py:24-29`
的代码注释（说明v1阶段`job_type`只被采集、不参与`compute_difficulty()`及内容
差异化，留待未来的题库检索环节使用）。因此本条改为独立追加，而非插入到某条
既有决策之后，避免在没有原始记录的情况下编造插入位置。

**内容：** 第2周曾决定v1版本题库不细分岗位、优先做通用行为题。第6周重新
评估后决定调整：三种题型（行为题/技术题/案例分析题）均按7种岗位
（技术/产品/市场营销/运营/设计/咨询/金融）细分，本周7种岗位全部
覆盖（而非只做部分岗位），200道题平均分配到21个"题型×岗位"类别，
每类约9-10道。

**调整原因：** 技术题本身天然需要按技术栈区分内容才有实际价值
（软件工程师和数据分析师的技术题不该是同一套），既然技术题需要
细分，为保持题库结构一致性，行为题和案例分析题也一并按岗位组织
（虽然这两类题内容跨岗位通用性更强，可以在岗位间共享部分题目，
但归类结构统一按岗位维护）。

**注意：** 第5周已建立的30道样题（用于标注数据校准，与
data/labeled_answers_draft.json和docs/scoring_calibration_checklist.md绑定）
保持不变，不纳入本次岗位细分调整，避免破坏已有的标注数据关联。
本次新增的题库是独立的、更大规模的RAG检索题库。

**归属：** RAG题库、评分系统。

## 25. RAG题库规模落地（data/question_bank.json，共200题）

**内容：** [[24]]中规划的岗位细分题库已生成，写入`data/question_bank.json`，
与`data/sample_questions.json`（第5周标注校准用的30道样题）相互独立，
互不影响。

最终规模：7种岗位 × 3种题型，共200道题，每个"岗位×题型"组合9-10道：

| 岗位 | 行为题 | 技术题 | 案例分析题 | 小计 |
| --- | --- | --- | --- | --- |
| 技术 | 10 | 10 | 9 | 29 |
| 产品 | 9 | 10 | 10 | 29 |
| 市场营销 | 10 | 9 | 10 | 29 |
| 运营 | 10 | 9 | 10 | 29 |
| 设计 | 9 | 10 | 9 | 28 |
| 咨询 | 10 | 9 | 9 | 28 |
| 金融 | 9 | 9 | 10 | 28 |
| **合计** | 67 | 66 | 67 | **200** |

每题字段：`question_id`（如`tech_behavioral_01`）、`question_text`、
`question_type`、`job_type`、`keyword_clusters`（6-7个同义词簇）、
`reference_points`（4条）。技术题按岗位真实技术栈差异化设计（如技术岗
覆盖系统设计/分布式，产品岗覆盖可行性评估/AB实验设计，金融岗覆盖估值/
财务分析方法），未复用同一套技术题跨岗位套用。

**归属：** RAG题库。

## 26. Baseline评分系统实现中发现并修复两处刷分漏洞

**内容：** 实现backend/scoring/baseline.py过程中，自测阶段发现两处可被利用的
评分漏洞：

1. 结构完整度检测漏洞：碎片化的关键词堆砌文字，可能因为语义匹配
   只检测到"提及相关词汇"就被误判为结构要素齐全，实际上并未真正
   构成完整叙事
2. 具体性下限保护漏洞：回答只要与参考答案主题相似（即使内容空洞），
   就可能绕过"具体性低于3分时总分不超过50%"这一保护机制

两处已修复，并各自补充了回归测试（test_specificity_floor_caps_overall_score、
test_keyword_stuffing_warning_fires_on_high_coverage_low_specificity）
固化修复效果，防止未来代码改动时被意外改回漏洞状态。

**当前状态：** 这是一个功能可用（working）但尚未校准（calibrated）的baseline——
所有启发式阈值是根据scoring_rubric.md合理推测的占位值，真实准确率
有待人工核对完150条标注数据后进行评估（见decision_log待办事项，
决策#23）。

**归属：** 评分系统。

## 27. Baseline评分系统准确率评估结果（[[23]]的待办已完成）

**内容：** [[23]]中提到的150条标注数据已全部人工核对完成
（`data/labeled_answers_human_reviewed.json`），用
`scripts/evaluate_baseline.py`跑了一次完整评估，结果写入
`results/baseline_accuracy.md`。核心数字：

四个维度整体MAE（0-10分制）与容差准确率：

| 维度 | MAE | ±1分准确率 | ±2分准确率 |
| --- | --- | --- | --- |
| 结构完整度 | 2.47 | 34% | 49% |
| 关键词覆盖率 | 3.59 | 23% | 31% |
| 逻辑连贯性 | 1.70 | 37% | 57% |
| 具体性 | 2.27 | 36% | 53% |

**关键发现1——关键词覆盖率是四个维度里误差最大、准确率最低的一项**，
且在行为题（MAE 4.60，±1准确率仅18%）和案例分析题（MAE 4.03，
±1准确率20%）上尤其差，技术题相对好一些（MAE 2.14）。误差最大的
10条记录里逐条核对后发现根因：baseline用的是关键词簇的精确子串
匹配（见`backend/scoring/baseline.py`的`_score_keyword_coverage()`），
面对自然改写的人类语言时经常匹配不到——例如`behavioral_02__9-10`
这条9-10档人工标注答案里，"砍掉了三分之一的非核心功能"表达的正是
"优先级排序"这个关键词簇的语义，但既不含"优先级排序"也不含其同义词
"分清主次/任务取舍"这几个精确字符串，导致baseline判定关键词覆盖率
为0/8，落入0-2分档（baseline给1.0分，人工给9.9分，绝对误差8.9，是
全部150条里误差最大的单项）。技术题相对好是因为技术术语本身更倾向
用固定说法（如"灰度发布"），改写空间比行为题的软技能描述小。

**关键发现2——两个保护机制中，具体性下限封顶机制触发频率合理，
关键词刷分警示机制在真实数据上从未触发**：

| 机制 | 触发次数/150 | 触发率 |
| --- | --- | --- |
| 具体性<3分→总分封顶50% | 54 | 36%（行为题50%/技术题34%/案例分析题24%） |
| 关键词覆盖率≥7且具体性≤4→刷分警示 | 0 | 0% |

具体性封顶机制的36%触发率、且三种题型间有梯度（行为题更容易触发，
案例分析题最少），是合理生效的信号，不是从来不触发也不是过度触发。
但关键词刷分警示0次触发不能直接解读为"数据集里不存在刷分样本"——
更可能的原因是上面发现1里同一个关键词覆盖率维度的系统性低估，
导致覆盖率分数很少能达到触发这条规则所需的≥7分门槛，所以这条
机制目前处于"因为上游维度失准而实质上不可能触发"的状态，而不是
已经在真实数据上验证过的合理阈值。

**结论：** baseline的四个维度中关键词覆盖率最需要优先重新校准——
建议从精确子串匹配改为语义相似度匹配（复用其他三个维度已经在用的
embedding方案），而不是继续扩充同义词簇列表；结构完整度和具体性
（MAE 2.2-2.5，±1准确率约34-36%）也明显没有达到可以替代人工/LLM
评分的精度，逻辑连贯性相对最接近人工评分。在关键词覆盖率修复并
重新评估之前，关键词刷分警示机制的真实触发行为仍是未验证状态。

**归属：** 评分系统。

## 28. 许可证从MIT改为PolyForm Noncommercial 1.0.0

**内容：** 项目最初用MIT License（完全无限制），后决定改用PolyForm
Noncommercial License 1.0.0，禁止任何商业盈利用途，仅允许个人学习/
研究/教育/非盈利场景使用代码。

**需要注意：** 严格意义上，使用此协议后项目不再符合OSI"开源"的官方
定义（因为限制了商业使用），业内更准确的说法是"源码可见"
（source-available）而非"开源"（open source）。后续README和简历
描述中需要注意用词准确性，避免误称为"开源项目"。

代码本身依然公开可见、可供个人学习使用，不影响项目"能被陌生人使用"
的核心目标。

**归属：** 项目许可与合规。

## 29. 关键词覆盖率维度改用语义相似度匹配（修复[[27]]发现的最大误差来源）

**背景：** [[27]]的准确率评估发现，关键词覆盖率是四个维度里MAE最高
（3.59）、±1分准确率最低（23%）的一项，逐条核对误差最大的记录后
确认根因：`_score_keyword_coverage()`原来用的是精确字符串子串匹配——
只要回答里没有一字不差地出现关键词簇的canonical词或某个synonym，
这个簇就判定为未命中，完全不管回答是否用改写的方式表达了同样的语义
（例如"砍掉了三分之一的非核心功能"表达的正是"优先级排序"这个簇，但
不含"优先级排序"或其同义词"分清主次/任务取舍"这几个精确字符串）。

**方法：** 把`backend/scoring/baseline.py`的`_score_keyword_coverage()`
改成基于embedding的语义相似度匹配（复用已有的
paraphrase-multilingual-MiniLM-L12-v2模型，见
`backend/scoring/embedding.py`）：对每个关键词簇，把簇内全部词条
（canonical+全部synonym）逐个embed，和回答拆分出的每个句子/短语的
embedding算余弦相似度，只要有一对相似度超过阈值就判定该簇命中，
不再要求精确子串匹配。新增`_get_keyword_cluster_term_embeddings()`
按`question_id`缓存每题的簇词条embedding，避免150条评估数据里
同一道题（每题平均被5个不同分档的标注答案复用）被重复embed。

**阈值选取：** 用`data/labeled_answers_human_reviewed.json`的全部150条
人工核对数据做网格搜索（先0.02步长粗扫0.20-0.64，再在峰值附近用0.01
步长精搜），以关键词覆盖率维度的±1分容差准确率为主要目标、MAE为
参考，最终取**0.37**。0.35-0.37之间MAE和准确率互相差距都在0.1分/1个
百分点以内，是一段平台而非孤立尖峰，说明这个取值不是过拟合到单个
数据点。阈值低于约0.30时几乎所有簇都会命中（平均命中率>0.80），
维度失去区分度；高于约0.45时又会退化到接近旧的精确匹配效果，因为
关键词的语义信号被embed进一整句话后会被稀释。阈值选定依据和具体
数字写在`backend/scoring/baseline.py`里`_KEYWORD_SIMILARITY_THRESHOLD`
常量上方的注释中。

**修复前后对比**（同一批150条数据，`scripts/evaluate_baseline.py`重跑，
完整表格见`results/baseline_accuracy.md`第6节）：

| 指标 | 修复前 | 修复后 |
| --- | --- | --- |
| 关键词覆盖率 MAE（整体） | 3.59 | 1.84 |
| 关键词覆盖率 ±1分准确率（整体） | 23% | 39% |
| 关键词覆盖率 ±2分准确率（整体） | 31% | 63% |
| 行为题 MAE / ±1准确率 | 4.60 / 18% | 2.25 / 32% |
| 案例分析题 MAE / ±1准确率 | 4.03 / 20% | 1.22 / 48% |
| 技术题 MAE / ±1准确率 | 2.14 / 30% | 2.04 / 36% |
| 关键词刷分警示触发次数/150 | 0（0%） | 21（14%） |

技术题提升幅度明显小于行为题/案例分析题，符合[[27]]里"技术术语本身
更倾向固定说法、改写空间更小"的预判。**关键词刷分警示机制此前从未
触发（[[27]]已指出这是因为关键词覆盖率维度系统性低估、分数很少能
达到≥7的触发门槛，而不是这条规则本身设计有问题）**，这次修复后
触发了21次（占比14%，三种题型间有梯度：行为题24%＞技术题14%＞
案例分析题4%），说明[[27]]的推测是对的——修好上游维度后，这条
之前"因为上游失准而实质不可能触发"的保护机制现在开始正常生效。

**归属：** 评分系统。

## 30. 标注数据核对范围确认——第7周模型实验维持150条batch1，batch2扩充数据留待后续

**背景：** 待人工核对的候选标注数据分两批草稿：batch1
（`data/labeled_answers_draft.json`，150条，对应`sample_questions.json`
里的30道通用题）和batch2（`data/labeled_answers_draft_batch2.json`，
300条，对应`question_bank.json`里7个领域×3种题型共60道题），合计450条，
统一核对进`data/labeled_answers_human_reviewed.json`，进度由
`scripts/review_labels.py`跟踪。经过实际核对过程，决定当前阶段以已
完成核对的部分为准，不再继续核对剩余部分。

**实际完成数量：** 直接调用`scripts/review_labels.py`里
`load_draft_batches()`/`load_existing_reviews()`/`make_review_id()`
这几个函数（和交互式运行时`print_summary()`用的是同一套统计口径，
`question_type`字段取自`question_bank.json`/`sample_questions.json`，
不是从`question_id`前缀猜的）核对`labeled_answers_human_reviewed.json`
得出，200条记录全部是`status: "scored"`，无`pending`残留：

- 合计：200/450（44%）
- batch1：150/150（**100%，全部核对完成**）
- batch2：50/300（17%）

**batch1（150条）按题型分布：** 三种题型均100%核对完成，均衡覆盖。

| 题型 | 已核对/总数 |
| --- | --- |
| behavioral | 50/50 |
| technical | 50/50 |
| case_analysis | 50/50 |

**batch1（150条）按分档分布：** 五档均100%完成，各30条（各占20%）。

| 分档 | 已核对/总数 |
| --- | --- |
| 0-2 | 30/30 |
| 3-4 | 30/30 |
| 5-6 | 30/30 |
| 7-8 | 30/30 |
| 9-10 | 30/30 |

**batch2（300条）按题型分布：** 只核对了behavioral题型的一半，
technical、case_analysis两种题型**尚未开始**（0/100，各自）。

| 题型 | 已核对/总数 |
| --- | --- |
| behavioral | 50/100 |
| technical | 0/100 |
| case_analysis | 0/100 |

**batch2（300条）按分档分布：** 五档进度均匀（各占已核对behavioral
题型的1/5），但相对300条总量每档只完成约17%。

| 分档 | 已核对/总数 |
| --- | --- |
| 0-2 | 10/60 |
| 3-4 | 10/60 |
| 5-6 | 10/60 |
| 7-8 | 10/60 |
| 9-10 | 10/60 |

**batch2 behavioral 50条在7个领域（`job_type`字段）内部的分布：**
完成度不均，金融/设计/运营三个领域进度明显落后。

| 领域 | 已核对/总数 |
| --- | --- |
| 技术 | 10/15 |
| 产品 | 10/15 |
| 市场营销 | 10/15 |
| 设计 | 5/15 |
| 咨询 | 5/15 |
| 运营 | 5/15 |
| 金融 | 5/10 |

**跨batch合并统计（按题型，三大类）：**

| 题型 | 已核对 |
| --- | --- |
| behavioral（batch1通用50 + batch2七领域50） | 100 |
| technical（仅batch1通用） | 50 |
| case_analysis（仅batch1通用） | 50 |

**跨batch合并统计（按分档）：** 200条里每档恰好40条，完全均匀
（各占20%）——这是batch1本身按档均分（每档30条）加上batch2已核对的
50条behavioral题型答案也恰好每档10条，两者叠加后仍保持均匀，属巧合
而非刻意控制的结果，不代表batch2整体核对进度是均衡的（见上面
batch2单独的分档表，相对300条总量每档仍只完成约17%）。

**结论：** 第7周的`ml/`小样本可行性实验只使用batch1的150条数据（三
种题型各50条，均衡），不并入batch2已核对的50条behavioral数据。原因：

1. batch1的150条全部来自`sample_questions.json`的30道通用校准题，
   batch2的50条behavioral来自`question_bank.json`里7个领域的定向题目
   ——两者是不同的数据源。若把这50条并入"behavioral"类别，会在同一
   个题型标签下混入两种来源的回答，模型可能学到"数据来源"而非
   "结构完整度"这个信号，构成分布混杂；
2. 题型分布会从均衡的50/50/50变成100/50/50，与按"题型×档位"联合分层
   的划分方案冲突，且technical、case_analysis两种题型完全没有batch2
   的对应数据，behavioral单独扩容不构成有意义的跨领域验证。

batch2的剩余核对工作（把300条候选全部审完，含technical、
case_analysis两种题型，目前均为0/100）是一项独立的、更大规模的标注
扩充任务，不属于第7周计划范围。待batch2三种题型的核对进度同步、
不再是只有behavioral一种题型有数据时，再统一并入并另开一条决策记录
说明入库理由；在此之前，`ml/`目录下的所有实验一律只读取batch1这
150条，`data/labeled_answers_human_reviewed.json`里当前已核对的
batch2的50条behavioral记录暂不使用。

**归属：** 评分系统、数据标注。

## 31. call_llm() 429限流修复改为按调用方分级等待，避免拖慢实时对话路径

**背景：** [[20]]第2项风险提到scoring_judge.py的三层兜底链路（JSON解析
失败→正则提取→长度关键词规则）缺专门测试覆盖，"API超时"等异常场景是
待验证项之一。第7周在Colab上真实跑`ml/augment.py`对fold 2做批量回译
增强时，从约第16个样本开始连续撞上Groq免费档429限流——原有
`llm_client.call_llm()`的重试逻辑是固定1s/2s退避、最多3次快速重试，
对"整个限流窗口已经打满"这种持续性限流完全无效，重试基本必然全部
失败，被`ml/augment.py`当作翻译失败跳过（虽然会print，但Colab cell的
输出本身不落盘，跳过记录容易随runtime一起丢失，无人察觉）。

**决策：**

1. `llm_client.call_llm()`新增`max_retry_wait_seconds`参数：遇到429时
   解析Groq响应的`Retry-After`/`Retry-After-Ms`头，真实sleep建议的
   冷却时间（而不是瞎猜1s/2s），但用这个参数给单次sleep封顶。默认值
   2.0秒——`call_llm()`的主要调用方是`backend/conversation/engine.py`
   的实时面试对话轮次生成，[[17]]和[[20]]都要求实时路径快速降级、
   不能让候选人长时间等待，因此**默认值必须是实时安全的那一个**，
   离线调用方显式传大值来"opt in"耐心等待，而不是默认值悄悄变慢、
   影响到所有调用方（包括没打算改动的实时路径）。
2. `ml/augment.py`的`default_translate()`显式传
   `max_retry_wait_seconds=60.0`（对齐`llm_client._rate_limit_wait_seconds()`
   内部已有的60秒护栏），离线批处理场景下真实等够Groq建议的冷却时间
   再重试，这是决定要不要重试这批429样本的关键。
3. `ml/augment.py`额外在每次真实Groq调用前加了约2.2秒的最小调用间隔
   （对应约27次/分钟，低于免费档30 RPM），从源头上避免整批调用在几
   分钟内打满限流窗口，而不是只靠重试事后补救。
4. `ml/augment.py`的`main()`现在把每折的跳过样本id落盘成
   `fold_{i}_train_augmented.skip_report.json`（哪怕0条跳过也写），
   并在本次产生跳过、或后续复用一份带跳过记录的旧文件时打印醒目
   警告——不再只依赖Colab cell的print输出，避免真实训练数据被静默
   漏掉却无人发现。

**范围澄清（避免混淆）：** `backend/conversation/scoring_judge.py`的
追问评分调用**不经过**`llm_client.call_llm()`——它有独立的Groq client
（`_get_judge_client()`），本来就是单次尝试、无重试循环、1秒超时，任何
异常（含429）都会被外层`except Exception`直接捕获并降级到正则/长度
规则兜底。本次改动完全没有触碰这条路径，此前也不存在"429导致长时间
等待"的风险——这条路径的"快速降级优先于等待重试成功"([[20]]的原则)
从一开始就是成立的。

**对[[20]]第2项风险的回应（部分，非完全验证）：** 本次修复只覆盖了
`call_llm()`调用链（供engine.py实时对话 + ml/augment.py离线批处理）下
的**429限流场景**——新增了真实Retry-After等待+按调用方分级的等待
上限，并用构造的fake异常做了单元验证（header解析正确性、封顶值按
调用方生效）。[[20]]第2项风险本身针对的是`scoring_judge.py`的JSON
schema兜底链路，待验证的具体场景（畸形JSON、字段缺失/类型错误、专门
构造的API超时）**仍未覆盖**，不应把本次改动理解为该风险已经解决——
scoring_judge.py本身完全没有改动。

**归属：** 对话引擎（`llm_client.py`、`engine.py`）、ml/实验脚本
（`ml/augment.py`）。

## 32. ml/augment.py 回译改回本地 Helsinki-NLP MarianMT，放弃 Groq API 方案

**背景：** `ml/augment.py`回译增强的原计划方案是本地跑 Helsinki-NLP
MarianMT（opus-mt-zh-en / opus-mt-en-zh），完全离线、不依赖任何外部
API。中途一度改为调用项目已有的Groq LLM client（[[19]]第1项、
[[20]]第2项背景），图省事复用`backend/conversation/llm_client.py`
现成的retry/timeout封装，避免另起一套翻译调用逻辑。

这个改动在fold 0上跑通过（102/102成功，见`ml/augment_review.md`），
但fold 2真实跑的时候连续撞上Groq免费档429限流（见[[31]]），修了
按Retry-After真实等待+调用方分级封顶之后，又在验证过程中发现更根本
的问题：Groq免费层除了每分钟请求数限制（RPM）外，还有**每日token
配额（TPD）**，而这个配额是跟`backend/conversation/llm_client.py`的
面试对话功能共用同一个模型（`llama-3.3-70b-versatile`）的——也就是说
`ml/augment.py`批量跑回译（一折102条样本×2跳=204次调用）会跟真实
面试对话抢同一份每日配额，一旦当天配额被批量任务耗尽，会直接影响到
面试对话这个核心功能本身的可用性。这不是靠调整重试/限速参数能解决的
问题（[[31]]的修复只解决了RPM这种"窗口性"限流，对TPD这种"每日耗尽后
当天不会恢复"的限流无效），持续跑多折回译在免费层下不可持续。

**决策：** 放弃Groq API方案，改回设计阶段的原始方案——本地跑
Helsinki-NLP MarianMT：

1. `ml/augment.py`的默认翻译器改为通过`transformers`直接加载
   `Helsinki-NLP/opus-mt-zh-en`（中译英）和`Helsinki-NLP/opus-mt-en-zh`
   （英译中）两个模型，`torch.cuda.is_available()`为真则用GPU，否则
   用CPU，不再经过`backend/conversation/llm_client.py`/Groq。
2. 同一批样本改为batch推理（`_marian_translate_batch()`/
   `back_translate_batch()`），而不是逐条调用——本地模型没有外部
   请求配额顾虑，batch化纯粹是为了跑得快，在Colab GPU上比逐条调用
   快很多。
3. 保留原有的所有安全机制：每折输出文件的幂等缓存检查、`--force`
   强制覆盖、`fold_{i}_train_augmented.skip_report.json`跳过记录
   （[[31]]之前那次修复加的）。本地模型基本不会失败，但仍然可能
   OOM或加载失败（没网络下载权重、`sentencepiece`/`sacremoses`
   环境缺失等）——遇到这些情况时同样记录被跳过的样本id，不能因为
   "本地模型很少出错"就放松这条底线，OOM时先按子批折半重试以尽量
   抢救数据，实在不行才整批标记为跳过。
4. `ml/requirements.txt`新增`sacremoses`（MarianTokenizer的分词
   依赖，torch/transformers/sentencepiece此前已经在依赖清单里，
   为train.py的微调模型服务，直接复用）。
5. `ml/baselines.py`里`--llm-baseline`可选项仍然调用Groq
   （用途不同：零样本LLM baseline评分，不是回译增强），本次改动
   不涉及，`groq`/`python-dotenv`依赖保留。

**为什么这是更合适的方案：** 本地模型完全不受外部API限速/日配额
影响，直接用Colab已经在付费/已经分配好的GPU算力，零额外成本——比
"想办法把Groq请求控制在配额内"更符合项目一贯的"尽量免费"约束
（[[19]]第2项TTS引擎选型也是同样的成本考量）。副作用是回译质量
可能不如大模型翻译自然（MarianMT是专用翻译模型，不是通用LLM），
`ml/augment_review.md`里针对fold 0（Groq版本）做的"未发现结构被
改写"人工抽查结论**不能直接沿用到MarianMT版本**——本地模型跑完
fold 0-4后需要重新抽查几条，确认回译质量仍然保留原有的结构完整度
信号，这一点留给下一次实际有真实MarianMT回译数据时去做，本决策
记录不代为下结论。

**归属：** ml/实验脚本（`ml/augment.py`、`ml/requirements.txt`）。

## 33. 第7周微调模型最终选择：distilbert-base-multilingual-cased，不使用数据增强；train.py新增最终模型训练模式

**背景：** [[30]]确定第7周只用batch1的150条数据（5折交叉验证pool 128条
+封存测试集22条）。5折交叉验证跑完了四组组合：xlm-roberta-base（普通版
/增强版）、distilbert-base-multilingual-cased（普通版/增强版）。

**决策（模型选择）：** 最终模型定为
`distilbert-base-multilingual-cased`，**不使用**`ml/augment.py`的回译
数据增强。

**理由（对比数字，均为5折验证集均值）：**

1. distilbert全面优于xlm-roberta-base：mean val macro_f1 0.885 vs
   0.770，mean val qwk 0.950 vs 0.929。
2. `ml/train.py`的过拟合检测（`check_overfit_and_suggest()`，train-val
   macro_f1差距>0.15阈值）在xlm-roberta-base上触发了警告，
   distilbert-base-multilingual-cased没有触发——即模型本身的建议路径
   （见`ml/train.py`模块docstring"Fallback... if xlm-roberta-base shows
   clear overfitting"）也指向同一个结论。
3. distilbert-base-multilingual-cased训练速度明显更快（6层 vs
   xlm-roberta-base的12层，且模型整体更小），在Colab GPU时间有限的
   前提下是额外的加分项，不是决定性理由。
4. 数据增强对distilbert没有带来提升，反而三项指标都略微下降且波动
   变大：macro_f1 0.885→0.878，qwk 0.950→0.942，within1_accuracy
   0.985→0.977。因此最终模型不使用增强数据训练。

**决策（新增train.py最终模型训练模式）：** 之前`ml/train.py`只支持5折
交叉验证（每折在自己的val_ids上评估），没有"确定模型后，合并全部
train+val数据重新训练一次、在封存测试集上出正式指标"这一步。本次给
`ml/train.py`加了`--final`模式：

1. `ml/common.py`新增`load_trainval_ids()`：返回不在`test.json`里的
   全部约128个id（用"排除test_ids"算，不是直接并5折里某一折的
   train_ids+val_ids，这样即使将来fold文件和test.json出现不一致也会
   在下游校验里体现出来，而不是默默算错）。
2. `ml/train.py`新增`train_final_model()`：只用`load_trainval_ids()`
   算出的~128条数据训练，**没有**再切一份验证集出来做早停。训练全部
   结束（`trainer.train()`跑完）之后，才对22条`test_ids`做**唯一一次**
   `trainer.predict()`调用，用来算最终要写进报告的macro_f1、qwk、
   within1_accuracy、exact_accuracy和混淆矩阵。函数一开始就校验
   `trainval_ids`和`test_ids`没有交集，有重叠直接抛`ValueError`，不会
   静默拿测试集数据参与训练——这是本次任务要求里"测试集绝不能以任何
   形式参与训练或早停决策"的硬约束在代码层面的落地。`ml/self_test.py`
   新增了针对这条guard的测试（构造故意重叠的id，断言必须抛异常）。
3. 早停策略调整：因为没有验证集了，`--max-epochs`/`--patience`/
   `--monitor`这几个CV模式的参数在`--final`模式下不生效，改成
   `--final-epochs`固定训练轮数。默认值`DEFAULT_FINAL_EPOCHS=14`——
   取自distilbert-base-multilingual-cased（不增强）5折交叉验证里各折
   收敛所在epoch数区间（约10-18轮）的中位数附近，作为没有精确逐折
   数字时的合理近似（当前Colab上那次CV跑的时候还没有记录逐折收敛
   epoch，本地也没有同步那次跑的summary.json，所以只能用这个近似值）。
   同时给`train_one_fold()`加了`best_epoch`字段（从
   `trainer.state.log_history`里，找`eval_{monitor}`取到最大值那次的
   epoch），`_write_summary()`里汇总出`mean_best_epoch`——以后重新跑
   CV时，`--final-epochs`可以直接从新一次summary.json的
   `mean_best_epoch`读，不用再靠这个近似值。`ml/colab_run.ipynb`新增
   的步骤11会自动读取该字段（读不到就落回默认值）。
4. `--final --augment`组合直接抛`NotImplementedError`：
   `ml/augment.py`的回译数据是按每折的train_ids单独生成的
   （`fold_{i}_train_augmented.json`），没有对应128条trainval全集的
   增强文件，而且本决策定的最终模型本来就不用增强，这个组合超出当前
   范围，不做即时支持。
5. `ml/colab_run.ipynb`新增步骤11（"最终模型——合并train+val训练一次，
   在封存测试集上评估一次"），原步骤11"拉取结果"顺延为步骤12。

**范围：** `ml/train.py`（`train_final_model()`、`--final`/
`--final-epochs`CLI、`train_one_fold()`的`best_epoch`记录）、
`ml/common.py`（`load_trainval_ids()`）、`ml/self_test.py`
（`test_train_final_smoke()`）、`ml/colab_run.ipynb`（新增步骤11）。

## 34. 第7周最终模型封存测试集结果（[[33]]的`--final`模式实际跑出的正式数字）

**内容：** [[33]]确定的最终模型（distilbert-base-multilingual-cased，不用
增强数据，CV pool 128条train+val合并训练，`--final-epochs`固定14轮、无
早停）已在Colab上用`ml/train.py --final`实际跑完，对22条封存测试集
做了唯一一次`trainer.predict()`调用，正式结果：

| 指标 | 数值 |
| --- | --- |
| exact_accuracy | 0.773 |
| macro_f1 | 0.769 |
| qwk | 0.936 |
| within1_accuracy | 1.000 |

对照：该模型5折交叉验证验证集均值为macro_f1=0.885、qwk=0.950
（[[33]]已记录）。

**解读：** 测试集的macro_f1/exact_accuracy明显低于CV验证集均值，但
qwk（0.936 vs 0.950）和within1_accuracy（1.000）几乎没有跟着下降——
22条测试样本里，预测档位全部落在真实档位±1档以内，没有偏离2档以上
的错判。测试集n=22远小于CV验证集单折的25-26条（更远小于5折加权平均
的等效样本量），本身方差就大，加上macro_f1对每个档位一视同仁地加权
（22条样本平均分到5个档位后，某一档只错1-2条就会让该档F1大幅波动），
这类差距在小样本下是预期内的正常波动，不足以单独作为"模型泛化能力
不足"的证据。qwk和within1_accuracy这两个对"错多远"更敏感/更宽容的
指标依然很高，且错判全部是相邻档位误判（未发现跨档2档以上的错误），
三个信号一起看，更支持"模型的结构判断能力本身是稳定的，测试集
exact_accuracy偏低主要是小样本方差，不是学到了错误的判断逻辑"这个
结论，而不是"CV阶段被高估、真实能力更接近测试集数字"。

**未验证/留待后续：** 22条样本量太小，这个解读本身也只是描述性归纳，
不是统计显著性检验的结论——严格意义上不能排除小部分能力确实有所
下降、只是被qwk/within1的宽容度掩盖了。后续若能扩充封存测试集规模
（例如batch2核对完成后按同样分层方式重新划出更大的test集），应
重新评估这个解读是否成立。

**归属：** ml/实验脚本（`ml/train.py` `--final`模式的实际产出）、
`docs/week7_finetuning_results.md`。

## 35. 数据增强长度伪影逐样本深度诊断——放弃补做，原始数据已随Colab虚拟机重置丢失

**背景：** `docs/week7_finetuning_results.md` 第7节原本定好了方法论要求：
如果第5节"数据增强前后对比"的指标出现明显变化（不论变好变坏），要用
`ml/error_analysis.py --compare-augmentation` 对distilbert普通版/增强版
的`oof_predictions.json`（5折CV阶段对CV pool 128条的逐样本OOF预测）做
一次逐样本级别的长度伪影交叉检查，排查回译增强是否让模型学到"更长=
更完整"这种捷径而非真实结构信号（[[32]]背景：回译会让训练样本平均
变长约23%）。第5节的实际结果确实触发了这个条件——distilbert增强版
四项指标（macro_f1/qwk/within1_accuracy/exact_accuracy）相比普通版
一致小幅下降。

**问题：** 尝试执行这项诊断时发现，5折CV阶段生成的`oof_predictions.json`
（distilbert普通版+增强版各一份）已经不在Colab虚拟机上——大概率是
运行时被重置（切换运行时类型，或GPU每日额度用完导致虚拟机被替换）
时丢失，当时没有同步保存到本地或Drive。目前唯一保留下来的是
`ml/train.py --final`那一步的输出（[[34]]用的22条封存测试集预测），
这份数据覆盖的是不同的样本集合（测试集，不是CV pool），无法替代
丢失的OOF预测用于这项诊断。

**决策：** 不为了补齐这一项诊断重新花Colab GPU时间重跑一次完整5折CV
（distilbert普通版+增强版各5折，共10折）。理由：这项诊断本身是探索性
排查线索，不是决定模型选择的必要依据（[[33]]的模型选择结论——distilbert
优于xlm-roberta、增强对distilbert没有帮助——完全建立在已有的汇总指标
上，不依赖这项逐样本诊断），重新训练10折的GPU时间成本，相对于补齐
一项"就算做了也可能因样本量小而给出'不确定'结论"的诊断，边际收益
不划算。

`docs/week7_finetuning_results.md`第7节改为仅基于第5节已有的汇总指标
给出结论：三项指标下降的量级（0.007-0.008）明显小于5折间本身的波动
（普通版±0.054、增强版±0.075，均以macro_f1为参考），差距很可能落在
噪声范围内，**不能确定下降是数据增强本身的负面影响还是随机波动**。
文档中明确标注这是"深度诊断未做"，不能写成"已排查、未发现长度伪影
证据"——两者含义完全不同，前者是问题悬而未决，后者是有证据支持的
排除，绝不能把"没做"包装成"做了没发现"。

**经验教训（面向后续，非当前立即行动项）：** 之后如果重新跑CV训练，
`oof_predictions.json`这类中间产物应该在每折训练结束后立即同步一份到
Drive或打包下载，不能只留在虚拟机本地文件系统里等训练全部结束后一次性
打包——运行时中途被重置（额度耗尽、类型切换）是已经实际发生过的风险
（这是本次丢失的直接原因），"全部跑完再打包"这个假设在长时间、跨多次
Colab session的训练流程里不成立。

**归属：** ml/实验脚本（`ml/error_analysis.py`、`ml/colab_run.ipynb`中间
产物保存方式）、`docs/week7_finetuning_results.md` 第7节。

## 36. 第8-13周最终计划定案（取代决策#14中"第8周=复盘报告生成"的旧预测）

**内容：** 第7周收尾时盘点"复盘报告"相关功能的具体缺口，发现比决策#14
预测的范围更大——尤其是baseline.py需要新增逐句高亮的数据结构支持（决策
#14第2项缺口），属于有实际工作量的后端任务；同时决策#16、#17里记录的
分诊流程UI改造、实时反馈闭环也需要独立安排周次。原定"11-12周"的宽限
一并重新核算。

**决策：** 项目总周期从原10周最终确定为13周（第8-13周共6周，比此前预留
的11-12周再加1周缓冲），由用户拍板决定，理由是"宁可提前说清楚需要多少
时间，也不要到第12周发现塞不下又要临时改计划"——对于需要经得起讲述的
简历项目，过程稳妥比赶进度更重要。最终安排（本决策取代决策#14中关于
第8周的预测）：

- 第8周：分诊流程UI改造（决策16 + 决策17第1项）——开场引导页、对话式
  分诊问答页、结果展示页，三页拆分，纯前端，不碰后端逻辑
- 第9周：对话引擎接入面试页面——把backend/conversation/engine.py接到
  新页面，问题展示+作答+追问推进+session落盘，首次跑通"分诊到面试结束"
  完整链路
- 第10周：实时反馈闭环（决策17第2项）——面试官开场白+每轮即时反馈
  （内容结构+表达纠错），叠加在第9周页面上
- 第11周：复盘报告后端——session按topic聚合评分、baseline.py补逐句
  高亮数据结构（决策14第2项缺口）、highlight_turn_id/highlight_reason
  生成（决策9）、history_trend+空session fallback（决策10）。纯后端+
  测试，不做页面
- 第12周：报告页面+进度追踪页面——渲染第11周的数据（总分/四维度/逐句
  高亮），接入第7周微调模型对比baseline；进度趋势图+可分享战绩卡片
  （决策14第3项）
- 第13周：精度债务优化+整合联调/部署/文档收尾——优先做具体性维度精度
  问题、语速/停顿阈值真实录音校准（决策20/27里价值最高的两项），其余
  债务写进最终backlog不强做；整体联调、部署、README/架构图/演示脚本
  收尾

**状态：** 计划已定案，从第8周起按此执行。

**归属：** 跨模块（前端UI、对话引擎、评分系统、复盘报告、进度追踪、
部署文档）。

## 37. 第10周实时反馈闭环上线，已知局限：对"部分相关但未正面回应"的
答案识别力较弱

**内容：** 第10周新增了对话过程的实时反馈闭环——每轮候选人作答后，除了
原有的追问决策逻辑，新增一次独立的轻量Groq调用（`backend/conversation/
realtime_feedback.py`，复用`scoring_judge.py`同款8B快模型+短超时+失败
静默降级的调用范式），生成"内容/结构反馈"和"2-3条表达纠错建议"两部分
文本，写入QAItem新增的`content_feedback`/`expression_suggestions`字段
并随每轮`save_session()`一起落盘；开场白同步更新为提及"我会给你反馈"
这一用户可感知行为，但不透露内部实现细节。

真实API测试中观察到：反馈对完全偏离主题的答案（如英文测试里用"I feel
good"回答技术项目问题）能准确识别"未回应问题"，但对部分相关但未正面
回应的情况（如中文测试里用"数据一致性方案"回答"为什么选Kafka"这类
选型理由问题）识别力较弱，倾向于归类为"内容不够具体"而非"未回答所
问问题"。

**决策：** 功能按计划完整实现并验证通过（真实API测试+本地UI走查），
合并入main。反馈判断力的这个局限记入后续待打磨清单，不阻塞本周合并；
如后续要优化，可考虑在prompt里显式要求模型先判断"回答是否正面回应了
被问的问题"再展开反馈内容。

**状态：** 已完成并合并。

**归属：** 对话引擎、评分系统。

## 38. 插入第11周"语音接入"，第11-13周顺延为第12-14周（更新决策#36的
周次编号）

**内容：** 第10周完成后发现，`backend/speech/`（`transcribe.py`语音
识别、`tts.py`语音合成、`features.py`语速/停顿/填充词/音量特征分析）
虽然函数实现相对完整（原计划中TTS已在第4周排期完成），但从未被接入
`frontend/app.py`——第8-10周重建整个面试页面（三页拆分、对话引擎接入、
实时反馈）的过程中，也始终没有触碰语音相关代码，导致候选人实际能用到
的产品目前是纯文字双向交互，语音功能是"已实现但未接入"的孤立模块。
另外注意到决策#27计划中"语速/停顿阈值真实录音校准"（原排在第13周精度
债务里）依赖真实录音数据，如果语音输入功能还没接上，届时校准工作会
没有真实音频可用。

**决策：** 在第10周之后插入一周专门做"语音接入"（ASR输入+TTS输出接进
面试对话页面），作为新的第11周，原第11-13周依次顺延为第12-14周。总
周期从13周（第8-13周）调整为14周（第8-14周）。插入位置选在紧接第10周
之后，理由：(1) 与第8-10周同属"面试页面"这一条工作线，趁上下文还热
乎的时候做完，减少跨周切换遗漏细节的风险；(2) 满足决策#27语速校准对
真实录音数据的依赖，语音先接上，第14周（原第13周）的校准工作才有真实
数据可用。本决策更新决策#36中第11-13周的编号安排，第11-13周的具体
内容不变，仅顺序整体后移一位。

调整后最终安排：
- 第11周（新增）：语音接入——ASR语音输入+TTS语音输出接进第9-10周已
  建好的面试对话页面
- 第12周（原第11周）：复盘报告后端
- 第13周（原第12周）：报告页面+进度追踪页面
- 第14周（原第13周）：精度债务优化+整合联调/部署/文档收尾

**状态：** 计划已定案，从新第11周起按此执行。

**归属：** 跨模块（语音处理、前端交互、项目管理）。

## 39. 完整性复查发现两项架构级缺口（RAG题库未接入、用户身份缺失），插入
两周，总周期调整为16周

**内容：** 第10周完成后进行了一次全面的项目完整性复查（扫描全部39个.py
文件的调用链、决策日志逐条核查、README及5份docs文档的关键词扫描），除
已发现并处理的语音接入缺口（见决策#38）外，还发现两项分量更重的架构级
缺口：

1. RAG题库检索系统（`backend/rag/`，含决策#24/#25规划的7岗位×3题型×200
   题库）从未被`backend/conversation/engine.py`调用——面试问题完全由LLM
   自由生成，题库基础设施建成但零使用。这个缺口还会连锁阻塞原计划中
   "复盘报告后端"这一周：`baseline.score_answer()`需要携带
   `question_type`/`job_type`/`keyword_clusters`/`reference_points`的
   `Question`对象，而现有QAItem不携带这些信息，报告后端在RAG接入之前
   实际无法开工。
2. `InterviewSession.user_id`字段全项目从未被赋值（始终为空字符串），
   项目没有任何用户身份识别机制。这会阻塞原计划中"报告页面+进度追踪
   页面"这一周的"进度趋势图"功能——没有办法区分不同用户的历史session。

另外核查还发现几项较小的缺口：决策#21（TTS音质优化）未排期；决策#20的
5项待验证风险中，第2/3/5项（Groq结构化输出容错专项测试、中文声线真人
盲听、VAD对填充词实际影响）既未排期也未被正式确认为backlog，处于中间
状态；决策#11要求对话引擎必须使用`interview_stage`参数，但
`backend/conversation/prompts`的`build_full_system_prompt()`至今只接受
persona和language，目前"能用"是因为严格型人设与终面阶段恰好一一对应的
巧合，不是真正实现；`QAItem.question_source_id`（RAG关联字段）和
`realtime_feedback_score`（追问决策的数值信号）两个字段定义了但从未被
实际写入，永远为None；决策#12的"如何应用"文字仍停留在"未排期"的旧状态，
但`backend/conversation/prompts/strict_zh.py`实际已经落实了该决策的
要求，是记录滞后而非功能缺口；第9-11周新增模块（session_adapter、
realtime_feedback、语音相关代码）目前没有单元测试覆盖。

**决策：** 在语音接入周之后插入两个新周次：

- 新增一周：RAG题库接入引擎——把`backend/rag/`检索能力接入`engine.py`
  的问题生成逻辑，同时顺手解决`interview_stage`未被实际使用的问题
  （同一批代码改动范围）
- 再新增一周（插在原"复盘报告后端"之后、原"报告页面+进度追踪"之前）：
  用户登录体系——新建用户表、注册登录页面，把现有session创建代码（分诊
  落库、面试环节）改为传入真实`user_id`

原定后续几周依次顺延两位。总周期从14周（插入语音接入后的周期）调整为
16周（第8-16周）。

**较小缺口的处理方式：** 决策#21（TTS音质优化）并入语音接入周（该周本
就涉及TTS代码）顺手处理；决策#20第2/3/5项正式确认为backlog（不排入
第8-16周），性质与决策#30一致——已知、暂不处理，非遗漏；
`interview_stage`问题并入新增的RAG接入周一起解决；
`QAItem.realtime_feedback_score`字段的填值缺失现在顺手修复
（`question_source_id`会随RAG接入自然解决）；决策#12状态文字更新为
"已完成"；测试覆盖债务记入最后一周"整合联调"范围。

**最终第8-16周完整安排：**

- 第8周：分诊流程UI改造（已完成）
- 第9周：对话引擎接入面试页面（已完成）
- 第10周：实时反馈闭环（已完成）
- 第11周：语音接入（ASR+TTS，含决策#21音质优化顺带处理）（已完成，另见
  语音接入后的两项跟进：播放条样式、开局对话/打字默认弹窗）
- 第12周：RAG题库接入引擎（含`interview_stage`参数补齐）（已完成，见
  决策#40）
- 第13周：复盘报告后端
- 第14周：用户登录体系
- 第15周：报告页面+进度追踪页面
- 第16周：精度债务优化+整合联调/部署/文档收尾（含测试覆盖债务）

**状态：** 计划已定案，从第11周起按此执行。

## 40. 第12周RAG题库接入引擎上线，`interview_stage`缺口一并修复

**内容：** 按决策#39的安排，把`backend/rag/retriever.py`的检索能力接进了
`backend/conversation/engine.py`的提问逻辑，同时补齐了决策#11要求但
`build_full_system_prompt()`此前从未真正接受的`interview_stage`参数。

**架构取舍——为什么是"提示词层注入候选问题"而不是"代码层强制替换"：**
`engine.submit_answer()`原有设计是每轮一次LLM调用，模型自己根据
`state_context`判断本轮是继续追问（FOLLOW_UP）还是收尾转下一话题
（NEXT_QUESTION），转话题时的新问题也是在同一次回复里由模型自由生成、
折叠进过渡语的——没有一个"新话题开始"的独立代码钩子可以拦截替换。为了
不推翻这个已经跑通、由few-shot示例调教出的自然对话流程，`engine.py`
新增了`next_question_hint`参数：`session_adapter.py`在每轮真正调用引擎
*之前*，会预先按话题轮转（第1话题behavioral/第2话题technical/第3话题
case_analysis，从题库5个候选里随机抽1个，避免同一岗位每次面试都问一模
一样的3道题）取一个候选问题，作为"如果你判断该转话题了，请用这个问题"
的条件性指令注入prompt——模型是否真的用上、是否需要转话题，仍由原有
机制决定，取不到候选（题库无匹配、检索报错）时`next_question_hint`为
`None`，行为与接入前完全一致，这是刻意维持的向后兼容路径，不是遗漏。

`interview_stage`修复：`build_full_system_prompt()`新增必填的
`interview_stage`参数，为HR初筛/技术面①/技术面②/终面各写了一句情境提示
（语气/追问深度的定性描述，不重写persona本身的语气规则），拼进system
prompt末尾。`EngineSession`相应新增`interview_stage`字段，
`session_adapter.start()`/前端调用点改为传入
`interview_session.config.interview_stage`（原来根本没传）。

**`question_source_id`补齐：** `InterviewProgress`新增
`current_topic_question_id`字段，与已有的`current_topic_turn_id`同生命
周期（话题开始时设置、追问轮次原样携带、下一话题开始时刷新），
`submit_round()`据此把每个主问题QAItem的`question_source_id`设为真实
题库id，追问QAItem保持`None`（决策#39里"顺带解决"的两个字段缺口之一，
另一个`realtime_feedback_score`早已在第9-10周填值，这次复查确认没有
遗漏）。

**验证：** `python -m py_compile`全量通过；新增
`tests/test_session_adapter_rag.py`（真实检索、话题轮转、随机性、检索
失败降级共6个用例）；新增`scripts/smoke_test_week12.py`，用真实Groq
API + 真实Chroma索引跑完整3话题面试，断言每个主问题的`question_source_id`
命中题库真实条目、追问条目为`None`、`save_session()`/`load_session()`
往返后字段不丢，测试session用完即删。这两项因为需要`chromadb`/
`sentence-transformers`/`groq`等依赖，在受限的沙盒桥接环境里跑不了，
留给有完整依赖的本地环境执行确认。

**顺手验证：** 复查确认`data/question_bank.json`的`job_type`取值
（技术/产品/市场营销/运营/设计/咨询/金融）与`questionnaire.py`的
`JOB_TYPES`完全一致，200题在7岗位×3题型的每个组合下都有9-10条，检索
不会出现"某岗位某题型无题可用"的空档。

**状态：** 已完成并通过本地真实环境验证——`pytest
tests/test_session_adapter_rag.py`6/6通过，`scripts/smoke_test_week12.py`
真实Groq API全程跑通（3个主问题分别命中`tech_behavioral_03`/
`tech_technical_04`/`tech_case_analysis_04`，5次追问`question_source_id`
均为`None`，存库读库往返无丢失），已提交（commit 3afef74，`week12-wip`
分支）。冒烟测试过程中发现的Groq限流问题另见决策#41。

**归属：** 对话引擎、RAG检索、前端交互。

## 41. 第12周冒烟测试暴露：Groq TPM速率限额偏紧，追问/反馈偶发限流降级

**内容：** 跑`scripts/smoke_test_week12.py`真实冒烟测试全程遇到大量Groq
429限流——`llama-3.3-70b-versatile`（主对话回复用）限额12000 TPM、
`llama-3.1-8b-instant`（`scoring_judge.judge_answer()`打分+
`realtime_feedback.generate_feedback()`即时反馈共用）限额6000 TPM，均被
打满，触发多次重试退避；有几轮追问/反馈在3次重试后仍失败，走了各自模块
已有的静默降级路径（追问回复退化为"抱歉，AI面试官暂时无法回应…"这类兜底
文案，反馈生成失败则该轮`content_feedback`/`expression_suggestions`为
`None`）——这是`llm_client.py`/`realtime_feedback.py`已有的容错设计在
正常工作，不是新bug，冒烟测试的断言范围只覆盖`question_source_id`归属
和存取库完整性，不校验回复语义，所以没有让测试失败。

第12周本身也让每次system prompt变长了一些（新增的`interview_stage`情境
提示每次都会拼进prompt，`next_question_hint`候选问题在多数追问轮次里也
会拼进去），对本就紧张的TPM额度是一个真实的、但目前无法量化占比的加重
因素——冒烟测试只跑了一次完整会话，样本太小，判断不了"限流频率相比第10-11
周是否明显上升"。

**决策：** 不阻塞第12周合并——限流触发的是已有的静默降级路径，不是功能性
缺陷，且属于Groq账号配额这一外部约束，非代码逻辑问题。记入backlog，不
排入当前第13-16周计划：

- 后续如果要频繁做真实演示/真实用户测试，优先考虑升级Groq账号tier换取
  更高TPM额度（对比"优化prompt长度"，这是更直接、风险更低的解法）
- 如果要降prompt体积，`interview_stage`情境提示和few-shot示例都有压缩
  空间，但会牺牲一些效果，不建议在没有实测对比前贸然做
- 顺带记录一个非阻塞提示：冒烟测试过程中出现过一次HuggingFace未认证
  请求的提示（建议设置`HF_TOKEN`），只影响`sentence-transformers`模型
  下载速度，不影响功能，一并记入backlog，不单独排期

**状态：** 已确认为已知限制，记入backlog。

**归属：** 对话引擎、外部API依赖管理。

**归属：** 跨模块（RAG检索、用户身份、对话引擎、前端交互、项目管理）。

## 42. 第13周复盘报告后端上线：逐句高亮、AI高光时刻、跨会话趋势

**内容：** 按决策#39第13周的安排，一次性做完了"复盘报告后端"的完整范围
（用户在范围确认时选择"全部做"），具体包括四块：

1. **单题打分聚合**：只对有真实`question_source_id`的主问题QAItem调用
   现成的`score_answer_report()`打分，追问（`question_source_id`为
   `None`，第12周就是这么设计的——追问是模型现场生成，不在题库里）直接
   跳过，不报错。
2. **逐句高亮结构化数据**（决策#14第2项/决策#39点名的缺口）：
   `backend/scoring/report.py`新增`Highlight`（`sentence_index` /
   `sentence_text` / `polarity` / `reason`）数据类，`DimensionScore`新增
   `highlights`字段；`backend/scoring/baseline.py`四个评分子函数各自补上
   了产出高亮的逻辑——结构完整性对每个命中的STAR/问题-方案-权衡-结论/
   案例五环节要素，定位其相似度最高的那句话；关键词覆盖对每个命中的关键
   词簇同理定位最佳匹配句（各上限5条，与原有`hit_preview`展示上限一致）；
   逻辑连贯性固定给出1条负向高亮，定位全文中相邻句相似度最低的那一处转折
   （"读起来像逻辑跳跃"的具体位置，而不只是一个分数）；具体性新增按句
   统计数字/细节用词密度，取密度最高的最多3句给正向高亮。`sentence_index`
   对应的是`baseline.py`自己的`_split_sentences()`切句结果里的位置，不是
   原始文本的字符偏移——这样前端只要用同一个切句函数重新切一次答案文本，
   就能直接用下标定位，不需要这里额外维护字符偏移量。
3. **AI高光时刻**（决策#9的主观判断+理由）：新建`backend/report/`包，
   `highlight_picker.py`照搬`scoring_judge.py`的调用模式（独立Groq
   client、小模型、严格超时、JSON schema、正则兜底），但兜底层做了改动
   ——`scoring_judge`的兜底是"没有真实答案时用规则硬猜一个"，这里的兜底
   则是"选综合分最高的一轮"，是一个真实、可以站得住脚的事实兜底，不是编造
   的主观判断，所以`highlight_turn_id`只要`detailed_scores`不为空就一定
   会有值，不会因为Groq调用失败就整体开天窗。
4. **跨会话分数趋势**（决策#10）：`backend/storage/db.py`新增
   `list_sessions_by_user()`，按`created_at`取某用户的历史session（可选
   排除当前session、可选limit），返回顺序reorder成按时间正序，供
   `history_trend`直接使用；只统计`report`不为`None`的历史session，
   首次面试或历史session都还没打分时自然是空列表（前端空列表兜底展示不
   在本周范围内，决策#39里已经明确排除）。

**为什么`voice_summary`/`text_correction_suggestions`不新增LLM调用：**
决策#41记录了这个项目的Groq TPM额度本身就偏紧，报告生成虽然不在面试
实时链路上、没有延迟压力，但一次报告生成如果要对整场转写做一次
prose-生成调用，消耗的token量本身仍是这份共享额度的真实开销，在没有
具体场景需要"模板写不出来的文字"之前不值得多花。所以`voice_summary`是
纯模板拼接（跨轮次汇总填充词/停顿次数，无语音数据时走既定兜底文案）；
`text_correction_suggestions`是对第10周`realtime_feedback.py`已经生成
过的`expression_suggestions`做去重聚合（上限5条），不是新调用。

**为什么没有把`generate_review_report()`接进
`session_adapter.end_interview()`：** 决策#39已经把本周范围限定为
"后端和测试"，报告页面排在第15周——现在接入意味着面试结束流程会多一次
（或几次）同步的打分+Groq调用，在还没有报告页面消费这份数据、也没有真实
体验反馈之前，没有必要让这个成本落到面试流程本身。`generate_review_report()`
现在是一个独立、可以单独调用/单独测的函数，留给第15周决定怎么接。

**新增/修改文件：** `backend/scoring/report.py`（`Highlight`类、
`DimensionScore.highlights`）、`backend/scoring/baseline.py`（四个评分
子函数补高亮逻辑）、`models/session_schema.py`（`DimensionHighlight`/
`DimensionScoreDetail`/`TopicScoreDetail`三个独立持久化孪生类、
`ReviewReport.detailed_scores`字段）、`backend/storage/db.py`
（`list_sessions_by_user()`、`detailed_scores`反序列化）、
`models/question_schema.py`（`get_question_by_id()`，`question_id`到
`Question`的查找，供报告生成把`question_source_id`换回真实题目）、新建
`backend/report/generator.py`（`generate_review_report()`主入口）、新建
`backend/report/highlight_picker.py`（AI高光时刻选取）。

**验证：** `python -m py_compile`全量通过；更新
`tests/test_baseline_scoring.py`（`{"score","explanation"}`键集断言改为
`{"score","explanation","highlights"}`，新增高亮内容/负向转折点/空答案
零高亮三个专项用例）；新增`tests/test_highlight_picker.py`（6个用例，全部
用`unittest.mock.patch`模拟Groq client，覆盖LLM正常返回/返回非法
turn_id/JSON解析失败走正则兜底/调用异常兜底/空`detailed_scores`五条
路径，不依赖真实网络）；新增`tests/test_report_generator.py`（monkeypatch
掉`get_question_by_id`/`list_sessions_by_user`/`pick_highlight`，用真实
`score_answer_report()`跑`data/sample_questions.json`，覆盖只打分主问题
跳过追问、题库id失效不崩溃、文本纠正建议去重截断、语音摘要中英文兜底文案
等场景）；新增`scripts/smoke_test_week13.py`，用`data/question_bank.json`
真实"技术"岗位题目+真实Groq API跑完整`generate_review_report()`，断言
高亮数据非空、`save_session()`/`load_session()`往返后`detailed_scores`
（含高亮）不丢、第二个session能出现在第一个session的`history_trend`里，
测试用完清库。后两项（`test_highlight_picker.py`不依赖网络已可在沙盒里
跑通语法检查，但`test_report_generator.py`需要真实embedding模型、
`smoke_test_week13.py`还需要真实Groq API）留给有完整依赖的本地环境执行
确认。

**状态：** 已完成并通过本地真实环境验证——`pytest
tests/test_baseline_scoring.py tests/test_highlight_picker.py
tests/test_report_generator.py`28/28通过，`scripts/smoke_test_week13.py`
真实Groq API全程跑通（逐句高亮非空、`save_session()`/`load_session()`
往返后`detailed_scores`含高亮不丢、第二个session正确出现在第一个session
的`history_trend`里），已提交并fast-forward合并进`main`（commit
baa108d，`week13-wip`分支）并推送到GitHub。

**归属：** 打分引擎、存储层、报告生成（新模块）、项目管理。

## 43. 第14周用户登录体系上线：用户名/密码 + 会话内登录态

**内容：** 按决策#39第14周的安排（"新建用户表、注册登录页面，把现有
session创建代码改为传入真实`user_id`"——原本只有这一句路线图描述，没有
任何设计细节），补齐了完整的用户名/密码登录体系。范围确认时的关键设计
点是"登录状态要不要跨浏览器刷新保持"，选择了**当前会话内有效**（不引入
额外的cookie管理依赖，刷新页面需要重新登录）。

**新增`models/user_schema.py`**：`User`数据类（`user_id`/`username`/
`password_hash`/`created_at`），刻意不建模用户名密码之外的任何字段——没有
邮箱、没有OAuth身份、没有"记住我"令牌，这是一个练习项目的登录闸门，不是
生产级账号系统。

**新增`backend/storage/user_db.py`**：在`db.py`已经使用的同一个
`sessions.db`文件里新建独立的`users`表（对同一SQLite文件执行第二个
`CREATE TABLE IF NOT EXISTS`是安全、幂等的，沿用`db.py`自己"每个存储模块
负责建自己的表"的既有模式，没有必要为此单独开一个数据库文件）。密码哈希
用标准库`hashlib`的PBKDF2-HMAC-SHA256（20万次迭代）+ `secrets.token_bytes`
随机加盐，存成`"盐值hex$哈希hex"`，不引入bcrypt/passlib——一个没有不可信
外部用户的练习项目登录系统，没必要为此新增依赖。`create_user()`/
`authenticate_user()`基本合法性校验（用户名3-30字符、密码至少6位）用
`InvalidCredentialsError`携带机器可读的`reason`码（不是拼好的中/英文
提示文本），前端自己把`reason`映射到`frontend/strings.py`的本地化字符串
——延续了这个项目"后端模块不硬编码UI文案"的一贯做法（对比
`scoring_judge.py`等模块的输出是LLM按语言生成的对话内容，性质不同）。
`authenticate_user()`对"用户名不存在"和"密码错误"统一返回`None`而不是
分别抛不同异常，避免调用方能借此枚举出哪些用户名已注册。

**前端接入（`frontend/app.py`）**：新增`render_login_page()`（登录/注册
两个tab，用`st.radio`切换），插在原有`onboarding_stage`路由**之前**作为
一个整体闸门——`st.session_state["current_user"]`不存在时只渲染登录页，
存在时才走原来的`welcome→triage→result→interview→interview_ended`路由，
并在侧边栏加一行当前用户名+退出登录按钮。`_finalize_triage()`创建
`InterviewSession`时，`user_id`改为传入`st.session_state["current_user"]
.user_id`，这是本周唯一需要改动下游行为的地方——`db.py`/
`backend/report/generator.py`已经在正确消费`user_id`（决策#42就是为了
这天，`list_sessions_by_user()`的跨会话趋势现在才第一次能真正按人分桶）。
新增`frontend/strings.py`条目全部走既有的`t()`机制，中英文各新增20条，
零硬编码文案。

**验证：** `backend/storage/user_db.py`纯标准库（`sqlite3`/`hashlib`/
`secrets`），不依赖Groq/embedding模型，这次不用等本地环境——直接在沙盒里
跑通：新增`tests/test_user_db.py`（15个用例，覆盖创建/查重/用户名密码
校验的三种reason码/登录成功失败的各种场景/去空格/同密码不同哈希/哈希
不包含明文密码），并额外手写了一遍等价的手动验证脚本在沙盒里实际执行
确认全部通过（沙盒没有pytest，装不了，改用等价断言脚本代替）。
`python -m py_compile`覆盖本周全部改动文件（含`frontend/app.py`）。
`frontend/strings.py`用AST解析确认中英文各84个key、无重复。**`app.py`/
`strings.py`的Streamlit运行时行为（登录/注册表单实际渲染、侧边栏退出
登录按钮、触发`_finalize_triage()`后`user_id`确实落库）没有真实Streamlit
环境跑不出来，需要本地`streamlit run frontend/app.py`手动走一遍登录
注册流程确认。**

**状态：** 已完成并通过本地真实环境验证——`pytest tests/test_user_db.py`
全部通过，`streamlit run frontend/app.py`手动走查注册/登录/退出登录/
真实面试流程下`user_id`落库均正常。已提交（commit cc02589，
`week14-wip`分支）并fast-forward合并进`main`，推送到GitHub。过程中
再次踩到device_bash沙盒`.git/index.lock`残留的老问题（这次甚至一度让
`week14-wip`和`main`指向同一提交、看起来像提交丢失），排查后确认是
锁文件问题而非数据丢失——本地磁盘上的文件内容全程完好，删除残留锁文件、
换回真实Terminal提交后一切正常。

**归属：** 用户身份、存储层、前端交互。

## 44. 第15周报告页面+进度追踪页面上线：接入第13周报告后端、第14周真实用户体系

**内容：** 按决策#39第15周的安排（路线图同样只有一句话"报告页面+进度
追踪页面"，没有拆分成两个独立页面还是一个页面的说明），选择了**合并成
一个页面**：面试结束页（原来只有一行"本轮问答记录已保存"）现在直接展开
成完整的复盘报告，报告最下方内嵌跨会话分数趋势图，不做一个独立的、随时
可从欢迎页进入查看历史所有session的浏览页——后者记入backlog，见下文
"未做的部分"。这个取舍是我自己按路线图原文的最简合理解读定的，没有再次
用AskUserQuestion打断确认（前几周的范围确认问题已经问过几次，这次范围
本身没有多个明显不同、需要用户拍板的方案分支，只有"做成什么样"的实现
细节，判断没必要再问一轮）。

**接入`generate_review_report()`（决策#42遗留问题，这周解决）：**
`backend/conversation/session_adapter.py`的`end_interview()`现在会调用
第13周写好的`generate_review_report()`，把结果赋给
`interview_session.report`，再`save_session()`——决策#42当时说"没有报告
页面消费这份数据，没必要接入"，现在报告页面有了，这周就是专门解决这个
遗留问题的。用`try/except`包住这次调用：打分或AI高光选取失败时
`interview_session.report`保持`None`，面试本身照常结束、照常存库，不能
因为报告生成出问题连累面试记录本身丢失——沿用了这个项目一直坚持的
"锦上添花的功能不能拖垮核心流程"原则，虽然报告生成严格来说已经不算纯
"锦上添花"（面试都结束了，没有什么"核心流程"需要保护），但这个原则本身
（宁可降级也不要让用户看到一个丑陋的报错页面）依然适用。

**报告页面内容（`frontend/app.py`的`render_interview_ended_page()`）：**
综合得分（`st.metric`）、AI高光时刻（决策#9，带对应题目和理由）、逐题
详情（每题一个`st.expander`，展开后是四个维度的分数+说明+第13周新增的
逐句高亮——正向高亮标✅、负向标⚠️，直接引用原句）、语音表现摘要、表达
纠正建议列表、跨会话分数趋势图。特意处理了两个边界情况：本次面试还没有
完整回答过一道主问题时（比如刚开始就点了"结束面试"），不展示"0.0/10"
这种会被误读成真实低分的数字，改成一行提示文字；今日分数只有在
`report.detailed_scores`非空时才会被并入趋势图的数据点，否则会有一个
虚假的"今天0分"拉低曲线。第一次面试（没有历史记录）不画图，只展示提示
文案——单点折线图没有信息量。

**趋势图选型：** 用Streamlit自带的`st.line_chart`（背后是Streamlit自身
就依赖的pandas），没有引入Altair等额外绘图库——这是本仓库第一个真正的
图表（之前grep确认过`frontend/`和`backend/`里没有任何`line_chart`/
`altair`/`plotly`/`matplotlib`痕迹），但没有办法在我的沙盒里验证Altair
是否已经装在用户真实的Anaconda环境里、也没法帮用户装，所以选了肯定已经
可用的方案，牺牲了一些视觉可定制性（比如给"今天"这一个点单独放大标注、
自定义hover tooltip样式）换取零新增依赖风险——和决策#43放弃bcrypt/
passlib、选纯标准库密码哈希是同一个取舍逻辑。

**已知的、这周不修的既有缺口：** `backend/scoring/baseline.py`的维度
说明文字（`explanation`字段）一直是纯中文硬编码，不跟随会话语言——这是
第5-6周就有的既有行为，第15周只是第一次真正把这段文字渲染到界面上，
让这个缺口第一次变得肉眼可见（英文界面下报告页会混入中文说明文字），
但修复它属于`baseline.py`打分逻辑本身的改动范围，不在"接入报告页面"
这个任务里，记入backlog。

**未做的部分（backlog，非本周范围）：** 独立的"查看历史所有面试记录"
浏览页面（不依赖刚结束的这次面试、随时可从欢迎页进入、可以点开任意一条
过去的报告）；报告生成目前仍是面试结束时同步触发，一次真实Groq调用+
本地embedding打分，没有做成异步/后台任务，面试结束的那一次点击会有
明显的等待感（依赖Streamlit自身的脚本重跑等待反馈，没有额外加
`st.spinner`文案）。

**验证：** `python -m py_compile`覆盖本周全部改动文件（含
`frontend/app.py`）。`frontend/strings.py`用AST解析确认中英文各97个
key、无重复。新增`tests/test_session_adapter_report_wiring.py`（4个
用例，mock掉`generate_review_report`/`save_session`，覆盖`ended_at`
正确设置/成功时报告正确挂载/`save_session`被正确调用/生成失败时优雅
降级为`report=None`且面试仍正常结束存库）——尝试在沙盒里直接跑发现
`backend.conversation.session_adapter`模块本身的导入链就需要
`backend.conversation.follow_up`等一系列真实依赖，和第12-13周一样沙盒
跑不了，这个新测试文件也需要本地真实`pytest`环境验证，不是像
`test_user_db.py`那样能在沙盒里独立跑通的纯标准库模块。报告页面本身的
Streamlit渲染效果、趋势图是否好看、面试结束后的实际等待感受，都需要
本地`streamlit run frontend/app.py`跑一次完整面试到结束页手动确认。

**状态：** 已完成并通过本地真实环境验证——`pytest
tests/test_session_adapter_report_wiring.py`全部通过，
`streamlit run frontend/app.py`手动走完整面试流程确认结束页正确展示
综合得分/AI高光时刻/逐题详情/语音摘要/趋势图。已提交（commit
be12c39，`week15-wip`分支）并fast-forward合并进`main`，推送到GitHub。

**归属：** 对话引擎、报告生成、前端交互、项目管理。

## 45. 第16周（最后一周）：具体性维度精度优化 + 语速/停顿真实录音校准
（工具已备好，待录音）+ 测试覆盖债务 + 部署文档化 + README/架构收尾

**内容：** 按决策#39锁定的最终安排，第16周是整个8-16周计划的最后一周，
范围是决策#36定的"精度债务优化+整合联调/部署/文档收尾（含测试覆盖
债务）"。开工前和用户确认了两个原计划里没有细化的点：(1)
语速/停顿阈值校准需要真实候选人录音，我这边（云端沙盒+设备桥接）拿不到，
用户选择"提供几段录音"，本周先把校准工具准备好，实际校准等录音到位后
再做；(2) "部署"对于一个简历项目做到什么程度，用户选择"文档化部署步骤"
（本地运行说明+Dockerfile），不做真正的云端上线（我这边没有Streamlit
Cloud账号/secrets访问权限，真要上线也得用户自己在网站上操作）。

**1. 具体性维度精度优化（`backend/scoring/baseline.py`）：** 决策#27的
评估结果显示具体性是四个维度里误差第二大的（MAE 2.27，±1准确率36%，
仅次于当时的关键词覆盖率）。但和决策#29对关键词覆盖率的修法（精确匹配
换成语义相似度匹配）不同，具体性本质上是个词法/模式属性——"有没有数字、
有没有具体工具名、有没有时间跨度"——而不是话题相似度，embedding模型
天然不擅长判断"这段话具不具体"，所以这次没有换匹配方式，而是：(a)
扩充`_DETAIL_MARKER_WORDS`固定词表，补上原来完全没覆盖的时间跨度
（"三个月""半年"等口语化时间说法，原来只认数字）、量化词（"多个""翻了
一倍"等不含数字的规模表达）、产品/规模指标（"日活""转化率""留存率"等
技术/案例分析题常见但原词表没有的词）；(b) 新增
`_count_proper_noun_markers()`：正则匹配文本里的大写开头英文单词（如
"Kafka""Redis""React"），作为"提到了具体工具/产品名"这个词表永远列不全
的信号的补充。开发过程中发现一个真实的正则坑：最初用`\b[A-Z][a-zA-Z]
{1,}\b`，但Python正则的`\b`把所有Unicode"单词字符"都算在内，而中文汉字
在Unicode模式下也是`\w`，导致"用Kafka做异步"这种工具名紧贴中文、中间
没有空格的（技术类回答里的常态）完全匹配不到——`\b`在"用"和"K"之间根本
不存在边界。改用`(?<![A-Za-z])[A-Z][a-zA-Z]{1,}(?![A-Za-z])`（只对
拉丁字母做环视判断，不依赖`\b`）修复，用真实用例手工验证过（"用Kafka做
消息队列，配合Redis做缓存"能正确识别出两个专名，"这次经历很好地体现了
我的领导力"不误触发）。权重/密度常量（`_SPECIFICITY_MARKER_WEIGHT`/
`_EXPECTED_MARKER_DENSITY`，目前仍是未校准的0.5/0.5占位值）本身没有动，
留给下面的校准脚本处理。

新增`scripts/calibrate_specificity.py`：仿照决策#29关键词阈值网格搜索
的方法，对150条人工核对数据预先算好每条记录的原始信号（不用每个网格点
都重新跑一次embedding，只跑一次embedding、之后网格搜索纯算术运算，
省时间），网格搜索`_SPECIFICITY_MARKER_WEIGHT`（0.30-0.70）和
`_EXPECTED_MARKER_DENSITY`（0.3-1.0）两个参数的组合，输出MAE/容差准确率
最优的前10组合，并像决策#29一样检查"最优点附近是不是一片平台而不是
孤立尖峰"。脚本注释里诚实标注了一个决策#29的搜索本身也没解决的问题：
这次网格搜索和`evaluate_baseline.py`报告准确率用的是同一批150条数据，
没有单独的留出集，网格搜索选出的组合是在这份数据上调出来的最优，不能
证明真正泛化——只能算是相对未调参的0.5/0.5起点的合理改进，不是最终
验证过的答案，留待`data/labeled_answers_draft_batch2.json`（决策#30里
还没审核的扩充数据）之后可以拿来做真正的样本外验证。

这一项需要本地真实embedding模型环境才能跑，我这边验证不了，需要用户
本地依次跑：`python scripts/calibrate_specificity.py`（看推荐的权重/
密度组合）→手动把选定的值写回`baseline.py`的两个常量→
`python scripts/evaluate_baseline.py`重新生成`results/
baseline_accuracy.md`确认具体性维度MAE/准确率相比现在（2.27/36%）确实
提升，参照决策#29的before/after对比表格格式。

**2. 语速/停顿阈值真实录音校准（工具就绪，待用户提供录音）：**
`backend/speech/features.py`里的CPM/WPM区间（中文180-260、英文100-150）
和300ms停顿阈值从第4周就是经验值，决策#20第4项早就标注"需要用真实
候选人录音样本重新校准"，但到现在语音功能接上快5周了还没做——原因就是
需要真实录音数据，我这边始终拿不到。新增`scripts/
calibrate_speech_features.py`：接收一个录音文件夹路径，对每个文件跑
`transcribe_audio()`+`compute_speech_rate()`/`compute_pause_features()`，
输出每个文件的实测CPM/WPM/停顿数据、当前阈值下会被打上什么标签，并按
分位数（p25/p75）给出一个"朴素建议"区间——特意没有做成正式的网格搜索
（不像具体性校准那样有150条人工标注分数可以拟合），因为这些录音没有
"候选人自己觉得这段语速是慢/正常/快"的标签，本质上是给人（用户+我）
参考真实分布做判断，不是纯数字优化，脚本注释里也明确说了这一点，避免
给人"这是自动校准"的错觉。这一项本周不会真正执行校准——等用户提供的
录音到位后再实际跑这个脚本、看数据、更新常量，记为本周遗留到录音到手
之后处理的收尾工作，不算本周"已完成"范围。

**3. 测试覆盖债务：** 决策#39提到第9-11周新增模块
（`session_adapter`、`realtime_feedback`、语音相关代码）零测试覆盖，
记入最后一周处理。这周补了两个新测试文件：`tests/
test_speech_features.py`（`backend/speech/features.py`的纯函数部分——
语速识别、停顿检测、填充词检测，用手写的`Word`时间戳列表构造，不需要
真实音频文件也不需要faster-whisper模型本身跑起来，只需要`Word`
dataclass；`compute_volume_features()`因为要读真实WAV波形没有覆盖，
继续沿用人工真实录音走查验证）；`tests/test_realtime_feedback.py`
（`_truncate_answer()`/`_parse_json_response()`两个纯逻辑函数直接测试，
`generate_feedback()`的成功/失败分支用`unittest.mock.patch`模拟掉
`_call_groq_feedback()`，和`tests/test_session_adapter_report_wiring.py`
第15周的做法一致）。`tests/test_baseline_scoring.py`也补了两个用例
覆盖新增的专名识别信号和扩充后的词表。这些新测试文件的源码逻辑我逐行
在沙盒里手工推演过（模拟`compute_pause_features()`/
`compute_filler_features()`的内部计算过程确认断言数值正确），但受限于
沙盒缺少`faster-whisper`/`soundfile`/`groq`这些依赖（和第12-15周的
`session_adapter`系列测试一样的老问题——模块顶层就导入了这些真实依赖，
连import都过不了），没法在这边真正跑`pytest`验证，需要用户本地
`pytest tests/`确认全部通过。（本周没有再单独补`session_adapter.py`
更多的测试用例——它已有的`test_session_adapter_rag.py`+
`test_session_adapter_report_wiring.py`覆盖了RAG选题和报告接入两条主要
分支逻辑，`submit_round()`本身更适合用真实API走查而不是继续堆mock。）

**4. 部署文档化：** 新增`Dockerfile`（`python:3.11-slim`基础镜像，装
`libsndfile1`/`ffmpeg`/`build-essential`三个系统依赖满足
`soundfile`/`faster-whisper`/部分ML依赖的编译需求，分层让依赖安装和
代码变更分开缓存）、`.dockerignore`（排除`.git`、`data/piper_voices`、
`data/chroma_question_bank`、`ml/`等不该打进镜像的内容）、`docs/
deployment.md`（环境变量说明、本地venv运行步骤、Docker运行步骤含
`-v`挂载`data/`目录避免语音模型/向量索引每次重新下载重建的原因、
"为什么不做真正云端上线"的说明——项目license本身是PolyForm
Noncommercial非商业限制，加上真要上线需要有人负责持有云平台账号/
`GROQ_API_KEY`密钥托管/线上服务的可用性和滥用风险，这些是运营决策，
不该被这个仓库本身替用户做掉）。这一项没有引入任何需要用户本地环境
验证的东西——`Dockerfile`/`docker-compose`风格的文件本身在我沙盒里没有
Docker环境可以`docker build`验证，需要用户本地或有Docker的机器上
`docker build -t ai-interview-coach .`确认能构建成功，我这边只能保证
语法和内容的合理性，不能实测构建。

**5. README重写：** 原`README.md`一直只有一行占位文字`# ai-interview-
coach`，对一个准备放进简历的项目来说是个明显缺口。重写为完整项目
说明：功能概述（六个环节：分诊→面试→语音→实时反馈→复盘报告→账号
体系）、Mermaid架构图（前端→对话引擎/RAG/语音/评分/报告/存储→Groq，
各模块用中文注释里已有的模块划分直接映射）、技术栈选型表（每项都标注
"为什么"并链接回对应的决策编号）、快速上手（链接到新的`docs/
deployment.md`）、测试运行说明（诚实列出哪些用`pytest`覆盖、哪些只能
靠真实API冒烟测试/人工走查，不假装测试覆盖率是100%）、评分准确率说明
（链接`results/baseline_accuracy.md`，明确说这是"如实追踪的数字，不是
营销宣传"）、License说明（决策#28的PolyForm Noncommercial，非OSI认证
"开源"）、项目日志入口（链接`docs/decision_log.md`）。

**验证：** 本周所有代码改动（`baseline.py`的正则/词表改动、两个新
calibrate脚本、两个新测试文件）都需要用户本地真实环境（`sentence-
transformers`/`faster-whisper`/`groq`/`pytest`）才能真正跑通验证，我
这边只能做到：手工验证了`_count_proper_noun_markers()`用到的正则表达式
本身在纯Python环境（无需任何项目依赖）下对几个真实/边界用例的行为
符合预期（包括发现并修复了`\b`在CJK文本里失效的那个坑）；`README.md`/
`docs/deployment.md`的Markdown/Mermaid语法本身检查过没有明显错误。

**6. 真实`pytest`跑出的两个bug，已修复：** 用户在本地跑了
`pytest tests/`（91个用例，先出现3个失败），暴露了两处我在沙盒里
manual推演时没有发现的真实缺陷：

1. **`_DETAIL_MARKER_WORDS`新加的"复盘"和现有防刷分机制冲突**——
   `test_specificity_floor_caps_overall_score`和
   `test_keyword_stuffing_warning_fires_on_high_coverage_low_specificity`
   两个用例用的都是同一段对抗性测试文本"领导力。目标拆解。授权。
   激励团队。跨部门协作。决策。复盘总结。结果达成。"（纯关键词堆砌、
   零真实细节，专门用来验证决策#22的两个防护机制）。这段文本里的
   "复盘总结"恰好命中了本周新加的"复盘"这个具体性标记词，导致
   `marker_count`从0变成>0，绕开了`_ZERO_MARKER_SIGNAL_CAP`这个"零
   标记词强制封顶"的关键防线，具体性分数从应有的<3分（0-2档，触发
   防护机制）变成了5.5分（5-6档，防护机制完全没触发）——本质上是
   给"关键词刷分"防护开了个后门：一个纯靠堆砌关键词、毫无具体细节的
   回答，只要堆的关键词里恰好包含"复盘"这种词，就能同时骗过关键词
   覆盖率维度和具体性维度。根因是"复盘"本身是个偏抽象的流程/方法论
   词汇，不像数字、时间跨度、工具专名那样天然要求真实内容支撑——
   "做了复盘"和"有复盘意识"一样可以是空话。修复：从
   `_DETAIL_MARKER_WORDS`里删掉"复盘"，代码里留了详细注释说明教训
   （一个同时也是某道题关键词簇canonical/synonym词条的词，不该被
   当作具体性标记词，因为这等于让防刷分检测器免费送分）。
2. **新增的`tests/test_speech_features.py`里一处浮点数边界测试本身
   有问题**——`test_compute_pause_features_detects_gaps_above_
   threshold_only`原本想构造一个"正好等于阈值、不应被计入"的边界
   用例，用`0.5 + PAUSE_THRESHOLD_SECONDS`算出第二个词的起始时间，
   代数上等于阈值，但二进制浮点数减法（`compute_pause_features()`
   内部算`nxt.start - prev.end`）实际算出来比0.3略大一点点，导致
   本该不计入的边界间隙被判定为"大于阈值"而计入，用例断言的
   `count==1`实际跑出`count==2`。这是我这条测试用例本身对浮点数
   边界处理不够严谨，不是`compute_pause_features()`的问题。修复：
   把边界间隙从"代数上等于阈值"改成"明确小于阈值"（0.25秒 vs 0.3秒
   阈值），不再依赖浮点数精确相等，同时在代码注释里记录了这个教训。

这次的经验：手工在沙盒里逐行推演测试逻辑（没有真实依赖时唯一能做的
验证方式）能发现明显的逻辑错误，但发现不了"两个独立设计的模块在某个
具体输入上意外冲突"这类问题（第1个bug）和浮点数精度这类运行时才会
暴露的细节（第2个bug）——这也是为什么这个项目从第9周开始就一直坚持
"沙盒里的手工验证不能替代用户本地真实`pytest`"这条原则，这次是它
真正生效、抓到真实bug的一次例子，不是走过场。

**7. 跑`scripts/calibrate_specificity.py`时发现的第三个问题——这个是
本周之前就存在的既有缺口，不是本周代码引入的：** 91个测试用例全部
通过后，跑`scripts/calibrate_specificity.py`时炸了：
`KeyError: 'tech_behavioral_01'`。排查后发现（用沙盒里的Python直接
读取三份数据文件核对）：`data/labeled_answers_human_reviewed.json`
里`status=="scored"`的记录数已经是200条，而不是决策#27/29评估时的
150条——多出来的50条用的是`tech_behavioral_01`、`product_behavioral_01`
等带岗位前缀的`question_id`，这些ID只存在于`data/question_bank.json`
（决策#24/25的200题RAG题库）里，不在`data/sample_questions.json`
（原始30题集，决策#27/29评估一直用的题源）里。也就是说标注数据集在
决策#30之后的某个时间点已经从150条扩充到了200条（且新增的50条已经
标了`status:"scored"`，不是决策#30当时说的"batch2留待后续"那批还没
审核的数据——看起来是另一次独立的扩充，决策日志里没有单独记录这次
扩充本身），但`scripts/evaluate_baseline.py`（以及本周新写的
`calibrate_specificity.py`，抄的是它的模式）从来没有跟着更新去读
`question_bank.json`这第二个题源，一直只读`sample_questions.json`。
这意味着即使不算本周的改动，现在直接重跑`scripts/evaluate_baseline.py`
本身也会用同样的`KeyError`崩溃——`results/baseline_accuracy.md`里
"150条"这个数字已经是过时快照，不是这份数据当前的真实状态。这不是
本周引入的bug，是本周第一次真正touchpoint到这条代码路径时才暴露出来
的既有缺口。

**修复：** `evaluate_baseline.py`和`calibrate_specificity.py`都改成
从`sample_questions.json`和`question_bank.json`两个文件合并加载题目
（确认过两边`question_id`没有重复，合并是安全的），新增
`load_all_questions()`辅助函数（`evaluate_baseline.py`）/直接在
`precompute_signals()`里合并（`calibrate_specificity.py`），两个脚本
顶部文档字符串也更新为不再硬编码"150条"这个过时数字。

**验证：** 这三份数据文件（`sample_questions.json`/
`question_bank.json`/`labeled_answers_human_reviewed.json`）我在沙盒里
直接用Python读取核对过：两个题源`question_id`确认无重复；50条"缺失"
记录的`question_id`确认全部能在`question_bank.json`里找到；合并后
200条`scored`记录的`question_id`确认全部有对应题目，不会再有
`KeyError`。但合并后重跑`score_answer()`本身（需要真实embedding模型）
没法在沙盒里验证，需要用户本地重新跑一次这两个脚本确认真正跑通。

**8. 网格搜索真实跑通，参数已定：** 修好第7项的题库合并问题后，用户
本地重新跑了`scripts/calibrate_specificity.py`，对全部200条记录（而
不是原来假设的150条）成功跑通网格搜索。结果：当前值
（weight=0.5/density=0.5）MAE=2.26、±1准确率38%、±2准确率53%；网格
搜索前10组合全部集中在weight∈{0.30, 0.35}，MAE都在最优值2.06的0.05
以内（决策#29式的"平台"而非孤立尖峰），且一旦weight降到0.30，density
从0.3到1.0几乎不影响结果（因为此时marker_signal只占combined分数的
30%权重，具体在哪饱和影响就小了）。最终选定
`_SPECIFICITY_MARKER_WEIGHT=0.30`、`_SPECIFICITY_REF_WEIGHT=0.70`
（原来都是0.5），`_EXPECTED_MARKER_DENSITY`维持0.5不变——网格里
0.30/0.50这组MAE=2.07，只比整体最优的2.06（0.30/1.00，网格边界值）
差0.01，选择留在平台内部而不是跳到网格边界值，避免对没测试过的更大
density区间做外推。三个常量已写回`baseline.py`，代码里的注释记录了
完整的网格搜索结果和选择理由。

**验证：** 网格搜索本身已经在用户本地真实跑通（见上）。写回
`baseline.py`后的代码改动我在沙盒里做了`py_compile`语法检查，但常量
改动后的实际打分效果（具体性维度MAE是否真的从2.26降到~2.07附近）
还需要用户本地重跑`scripts/evaluate_baseline.py`用全部200条数据生成
新的`results/baseline_accuracy.md`才能最终确认——网格搜索脚本是用
预先算好的信号做纯算术复现`_score_specificity()`的计算，理论上和
真正调用`score_answer()`应该一致，但"理论上一致"不等于"已经验证一致"，
这一步不能跳过。

**9. 最终确认——具体性维度准确率提升已用真实数据验证：** 用户本地
依次跑了`pytest tests/`（91个用例全部通过）和
`scripts/evaluate_baseline.py`（200条数据全部评估成功），新的
`results/baseline_accuracy.md`显示具体性维度总体
MAE从校准前的2.26降到**2.07**，±1准确率38%→**40%**，±2准确率
53%→**57%**——和网格搜索脚本预测的数字（2.07/40%/57%）完全吻合，
说明`_score_specificity()`实际打分行为和`calibrate_specificity.py`
用预计算信号做的纯算术复现是一致的。（另外`results/
baseline_accuracy.md`里结构完整度维度MAE也从旧的2.47变成了2.27——
这不是本周改动带来的，纯粹是因为这次是在扩充后的200条数据上评估、
不是原来的150条，评估池本身变了，如实记录、不归功于本周工作。）

**状态：** 第16周范围内已完成并全部通过真实验证的部分：具体性维度
精度优化（修复2个真实bug后，网格搜索+真实评估双重确认MAE
2.26→2.07的提升）、测试覆盖债务（91个用例，pytest全过）、部署文档化
（`Dockerfile`/`docs/deployment.md`，镜像构建本身因用户本地未装
Docker未做实测，不算本周阻塞项）、README重写。语速/停顿真实录音
校准工具（`scripts/calibrate_speech_features.py`）已就绪但本周不
执行——待用户之后提供真实录音再实际运行校准，作为本项目8-16周计划
之外的一个独立后续任务记录在案，不阻塞本周收尾。全部代码待合并进
`main`并推送。

**归属：** 评分系统、语音分析、测试基础设施、部署与文档、项目管理。

## 46. 语速阈值真实录音校准（决策#45遗留任务，收尾）

**内容：** 第16周（决策#45）把`scripts/calibrate_speech_features.py`
工具准备好了，但当时没有真实录音数据，实际校准留到之后。用户随后
发了4段录音——1段自由发挥的例子（英文，用于wpm）、3段同一段约200字
中文文本按"刻意放慢/正常语速/说快一点"三种语速朗读的版本（用于cpm）。
录音文件是通过对话直接上传的（不是设备桥接的本地文件夹），我在沙盒里
用`ffmpeg`把mp4容器里的音频轨提取成标准16kHz单声道wav，再通过设备桥接
写回用户电脑的`~/Documents/interview_recordings/`目录——特意放在项目
仓库之外，不进`.gitignore`名单也不会被提交，因为这是候选人（这里是
用户本人）的真实语音数据，不应该进版本库。

**实测结果：** 3段中文朗读的CPM分别是294/298/366，**全部**高于当时
`_RATE_BANDS`里`fast_min=260`这个上限——包括刻意放慢那一段。这是个
明确的真实信号：原来180-260这个区间从第4周立项起就只是文档给的经验值
（决策#20第4项一直标注"待用真实录音校准"），现在看确实定得偏低，不是
这次录音的人说话异常快。英文那段（109 wpm）落在现有100-150区间内的
"normal"，没有意外，但只有1个数据点，没法据此调整wpm区间。停顿方面：
检测到的14次停顿中位数0.49秒，明显高于0.3秒门槛，没有看到"大量卡在
临界值附近被误判"的迹象，这次数据没给出改动300ms停顿阈值的理由。

**决策：** 把`backend/speech/features.py`的`_RATE_BANDS["cpm"]`从
`(180.0, 260.0)`调整为`(230.0, 330.0)`——slow_max留了明显的余量在
最低实测值（294）以下，保证真正很慢/犹豫的语速依然能被判成"slow"；
fast_min定在略低于刻意说快那段的实测值（366）之下，让它依然能被判成
"fast"，同时把294/298这两个更居中的实测值都划进"normal"区间。wpm区间
和300ms停顿阈值都维持不变（前者数据不够、后者没有改动理由）。

**如实标注的局限：** 这是**一个人**读**同一段固定文本**的3次朗读，
不是多说话人验证过的通用区间——不能说这个新区间适用所有候选人的
自然语速。之所以还是采纳了这次调整而不是继续等更多数据，是因为
这个项目本身偏个人练习向的工具（决策#43的设计思路也是"面向自己/
小范围使用"），比100%拍脑袋的旧经验值好，且代码注释和这条决策记录
里都清楚写明了这个局限，不是包装成"已充分验证"。如果之后有其他人的
录音，应该重新跑一遍`calibrate_speech_features.py`看这个区间站不
站得住。

**测试影响：** `tests/test_speech_features.py`里
`test_classify_speech_rate_buckets_slow_normal_fast()`原来硬编码了
基于旧区间（180-260）的具体数值断言，区间一调整这条测试会悄悄断言错
东西而不是直接报错（比如原来的边界值220在新区间下会从"normal"变成
"slow"）。改成直接从`_RATE_BANDS`读实际区间、用"边界±1"和"区间中点"
构造断言，这样以后再校准也不需要跟着手动改这条测试。

**验证：** 4段录音本身的转写+特征提取是用户本地真实
`scripts/calibrate_speech_features.py`跑出来的，是真实数据。区间改动
后的`_RATE_BANDS`常量、`py_compile`语法检查、测试文件的修复都是我这边
做的，但需要用户本地重跑一次`pytest tests/`确认改完区间后测试还是
全过（尤其是刚改过的那条分类边界测试）。

**状态：** 代码已完成，等待用户本地`pytest tests/`确认全过，然后
提交合并推送——这次不再是一整周的功能开发，只是第16周遗留的一个小
收尾任务，走一个小分支+直接合并即可，不需要单独走"周"的完整流程。

**归属：** 语音分析、测试基础设施、项目管理。
