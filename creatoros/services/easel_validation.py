"""Host-side validation for files produced by Easel platform skills.

The Agent's receipt is not evidence that a file was rendered or checked.  This
module opens media and executes the checked-in Easel validators independently.
It never installs dependencies, calls a model, or publishes content.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def validate_platform(platform: str, directory: Path, skills_root: Path, output_kind: str = "standard") -> dict[str, Any]:
    """Return a relative-path validation receipt; any failed check blocks it.

    ``skills_root`` accepts the Easel ``skills`` directory (openclaw/shared) or
    the runtime's flat ``workspace/skills`` directory. ``primary_text`` points
    to the editable source, while ``copy_text`` contains only publishing copy.
    """
    return _Validator(platform, directory, skills_root, output_kind).validate()


class _Validator:
    def __init__(self, platform: str, directory: Path, skills_root: Path, output_kind: str):
        self.platform = "wechat-oa" if platform in {"wechat", "公众号"} else platform
        self.directory = Path(directory).absolute()
        self.base = self.directory.resolve()
        self.root = self.base
        self.skills = Path(skills_root).resolve()
        self.kind = output_kind
        self.checks: list[dict[str, Any]] = []
        self.missing: list[str] = []
        self.artifacts: list[str] = []
        self.primary = ""
        self.copy_text = ""
        self.media_kind = {"xiaohongshu": "image", "wechat-oa": "article", "douyin": "script"}.get(self.platform, "unknown")
        self.logdir: Path | None = None

    def add(self, name: str, passed: bool, detail: str, **extra: Any) -> bool:
        self.checks.append({"name": name, "status": "passed" if passed else "failed", "detail": self.clean(detail), **extra})
        return passed

    def clean(self, text: str) -> str:
        return str(text).replace(str(self.root), ".").replace(str(self.base), ".").replace(str(self.skills), "<skills>")

    def result(self) -> dict[str, Any]:
        return {"status": "passed" if self.checks and all(x["status"] == "passed" for x in self.checks) else "blocked",
                "checks": self.checks, "missing": list(dict.fromkeys(self.missing)),
                "artifacts": sorted(set(self.artifacts)), "primary_text": self.primary,
                "copy_text": self.copy_text, "media_kind": self.media_kind}

    def file(self, relative: Any) -> Path | None:
        if not isinstance(relative, str) or not relative.strip():
            self.add("artifact_path", False, "文件路径必须是非空相对路径")
            return None
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or rel.parts[0] == ".validation":
            self.add("artifact_path", False, f"不允许的产物路径：{relative}")
            return None
        path = self.root / rel
        try:
            path.resolve().relative_to(self.root)
            cursor = path
            while cursor != self.root:
                if cursor.is_symlink():
                    raise ValueError("不允许符号链接")
                cursor = cursor.parent
            if not path.is_file() or not path.stat().st_size:
                self.missing.append(relative)
                raise ValueError("文件缺失或为空")
        except (ValueError, OSError) as exc:
            self.add("artifact_file", False, f"{relative}：{exc}")
            return None
        return path

    def scan(self) -> bool:
        if self.directory.is_symlink() or not self.directory.is_dir():
            return self.add("directory", False, "产物目录不存在或为符号链接")
        problems = []
        try:
            for base, dirs, files in os.walk(self.root, followlinks=False):
                for name in dirs + files:
                    path = Path(base) / name
                    rel = path.relative_to(self.root)
                    if path.is_symlink():
                        problems.append(f"{rel} 是符号链接")
                        continue
                    path.resolve().relative_to(self.root)
                    if path.is_file() and ".validation" not in rel.parts:
                        if path.stat().st_size == 0:
                            problems.append(f"{rel} 为空")
                        self.artifacts.append(rel.as_posix())
                    elif name in files and not path.is_file():
                        problems.append(f"{rel} 不是普通文件")
        except (OSError, ValueError) as exc:
            problems.append(str(exc))
        return self.add("artifact_safety", not problems, "；".join(problems) if problems else "产物均为目录内非空普通文件，无符号链接")

    def _project_artifacts(self) -> list[str]:
        """Return files inside the selected Easel project, relative to it."""
        try:
            prefix = self.root.relative_to(self.base)
        except ValueError:
            return []
        out = []
        for relative in self.artifacts:
            path = Path(relative)
            if prefix == Path(".") or path.is_relative_to(prefix):
                out.append(path.relative_to(prefix).as_posix() if prefix != Path(".") else path.as_posix())
        return out

    def _to_base(self, relative: str) -> str:
        """Convert a project-relative artifact path to a workbench path."""
        prefix = self.root.relative_to(self.base)
        path = Path(relative)
        return (prefix / path).as_posix() if prefix != Path(".") else path.as_posix()

    def _select_project_root(self) -> None:
        """Find the dynamic project directory used by the Easel output spec."""
        candidates = {self.base}
        for relative in self.artifacts:
            path = self.base / relative
            if path.name == "meta.json" or path.name == "article.md":
                candidates.add(path.parent)
        def score(path: Path) -> tuple[int, int]:
            names = {item.name.lower() for item in path.iterdir()} if path.is_dir() else set()
            html = any(name.endswith((".html", ".htm")) for name in names)
            md = any(name.endswith((".md", ".markdown")) for name in names)
            if self.platform == "xiaohongshu":
                value = int("meta.json" in names) + int(md) + int(any(name.startswith("card_") and name.endswith(".png") for name in names))
            elif self.platform == "douyin":
                value = int("meta.json" in names) + int(md) + int(any(name.endswith(".mp4") for name in names))
            else:
                value = int("article.md" in names) + int(html)
            try:
                depth = len(path.relative_to(self.base).parts)
            except ValueError:
                depth = 999
            return value, -depth
        self.root = max(candidates, key=score)

    def read(self, relative: str) -> str | None:
        path = self.file(relative)
        if path is None:
            return None
        try:
            value = path.read_text(encoding="utf-8")
            if not value.strip():
                raise ValueError("文本仅含空白")
            return value
        except (OSError, UnicodeError, ValueError) as exc:
            self.add("text_file", False, f"{relative}：{exc}")
            return None

    def metadata(self) -> dict[str, Any] | None:
        value = self.read("meta.json")
        if value is None:
            return None
        try:
            data = json.loads(value)
            if not isinstance(data, dict):
                raise ValueError("顶层必须是 JSON 对象")
            return data
        except (ValueError, TypeError) as exc:
            self.add("meta_json", False, f"meta.json 无效：{exc}")
            return None

    def script(self, skill: str, filename: str) -> Path:
        if skill == "shared":
            return self.skills / "shared" / "scripts" / filename
        base = self.skills / "openclaw" if (self.skills / "openclaw").is_dir() else self.skills
        return base / skill / "scripts" / filename

    def run(self, name: str, script: Path | None, args: list[str], *, stdin: str | None = None,
            warnings_fail: bool = False, executable: str | None = None) -> dict[str, Any] | None:
        logname = f"{len(self.checks) + 1:02d}-{re.sub('[^a-zA-Z0-9_-]', '-', name)}.log"
        log = self.logdir / logname
        command = [executable, *args] if executable else [sys.executable, str(script), *args]
        try:
            if script is not None and not script.is_file():
                raise FileNotFoundError(f"官方校验脚本缺失：{script}")
            proc = subprocess.run(command, input=stdin, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=self.root, timeout=60, check=False)
            output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""))[:50000]
            passed = proc.returncode == 0 and not (warnings_fail and re.search(r"\bWARN(?:ING)?\b", output))
            detail = f"退出码 {proc.returncode}；" + (output.strip()[-1200:] or "无输出")
        except (OSError, subprocess.SubprocessError) as exc:
            passed, output, detail = False, str(exc), str(exc)
        log.write_text(self.clean(output or detail) + "\n", encoding="utf-8")
        self.add(name, passed, detail, log=f".validation/{logname}")
        if not passed:
            return None
        try:
            return json.loads(output)
        except (ValueError, TypeError):
            return {}

    def image(self, relative: Any, *, size: tuple[int, int] | None = None) -> bool:
        path = self.file(relative)
        if path is None:
            return False
        try:
            from PIL import Image
            with Image.open(path) as im:
                if im.format not in {"PNG", "JPEG"}:
                    raise ValueError("只接受实际 PNG 或 JPEG 文件")
                im.verify()
            with Image.open(path) as im:
                im.load()
                width, height = im.size
                if width <= 0 or height <= 0:
                    raise ValueError("图片尺寸无效")
                if size and (width, height) != size:
                    raise ValueError(f"尺寸应为 {size[0]}×{size[1]}（3:4），实际为 {width}×{height}")
            return self.add("image_decode", True, f"{relative} 已解码：{width}×{height}")
        except (ImportError, OSError, ValueError, SyntaxError) as exc:
            return self.add("image_decode", False, f"{relative}：{exc}")

    @staticmethod
    def number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def xhs(self, meta: dict[str, Any]) -> None:
        notes = [p for p in self._project_artifacts() if Path(p).parent == Path(".") and Path(p).suffix.lower() in {".md", ".markdown"}]
        note = "note.md" if "note.md" in notes else notes[0] if len(notes) == 1 else "note.md"
        text = self.read(note)
        if text:
            self.primary = self._to_base(note)
        title, caption, tags = meta.get("title"), meta.get("caption"), meta.get("hashtags")
        if isinstance(title, str) and isinstance(caption, str) and isinstance(tags, list) and all(isinstance(t, str) for t in tags):
            self.copy_text = title.strip() + "\n\n" + caption.strip() + "\n\n" + " ".join(tags)
        self.run("xhs_meta", self.script("xhs-note-creator", "validate_meta.py"), [str(self.root / "meta.json")])
        self.add("xhs_title", isinstance(title, str) and 1 <= len(title.strip()) <= 20, "小红书发布标题必须为 1–20 字")
        if meta.get("post_format", "image") != "image":
            self.media_kind = "video"
            self.video(meta)
            return
        cards, images = meta.get("cards"), meta.get("images")
        valid = isinstance(cards, list) and all(isinstance(c, dict) for c in cards) and isinstance(images, list) and 3 <= len(images) <= 9 and len(images) == len(cards)
        if not self.add("xhs_images", valid, "meta.images 必须按卡片顺序列出每张实际图片，数量与 cards 一致且为 3–9 张"):
            return
        if not self.add("xhs_unique_images", len(set(str(p) for p in images)) == len(images), "每张卡片必须有独立图片文件"):
            return
        for card, relative in zip(cards, images):
            if self.image(relative, size=(1080, 1440)) and card.get("synthesis_strategy", "html_card") == "html_card":
                self.run("card_audit", self.script("card-design", "card_audit.py"), ["audit", "-f", str(self.root / relative), "--json"])

    def wechat(self, meta: dict[str, Any]) -> None:
        project_files = self._project_artifacts()
        md_candidates = [p for p in project_files if Path(p).parent == Path(".") and Path(p).suffix.lower() in {".md", ".markdown"} and Path(p).name != "meta.json"]
        article_name = "article.md" if "article.md" in md_candidates else (md_candidates[0] if md_candidates else "article.md")
        article = self.read(article_name)
        html_candidates = [p for p in project_files if Path(p).parent == Path(".") and Path(p).suffix.lower() in {".html", ".htm"}]
        html_name = next((name for name in ("article.html", "preview.html") if name in html_candidates), html_candidates[0] if html_candidates else "article.html")
        html = self.read(html_name)
        if article:
            self.primary, self.copy_text = self._to_base(article_name), article.strip()
        title = meta.get("title")
        digest = meta.get("digest", meta.get("summary"))
        self.add("wechat_title", isinstance(title, str) and 1 <= len(title.strip()) <= 64, "公众号标题必须为 1–64 字")
        self.add("wechat_digest", isinstance(digest, str) and 1 <= len(digest.strip()) <= 120, "公众号摘要必须为 1–120 字")
        if article:
            self.run("wechat_ai_score", self.script("skill-wechat-publisher", "ai_score.py"), [str(self.root / article_name), "--threshold", "45", "--json"])
        if html:
            clean_section = bool(re.match(r"\s*<section(?:\s|>)", html, re.I)) and bool(re.search(r"</section>\s*$", html, re.I)) and not re.search(r"<!doctype|</?(?:html|head|body)(?:\s|>)", html, re.I)
            self.add("wechat_html_fragment", clean_section, "公众号 HTML 必须是纯 section 正文片段")
            self.run("wechat_html", self.script("gzh-design", "validate_gzh_html.py"), [str(self.root / html_name)], warnings_fail=True)
        declared = meta.get("images", [])
        if not isinstance(declared, list):
            self.add("wechat_images", False, "images 必须是本地图片相对路径数组")
            declared = []
        if meta.get("cover_image"):
            declared = [meta["cover_image"], *declared]
        for relative in dict.fromkeys(str(x) for x in declared):
            self.image(relative)

    def douyin(self, meta: dict[str, Any]) -> None:
        script = self.read("script.md")
        if script:
            self.primary = self._to_base("script.md")
        title, caption, tags = meta.get("title"), meta.get("caption"), meta.get("hashtags")
        self.add("douyin_title", isinstance(title, str) and 1 <= len(title.strip()) <= 30, "抖音标题必须为 1–30 字")
        self.add("douyin_caption", isinstance(caption, str) and 100 <= len(caption.strip()) <= 300, "video-script caption 必须为 100–300 字")
        tags_ok = isinstance(tags, list) and 3 <= len(tags) <= 5 and all(isinstance(t, str) and t.startswith("#") and len(t) > 1 for t in tags)
        self.add("douyin_hashtags", tags_ok, "抖音需要 3–5 个 #话题")
        if isinstance(title, str) and isinstance(caption, str) and tags_ok:
            self.copy_text = title.strip() + "\n\n" + caption.strip() + "\n\n" + " ".join(tags)
        hooks = meta.get("hooks")
        hooks_ok = isinstance(hooks, list) and len(hooks) == 3 and all(isinstance(h, dict) and isinstance(h.get("text", h.get("hook")), str) and h.get("text", h.get("hook", "")).strip() and self.number(h.get("score")) and 0 <= h["score"] <= 20 for h in hooks)
        self.add("douyin_hooks", bool(hooks_ok), "需要 3 个有 text 和 0–20 分 score 的 Hook 变体")
        duration = meta.get("duration_seconds")
        duration_ok = self.number(duration) and duration > 0
        self.add("douyin_duration", duration_ok, "duration_seconds 必须为正数")
        quality = meta.get("quality_score")
        self.add("douyin_quality", self.number(quality) and 80 <= quality <= 100, "video-script 质量评分必须为 80–100")
        shots, narration, reasons, end = meta.get("shots"), [], [], 0.0
        if not isinstance(shots, list) or not shots:
            reasons.append("shots 必须是非空数组")
        else:
            for index, shot in enumerate(shots):
                if not isinstance(shot, dict):
                    reasons.append(f"镜头 {index + 1} 必须是对象")
                    continue
                start, stop = shot.get("start"), shot.get("end")
                if not self.number(start) or not self.number(stop) or start < 0 or stop <= start or abs(start - end) > 0.05:
                    reasons.append(f"镜头 {index + 1} 时间码无效或不连续")
                else:
                    end = float(stop)
                for field in ("narration", "subtitle", "visual"):
                    if not isinstance(shot.get(field), str) or not shot[field].strip():
                        reasons.append(f"镜头 {index + 1} 缺少 {field}")
                if isinstance(shot.get("narration"), str):
                    narration.append(shot["narration"])
            if duration_ok and abs(end - duration) > 0.05:
                reasons.append("最后镜头结束时间与 duration_seconds 不一致")
        self.add("douyin_shots", not reasons, "；".join(reasons) if reasons else "镜头完整且时间轴连续")
        if duration_ok and narration:
            self.run("douyin_wordcount", self.script("shared", "wordcount.py"), ["check", "--target", str(max(1, round(duration / 60 * 250))), "--tolerance", "0.1", "--json"], stdin="\n".join(narration))
        if self.kind == "video":
            self.media_kind = "video"
            self.video(meta)

    def video(self, meta: dict[str, Any]) -> None:
        relative = meta.get("video_path") or meta.get("video") or "final.mp4"
        if not (self.root / str(relative)).is_file():
            relative = next((item for item in self._project_artifacts() if item.lower().endswith(".mp4")), relative)
        path = self.file(relative)
        if not path:
            return
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            self.add("video_probe", False, "ffprobe 不可用，无法验证实际视频")
            return
        data = self.run("video_probe", None, ["-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,duration", "-of", "json", str(path)], executable=ffprobe)
        if data is None:
            return
        streams = data.get("streams", [])
        video = next((s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), None)
        try:
            width, height = int(video["width"]), int(video["height"])
            duration = float(data.get("format", {}).get("duration", video.get("duration", 0)))
            valid = width > 0 and height > 0 and math.isfinite(duration) and duration > 0 and abs(width / height - 9 / 16) < 0.01
            expected = meta.get("duration_seconds")
            if expected is None and isinstance(meta.get("shots"), list):
                expected = sum(float(s.get("duration_sec", 0)) for s in meta["shots"])
            if self.number(expected) and expected > 0:
                valid = valid and abs(duration - expected) <= max(1, expected * 0.1)
            self.add("video_media", valid, f"实际视频 {width}×{height}，{duration:.2f} 秒；要求竖屏 9:16 且时长与脚本一致")
        except (KeyError, TypeError, ValueError, OverflowError):
            self.add("video_media", False, "ffprobe 未返回有效视频流、尺寸或时长")

    def validate(self) -> dict[str, Any]:
        if self.platform not in {"xiaohongshu", "douyin", "wechat-oa"}:
            self.add("platform", False, "不支持的平台")
            return self.result()
        if not self.scan():
            return self.result()
        self._select_project_root()
        self.logdir = self.base / ".validation"
        try:
            self.logdir.mkdir(exist_ok=True)
        except OSError as exc:
            self.add("validation_logs", False, f"无法保存校验日志：{exc}")
            return self.result()
        meta = self.metadata()
        if meta is not None:
            try:
                {"xiaohongshu": self.xhs, "wechat-oa": self.wechat, "douyin": self.douyin}[self.platform](meta)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.add("validation_error", False, str(exc))
        return self.result()
