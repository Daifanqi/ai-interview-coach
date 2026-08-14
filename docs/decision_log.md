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
