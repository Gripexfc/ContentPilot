from __future__ import annotations

import json
from pathlib import Path

import pytest

from creatoros.services.easel_validation import validate_platform


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "vendor" / "easel" / "skills"


def _meta(path: Path, value: dict) -> None:
    (path / "meta.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_wechat_runs_real_html_and_ai_gates(tmp_path: Path) -> None:
    text = (
        "昨天我把一篇旧稿重新排了一遍。结果比预想中简单。\n\n"
        "先删掉几段空话，再把一个真实案例放到开头。读者看完就知道这篇文章要解决什么。\n\n"
        "中间的步骤不长，却必须写清楚。一个数字也不能靠猜。\n\n"
        "最后我留下一句很短的提醒：先核验，再发布。"
    )
    (tmp_path / "article.md").write_text(text, encoding="utf-8")
    (tmp_path / "article.html").write_text(
        '<section><p><span leaf="">昨天我把一篇旧稿重新排了一遍。</span></p>'
        '<p><span leaf="">先删掉空话，再写清楚真实案例。</span></p></section>',
        encoding="utf-8",
    )
    _meta(tmp_path, {"title": "把旧稿重新排一遍", "digest": "一篇可复制的排版经验"})

    report = validate_platform("wechat-oa", tmp_path, SKILLS)

    assert report["status"] == "passed", report
    assert report["primary_text"] == "article.md"
    assert "先核验" in report["copy_text"]
    assert {c["name"] for c in report["checks"]} >= {"wechat_html", "wechat_ai_score"}


def test_wechat_html_warning_is_blocking(tmp_path: Path) -> None:
    (tmp_path / "article.md").write_text("一段文章。", encoding="utf-8")
    (tmp_path / "article.html").write_text(
        '<section><p><span leaf="">中文, 半角标点</span></p></section>',
        encoding="utf-8",
    )
    _meta(tmp_path, {"title": "标题", "digest": "摘要"})

    report = validate_platform("wechat", tmp_path, SKILLS)

    assert report["status"] == "blocked"
    check = next(c for c in report["checks"] if c["name"] == "wechat_html")
    assert check["status"] == "failed"


def test_douyin_script_runs_wordcount_gate(tmp_path: Path) -> None:
    (tmp_path / "script.md").write_text("# 抖音脚本\n\n三段镜头脚本。", encoding="utf-8")
    caption = "这是一个用于测试的抖音发布配文。" * 15
    meta = {
        "title": "三步写出好脚本",
        "duration_seconds": 12,
        "hooks": [
            {"text": "先看这一步", "score": 18},
            {"text": "别再这样写", "score": 17},
            {"text": "给你一个方法", "score": 16},
        ],
        "shots": [
            {"start": 0, "end": 4, "narration": "第一步先说清楚问题在哪里", "subtitle": "先说问题", "visual": "人物出镜"},
            {"start": 4, "end": 8, "narration": "第二步给出一条具体可行的办法", "subtitle": "给出办法", "visual": "展示步骤"},
            {"start": 8, "end": 12, "narration": "第三步现在就提醒观众马上行动吧马上开始", "subtitle": "马上行动", "visual": "镜头收束"},
        ],
        "caption": caption,
        "hashtags": ["#写作", "#短视频", "#内容创作"],
        "quality_score": 85,
    }
    _meta(tmp_path, meta)

    report = validate_platform("douyin", tmp_path, SKILLS)

    assert report["status"] == "passed", report
    assert report["media_kind"] == "script"
    assert {c["name"] for c in report["checks"]} >= {"douyin_hooks", "douyin_shots", "douyin_wordcount"}


def test_unsafe_symlink_blocks_before_skill_validation(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-easel-validation.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "meta.json").symlink_to(outside)

    report = validate_platform("douyin", tmp_path, SKILLS)

    assert report["status"] == "blocked"
    assert any(c["name"] == "artifact_safety" and c["status"] == "failed" for c in report["checks"])


@pytest.mark.skipif(__import__("importlib.util").util.find_spec("PIL") is None, reason="Pillow is optional in the test interpreter")
def test_xhs_runs_meta_and_card_audit(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    cards = []
    for index, kind in enumerate(("cover", "content", "ending"), 1):
        rel = f"images/card_{index}.png"
        image_path = tmp_path / rel
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1080, 1440), (245, 240, 230))
        draw = ImageDraw.Draw(image)
        # card_audit measures horizontal edge density (x-axis differences),
        # so use repeated vertical strokes that fill most of the canvas.
        for x in range(80, 1000, 6):
            draw.rectangle((x, 80, x + 2, 1370), fill=(30, 30, 30))
        image.save(image_path, format="PNG")
        cards.append({"page": index, "type": kind, "title": kind, "content": "一条具体信息", "synthesis_strategy": "html_card"})
    (tmp_path / "note.md").write_text("## 一条笔记\n\n这是正文。", encoding="utf-8")
    _meta(tmp_path, {
        "title": "三步做好早餐",
        "platform": "小红书",
        "created_at": "2026-10-07T10:00:00+08:00",
        "caption": "这是用于测试的小红书发布配文。" * 12,
        "hashtags": ["#旅行", "#早餐", "#攻略", "#大连", "#预算"],
        "post_format": "image",
        "card_count": 3,
        "cards": cards,
        "images": ["images/card_1.png", "images/card_2.png", "images/card_3.png"],
    })

    report = validate_platform("xiaohongshu", tmp_path, SKILLS)

    assert report["status"] == "passed", report
    assert report["primary_text"] == "note.md"
    assert any(c["name"] == "card_audit" and c["status"] == "passed" for c in report["checks"])
