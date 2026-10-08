from __future__ import annotations

from typing import Any, Dict


def generate_content(*, title: str, input_text: str, profile: Dict[str, Any], brief: Dict[str, Any],
                     memories: list[Dict[str, Any]] | None = None) -> Dict[str, Dict[str, Any]]:
    """Create an offline, deterministic first draft for the vertical slice.

    This adapter deliberately makes no external call and never claims that a
    platform draft has been published. It is the seam for a future LLM adapter.
    """
    voice = profile.get("voice", {}) or {}
    tone = voice.get("tone", "清晰、具体")
    reader = brief.get("reader_problem") or "目标读者正在寻找更清晰的判断和下一步行动"
    angle = brief.get("author_angle") or "从作者经验出发，给出可核验的拆解"
    seed = input_text.strip() or title
    applied = [str(item.get("statement") or "").strip() for item in (memories or []) if str(item.get("statement") or "").strip()]
    memory_note = f" 已采纳的写作偏好：{'；'.join(applied)}。" if applied else ""
    shared = f"围绕“{title}”，先把问题拆成事实、判断和行动三层。{memory_note}"

    return {
        "wechat": {
            "generation_kind": "demo_deterministic",
            "title_candidates": [title, f"{title}：先把这三个问题想清楚"],
            "title": title,
            "summary": f"{shared} 这篇长文会回答：{reader}。",
            "sections": [
                {"heading": "先确认发生了什么", "body": f"素材入口：{seed}\n当前只保留待核验事实，不把推测写成结论。"},
                {"heading": "再说作者怎么看", "body": f"作者角度：{angle}\n表达基调：{tone}。"},
                {"heading": "最后给出可执行动作", "body": "把下一步拆成一个今天可以完成的小实验，并记录结果。"},
            ],
            "fact_citations": [],
            "cover_brief": "留白、一个明确的主题词、避免暗示已经发布或取得结果。",
            "body_image_briefs": ["事实层示意图", "判断层对照图", "行动层清单图"],
            "ending_policy": "natural",
            "applied_memory_ids": [str(item["id"]) for item in (memories or [])],
            "memory_guidance": applied,
        },
        "xiaohongshu": {
            "generation_kind": "demo_deterministic",
            "title_candidates": [f"{title}｜先别急着下结论", f"把{title}拆成3步"],
            "title": f"{title}｜先别急着下结论",
            "cover_copy": f"{title}\n3步拆清楚",
            "cards": [
                {"page": 1, "text": f"{title}\n先把问题摆到桌面上"},
                {"page": 2, "text": "01 事实是什么？\n只写有来源或待核验的内容。"},
                {"page": 3, "text": "02 我怎么看？\n把经验和判断分开。"},
                {"page": 4, "text": "03 下一步做什么？\n用一个小实验验证。"},
            ],
            "body": f"{shared}\n\n适合移动端快速阅读，每段只保留一个动作。",
            "topics": ["内容创作", "选题方法", "个人经验"],
            "image_prompts": ["简洁信息卡，突出事实、判断、行动三列", "移动端竖版留白排版"],
            "applied_memory_ids": [str(item["id"]) for item in (memories or [])],
            "memory_guidance": applied,
        },
        "douyin": {
            "generation_kind": "demo_deterministic",
            "title": f"{title}：3步拆清楚",
            "hook_3s": f"如果你也在纠结“{title}”，先别急着做结论。",
            "voiceover": f"{shared}第一步，确认事实；第二步，说明你的判断；第三步，安排一个能验证的动作。素材里还有待核验部分，发布前要补齐来源。",
            "shots": [
                {"scene": 1, "seconds": 3, "visual": "镜头正面，屏幕出现主题词", "audio": "3秒开场"},
                {"scene": 2, "seconds": 8, "visual": "事实、判断、行动三个词依次出现", "audio": "口播第一、二步"},
                {"scene": 3, "seconds": 6, "visual": "展示一个待验证的小实验清单", "audio": "口播第三步"},
            ],
            "subtitle": "事实｜判断｜行动\n来源待核验，结论要留证据",
            "visual_notes": "优先使用作者真实素材；当前只生成脚本，不代表已渲染视频。",
            "broll_suggestions": ["主题相关的公开资料画面", "作者工作台或笔记特写", "实验结果记录"],
            "voice_and_music": {"voice": "自然、克制", "music": "低存在感节奏，无版权承诺"},
            "video_generation_flow": "可选：图片/卡片→独立媒体模块→FFmpeg；本阶段不执行渲染。",
            "applied_memory_ids": [str(item["id"]) for item in (memories or [])],
            "memory_guidance": applied,
        },
    }
