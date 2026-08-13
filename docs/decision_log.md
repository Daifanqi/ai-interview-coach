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
