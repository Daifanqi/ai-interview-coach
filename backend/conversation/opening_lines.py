"""
Interviewer opening lines: 3 personas x 2 languages, copied verbatim from
docs/persona_prompts_design.md section 3.

The opening line is delivered as the interviewer's first conversational
turn, before the first real question -- it briefly sets the scene (role,
language, roughly what to expect, that follow-ups are normal) so the
candidate isn't dropped into questioning cold. It must stay in-character:
it does not mention scoring, follow-up round limits, or any other internal
mechanism (same "never reveal internal logic" rule as the System Prompts
in backend/conversation/prompts/).
"""
from __future__ import annotations

from backend.conversation.prompts import Language, Persona

_OPENING_LINES: dict[tuple[Persona, Language], str] = {
    (Persona.FRIENDLY, "zh"): (
        "你好呀，很高兴今天能和你聊聊～接下来这段时间我会扮演HR面试官，"
        "跟你做一次初面沟通，整个过程会用中文进行。我们会聊聊你的背景、"
        "经历，还有一些我比较感兴趣的话题，不会有特别刁钻的问题，你可以"
        "把这当成一次轻松的双向了解。每聊完一个话题，我可能会顺着你说的"
        "内容再多问一两句，这个很正常，就是想多了解一些细节，不代表你哪里"
        "说得不好，放轻松就好。准备好了我们就开始吧？"
    ),
    (Persona.FRIENDLY, "en"): (
        "Hi there, great to have you today! I'll be playing the role of an "
        "HR interviewer for this first-round conversation, and we'll do the "
        "whole thing in English. We'll talk about your background, your "
        "experience, and a few things I'm genuinely curious about — nothing "
        "designed to trip you up, so feel free to treat this as a relaxed, "
        "two-way conversation. After each topic, I might ask a follow-up "
        "question or two based on what you shared — that's completely "
        "normal, it just means I want to hear a bit more detail, not that "
        "anything was wrong with your answer. Take your time, and whenever "
        "you're ready, let's get started."
    ),
    (Persona.TECHNICAL, "zh"): (
        "好，我们开始吧。接下来我会扮演技术面试官，跟你进行一次技术面，"
        "全程用中文交流。我们会聊到一些具体的项目、技术方案和实现细节，"
        "我会比较关注你对原理和权衡的理解，所以每个话题聊完之后，我大概率"
        "会针对你提到的某个点再深挖一下，这是技术面正常的节奏，不用紧张，"
        "遇到不确定的地方可以坦诚地讲你当时的思考过程，这个我会很感兴趣。"
        "准备好了吗？我们开始第一个问题。"
    ),
    (Persona.TECHNICAL, "en"): (
        "Alright, let's get into it. I'll be playing the interviewer for a "
        "technical round, and we'll do this fully in English. We'll dig into "
        "specific projects, technical decisions, and implementation details "
        "— I'm genuinely interested in the reasoning and trade-offs behind "
        "what you built, so after most answers I'll probably follow up on "
        "something specific you mentioned. That's just the normal rhythm of "
        "a technical interview, nothing to worry about — if you're not 100% "
        "sure about something, it's fine to just walk me through your "
        "thinking at the time, that's actually what I care about most. "
        "Ready? Let's start with the first question."
    ),
    (Persona.STRICT, "zh"): (
        "你好，我是今天负责终面的面试官。这一轮面试会比较全面，会覆盖技术"
        "判断、决策过程、协作影响等多个维度，不是为了出难题，而是希望更"
        "完整地了解你处理问题的方式。整个过程用中文进行，每个话题我可能会"
        "追问几轮，这是终面的常规流程，目的是把情况了解得更全面一些，你"
        "按照真实情况回答就可以。我们开始吧。"
    ),
    (Persona.STRICT, "en"): (
        "Hello, I'll be conducting the final round today. This session is "
        "comprehensive by design — we'll cover technical judgment, "
        "decision-making process, and cross-team impact, among other "
        "dimensions. That's not meant to make things harder, just to get a "
        "fuller picture of how you approach problems. We'll conduct this "
        "entirely in English, and for most topics I'll follow up a few "
        "times — that's standard for a final round, simply to understand "
        "the full picture. Just answer as accurately as you can. Let's "
        "begin."
    ),
}


def get_opening_line(persona: Persona, language: Language) -> str:
    """Return the interviewer's opening line for this persona/language pair."""
    return _OPENING_LINES[(persona, language)]
