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

**How to apply:** Not yet scheduled -- deferred to when interviewer persona
prompts are actually written. When that work happens, the `终面` persona
prompt must be written around "broader coverage + deeper follow-ups," and
must not be written as "ask harder/more advanced questions." No change is
needed to `difficulty.py` or `matcher.py` for this decision; it only
constrains future prompt-writing.

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
