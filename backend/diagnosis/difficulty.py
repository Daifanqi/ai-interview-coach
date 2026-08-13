"""
AI 面试系统 · 智能分诊模块 —— 难度计算与UI辅助函数
配合 theme.css 中的 .difficulty-badge / .persona-tag 样式使用
"""
from typing import Literal

# ---------- 基础值：经验水平 ----------
EXPERIENCE_BASE = {
    "实习生": 1,
    "应届": 2,
    "1-3年": 3,
    "3年以上": 4,
}

# ---------- 调整值 & 人设：面试阶段 ----------
STAGE_CONFIG = {
    "HR初筛":  {"adjustment": -1, "persona": "亲和型",   "persona_css": "friendly"},
    "技术面①": {"adjustment": 0,  "persona": "技术挖掘型", "persona_css": "technical"},
    "技术面②": {"adjustment": 1,  "persona": "技术挖掘型", "persona_css": "technical"},
    "终面":    {"adjustment": 1,  "persona": "严格型",   "persona_css": "strict"},
}

Experience = Literal["实习生", "应届", "1-3年", "3年以上"]
Stage = Literal["HR初筛", "技术面①", "技术面②", "终面"]


def compute_difficulty(experience: Experience, stage: Stage) -> dict:
    """
    计算最终面试难度。
    最终难度 = clamp(基础值 + 调整值, 1, 5)
    返回值中的 was_clamped 用于埋点/日志，追踪哪些组合触发了边界钳制
    （目前已知唯一会触发下界钳制的组合：实习生 + HR初筛，原始和为 0）。
    """
    if experience not in EXPERIENCE_BASE:
        raise ValueError(f"未知经验水平: {experience}，请从 {list(EXPERIENCE_BASE)} 中选择")
    if stage not in STAGE_CONFIG:
        raise ValueError(f"未知面试阶段: {stage}，请从 {list(STAGE_CONFIG)} 中选择")

    base = EXPERIENCE_BASE[experience]
    cfg = STAGE_CONFIG[stage]
    raw_sum = base + cfg["adjustment"]
    final_difficulty = max(1, min(5, raw_sum))

    return {
        "experience": experience,
        "stage": stage,
        "base": base,
        "adjustment": cfg["adjustment"],
        "raw_sum": raw_sum,
        "final_difficulty": final_difficulty,
        "was_clamped": raw_sum != final_difficulty,
        "persona": cfg["persona"],
        "persona_css": cfg["persona_css"],
    }


# ---------- UI 辅助：生成可直接塞进 st.markdown(..., unsafe_allow_html=True) 的 HTML ----------
def difficulty_badge_html(level: int) -> str:
    # Deferred import: t() pulls in frontend.strings (and therefore streamlit's
    # session_state), which backend modules otherwise have no reason to depend
    # on. Importing here -- rather than at module load time -- keeps every
    # other function in this file usable outside a running Streamlit script
    # (e.g. the __main__ self-check below), and only pays the frontend
    # dependency when this specific HTML helper is actually called.
    from frontend.strings import t

    return f'<span class="difficulty-badge difficulty-{level}">{t("difficulty_word")} {level}</span>'


def persona_tag_html(persona_css: str, persona_label: str) -> str:
    return f'<span class="persona-tag persona-{persona_css}">{persona_label}</span>'


if __name__ == "__main__":
    # 自检：打印全部 16 种组合，人工核对与文档中的对照表是否一致
    for exp in EXPERIENCE_BASE:
        for stage in STAGE_CONFIG:
            r = compute_difficulty(exp, stage)
            flag = "  <== 触发钳制" if r["was_clamped"] else ""
            print(f"{exp:>5} + {stage:<6} | base={r['base']} adj={r['adjustment']:+d} "
                  f"raw={r['raw_sum']} final={r['final_difficulty']} persona={r['persona']}{flag}")