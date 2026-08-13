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
