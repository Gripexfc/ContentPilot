from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from creatoros.services.easel_validation import validate_platform
from creatoros.services.workflow_service import (
    ARCHIVE_SKILLS,
    FINAL_ARTIFACTS,
    QUALITY_SKILLS,
    STAGES,
    TARGETS,
    WorkflowService,
)


PLATFORM_PIPELINES = {
    "xiaohongshu": {
        "skill": "xhs-note-creator",
        "skills": ["xhs-note-creator", "text-polisher", "card-design", "card-xiaohongshu"],
        "media_kind": "cards",
        "required": "meta.json + note markdown + 3-9 rendered card PNG files",
    },
    "douyin": {
        "skill": "video-script",
        "skills": ["video-script"],
        "media_kind": "script",
        "required": "structured script markdown with hook, timecodes, narration, subtitles, visuals, caption and hashtags",
    },
    "wechat-oa": {
        "skill": "social-content",
        "skills": ["social-content", "gzh-design"],
        "media_kind": "article-html",
        "required": "article markdown + paste-ready HTML section + gzh validation result",
    },
}


class EaselAgentWorkflowService(WorkflowService):
    """CreatorOS job shell backed by the vendored Easel/OpenClaw skills.

    The base WorkflowService remains available for legacy and compact tests.
    This class deliberately treats Agent-written files and deterministic checks
    as the completion signal; an Agent response that merely claims success is
    never promoted to a completed platform artifact.
    """

    default_execution_mode = "easel-agent-v1"

    def __init__(self, outputs: Path, gateway, agent_runner, raw_stream_path: Path | None = None, **kwargs):
        super().__init__(outputs, gateway, agent_runner, **kwargs)
        self.agent_runner = agent_runner
        self.raw_stream_path = Path(raw_stream_path) if raw_stream_path else None
        self._last_agent_trace: dict[str, Any] = {"available": False, "source": "session_transcript"}

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _raw_stream_offset(path: Path | None) -> int | None:
        if not path:
            return None
        try:
            return path.stat().st_size
        except OSError:
            # The gateway may create the shared stream after the CLI process
            # starts. Starting at zero is safe for a newly-created file and
            # lets the observer attach instead of silently disabling previews.
            return 0

    @staticmethod
    def _watch_raw_stream(path: Path, offset: int | None, stop: threading.Event,
                          on_delta: Callable[[str], None] | None,
                          on_event: Callable[[dict[str, Any]], None] | None) -> None:
        """Forward this CLI turn's raw gateway deltas without exposing payloads.

        The CLI buffers its final stdout, but the gateway writes token events to
        the shared raw stream. The first run id after the captured offset is
        latched to avoid mixing another concurrent chat into this workflow.
        """
        if offset is None:
            return
        handle = None
        try:
            deadline = time.monotonic() + 30
            while handle is None and not stop.is_set():
                try:
                    handle = path.open('r', encoding='utf-8')
                except OSError:
                    if time.monotonic() >= deadline:
                        return
                    time.sleep(0.05)
            if handle is None:
                return
            run_id = None
            handle.seek(offset)
            pending = ''

            def consume(line: str) -> None:
                nonlocal run_id
                try:
                    value = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    return
                if not isinstance(value, dict):
                    return
                incoming = value.get('runId')
                if run_id is None:
                    if incoming is None:
                        return
                    run_id = incoming
                elif incoming is not None and incoming != run_id:
                    return
                event = value.get('event')
                evt_type = value.get('evtType')
                delta = value.get('delta') or ''
                if event == 'assistant_text_stream' and evt_type == 'text_delta' and isinstance(delta, str):
                    if on_delta and delta:
                        on_delta(delta)
                    return
                if on_event and event:
                    tool = value.get('toolName') or value.get('tool') or value.get('name')
                    on_event({
                        'event': str(event)[:80],
                        'evtType': str(evt_type)[:80] if evt_type else '',
                        'tool': str(tool)[:120] if tool else '',
                        'has_delta': bool(delta),
                    })

            while not stop.is_set():
                chunk = handle.readline()
                if chunk == '':
                    time.sleep(0.05)
                    continue
                pending += chunk
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    if line.strip():
                        consume(line)
            # Drain complete lines appended just before the agent returned.
            pending += handle.read() or ''
            for line in pending.splitlines():
                if line.strip():
                    consume(line)
        except OSError:
            return
        finally:
            if handle:
                handle.close()

    def _stream_hooks(self, job: dict[str, Any], stage: str, platform: str | None = None):
        self._begin_live_stream(job, stage, platform)
        if platform:
            state = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
            now = time.time()
            state.update(text='', complete=False, started_at=now, updated_at=now, finished_at=None, error='', chars=0)
        buffer = {'text': '', 'last_saved': 0.0, 'last_chars': 0}

        def on_delta(delta: str):
            if not isinstance(delta, str) or not delta:
                return
            buffer['text'] += delta
            now = time.time()
            if now - buffer['last_saved'] < 0.2 and len(buffer['text']) - buffer['last_chars'] < 128:
                return
            with self.lock:
                live = job.setdefault('live_stream', {})
                live.update(text=buffer['text'], updated_at=now, chars=len(buffer['text']), status='running')
                if platform:
                    state = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
                    state.update(text=buffer['text'], complete=False, updated_at=now, chars=len(buffer['text']), error='')
                self._save(job)
            buffer['last_saved'] = now
            buffer['last_chars'] = len(buffer['text'])

        def on_event(event: dict[str, Any]):
            if not job.get('debug_mode'):
                return
            name = event.get('event') or 'agent_event'
            event_type = event.get('evtType') or ''
            tool = event.get('tool') or ''
            self._debug_event(job, 'agent_event', stage=stage, platform=platform,
                              message=f'Agent 事件：{name}{" / " + event_type if event_type else ""}{" · " + tool if tool else ""}', detail=event)

        def finish(status='completed', error=''):
            with self.lock:
                live = job.setdefault('live_stream', {})
                live.update(text=buffer['text'], complete=status == 'completed', status=status,
                            updated_at=time.time(), chars=len(buffer['text']))
                live['finished_at'] = live['updated_at']
                if error:
                    live['error'] = str(error)[:240]
                if platform:
                    state = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
                    state.update(text=buffer['text'], complete=status == 'completed', updated_at=live['updated_at'],
                                 finished_at=live['updated_at'], chars=len(buffer['text']), error=str(error or ''))
                self._save(job)

        return on_delta, on_event, finish

    def _call_agent(self, prompt: str, session_id: str, timeout: int = 900,
                    on_delta: Callable[[str], None] | None = None,
                    on_event: Callable[[dict[str, Any]], None] | None = None) -> str:
        """Call the existing CreatorOS Agent runner, keeping test adapters small."""
        self._last_agent_trace = {"available": False, "source": "session_transcript"}
        stop = threading.Event()
        stream_thread = None
        offset = self._raw_stream_offset(self.raw_stream_path)
        if self.raw_stream_path and (on_delta or on_event) and offset is not None:
            stream_thread = threading.Thread(
                target=self._watch_raw_stream,
                args=(self.raw_stream_path, offset, stop, on_delta, on_event),
                name=f'creatoros-agent-stream-{session_id[-24:]}',
                daemon=True,
            )
            stream_thread.start()
        try:
            try:
                result = self.agent_runner(prompt, timeout, session_id)
            except TypeError as exc:
                # A few embedders expose the historical (prompt, session_id) form.
                # Only use it as a compatibility fallback.
                if "positional argument" not in str(exc) and "required positional" not in str(exc):
                    raise
                try:
                    result = self.agent_runner(prompt, session_id)
                except TypeError as second:
                    if "positional argument" not in str(second) and "required positional" not in str(second):
                        raise
                    result = self.agent_runner(prompt)
            if isinstance(result, dict):
                self._last_agent_trace = result.get("trace") if isinstance(result.get("trace"), dict) else {"available": False, "source": "session_transcript"}
                result = result.get("response", "")
            if not isinstance(result, str) or not result.strip():
                raise RuntimeError("OpenClaw Agent 未返回有效结果")
            return result.strip()
        finally:
            stop.set()
            if stream_thread:
                stream_thread.join(timeout=2.0)

    @staticmethod
    def _receipt_from_response(response: str) -> dict[str, Any]:
        for raw in reversed(response.splitlines()):
            line = raw.strip()
            if not (line.startswith("{") and line.endswith("}")):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _files(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()]

    def _check_platform_artifacts(self, platform: str, platform_dir: Path) -> dict[str, Any]:
        files = self._files(platform_dir)
        names = {p.name.lower() for p in files}
        markdown = [p for p in files if p.suffix.lower() in {".md", ".markdown", ".txt"}]
        pngs = [p for p in files if p.suffix.lower() == ".png"]
        html = [p for p in files if p.suffix.lower() in {".html", ".htm"}]
        checks: list[dict[str, Any]] = []
        missing: list[str] = []

        if platform == "xiaohongshu":
            has_meta = "meta.json" in names
            has_note = bool(markdown)
            if not has_meta:
                missing.append("meta.json")
            if not has_note:
                missing.append("note markdown")
            if not 3 <= len([p for p in pngs if p.name.lower().startswith("card_")]) <= 9:
                missing.append("3-9 card_*.png")
            checks.extend([
                {"name": "meta.json", "status": "passed" if has_meta else "failed"},
                {"name": "note", "status": "passed" if has_note else "failed"},
                {"name": "card_images", "status": "passed" if not any(x.startswith("3-9") for x in missing) else "failed", "count": len([p for p in pngs if p.name.lower().startswith("card_")])},
            ])
        elif platform == "douyin":
            has_script = bool(markdown)
            if not has_script:
                missing.append("script markdown")
            checks.append({"name": "video-script", "status": "passed" if has_script else "failed", "media_kind": "script"})
        else:
            has_article = bool(markdown)
            has_html = bool(html) and any("<section" in p.read_text(encoding="utf-8", errors="ignore") for p in html)
            if not has_article:
                missing.append("article markdown")
            if not has_html:
                missing.append("paste-ready HTML section")
            checks.extend([
                {"name": "article", "status": "passed" if has_article else "failed"},
                {"name": "gzh-design", "status": "passed" if has_html else "failed"},
            ])

        return {
            "status": "completed" if not missing else "blocked",
            "artifacts": [str(p.relative_to(self.outputs)) for p in files],
            "checks": checks,
            "missing": missing,
            "media_kind": PLATFORM_PIPELINES[platform]["media_kind"],
        }

    def _mark(self, job: dict, key: str, status: str, reason: str = "", artifact: str | None = None) -> None:
        with self.lock:
            now = time.time()
            stage = job["stages"][key]
            stage.update(status=status, reason=reason, finished_at=now)
            if artifact:
                stage["artifact"] = artifact
            self._save(job)

    def _agent_prompt(self, job: dict, stage: str, platform: str | None = None, output_dir: str | None = None, source_text: str = "") -> str:
        project = f"outputs/workflow-{job['id']}"
        base = (
            "你正在 CreatorOS 中执行 Easel/OpenClaw 原生工作流。必须读取当前 runtime workspace 的 "
            "AGENTS.md、SOUL.md 和目标 SKILL.md；不要使用随波逐流、ContentPilot 或 compact-v2 规则。"
            "允许调用 Skill 要求的检索、脚本、浏览器和渲染工具；禁止发布到任何平台，生成结果统一保持 draft。\n"
            f"主题：{job['topic']}\n账号画像：{job.get('profile') or '通用'}\n"
        )
        if stage == "discovery":
            return base + (
                f"阶段：发现与核验。执行 /skill-trending-topics 和 /skill-news-intelligence，"
                f"将事实、来源链接、观察日期和待核验项写入 {project}/01-discovery.md。"
                "不能访问的来源必须记录 BLOCKED，不能虚构亲测、数据或引用。\n"
            )
        if stage == "topic":
            return base + (
                f"阶段：选题与结构。执行 /skill-trend-rider、/skill-topic-evaluator、/skill-article-outline，"
                f"只读取 {project}/01-discovery.md，将读者任务、核心承诺、平台方向和大纲写入 {project}/02-topic.md。\n"
            )
        if stage == "master":
            return base + (
                f"阶段：母稿。执行 /social-content 生成可供三端改写的事实边界清楚的母稿，"
                f"写入 {project}/03-master.md。它是中间产物，不要代替三端专用 Skill。"
                f"参考前序产物：{project}/01-discovery.md、{project}/02-topic.md。\n"
            )
        if stage == "adaptation" and platform:
            spec = PLATFORM_PIPELINES[platform]
            target = output_dir or f"{project}/{platform}"
            common = (
                f"阶段：{TARGETS[platform]}平台生成。目标目录必须是 {target}，"
                "所有真实文件必须落在该目录内；完成后返回一行 JSON 回执，包含 status、executed_skills、"
                "artifacts、checks、missing、content_status=draft、published=false、media_kind。"
                "回执不能替代文件，不能只返回文章文本。前序材料："
                f"{project}/01-discovery.md、{project}/02-topic.md、{project}/03-master.md。\n"
            )
            if platform == "xiaohongshu":
                return base + common + (
                    "执行 /xhs-note-creator，默认图文模式；没有真实图片时使用 HTML 卡片管线，"
                    "执行 card-design→card-xiaohongshu→shared/render_card.py→card_audit.py，"
                    "生成 3-9 张 card_*.png、note markdown、meta.json 和 reference；执行 validate_meta.py。"
                    "任何渲染依赖或素材缺失都要 BLOCKED，不能用配图建议冒充图片。\n"
                )
            if platform == "douyin":
                if job.get("output_kind") == "video":
                    return base + common + (
                        "执行 /auto-short-video，先调用 /video-script 生成脚本，再按已确认的竖屏 9:16、1080×1920 规格制作实际成片。"
                        "同时保留 script.md 和 meta.json（含 duration_seconds、hooks、shots、caption、hashtags、quality_score）。"
                        "涉及按量付费的生图、生视频、配音或音乐时，不得自动发起请求；写明缺失配置并 BLOCKED。"
                        "必须存在真实 final.mp4、storyboard 和中间素材，并用 ffprobe 检查后再回执。\n"
                    )
                return base + common + (
                    "执行 /video-script，默认 30 秒抖音脚本；生成 3 个 Hook 变体及评分、时间码、口播、字幕、"
                    "画面、caption、3-5 个话题、封面方案和质量评分，并按 video-script 的 wordcount/格式规则校验。"
                    "本阶段 media_kind=script，不得声称已经生成 MP4；如需成片必须另走 auto-short-video。\n"
                )
            return base + common + (
                "执行 /social-content 生成公众号原生长文，再执行 /gzh-design 读取主题组件库排版；"
                "按 Skill 的官方动态文件名生成 Markdown、干净 section HTML 和可选预览页；不要把 HTML 外壳当正文。"
                "运行 validate_gzh_html.py，"
                "ERROR 和 WARNING 都必须清零。配图或封面缺少外部能力时明确 BLOCKED，不发布公众号草稿。\n"
            )
        if stage == "quality" and platform:
            spec = PLATFORM_PIPELINES[platform]
            target = output_dir or f"{project}/{platform}"
            return base + (
                f"阶段：{TARGETS[platform]}质量检查。执行 /skill-quality-gate，"
                f"有账号画像再执行 /skill-persona-check；检查 {target} 的文件、来源边界、平台规范、"
                "真实媒体和校验回执，结果写入质量报告，明确通过项、风险项和人工复核项。不要发布。\n"
            )
        if stage == "archive":
            return base + (
                "阶段：归档交付。执行 /asset-manager 和 /skill-publish-checklist，"
                f"读取 {project} 下的研究、母稿、平台产物和质量报告，写出 {project}/06-archive-checklist.md。"
                "只登记草稿和待人工复核状态，不调用任何 publisher，不登录、不建公众号草稿、不发布。\n"
            )
        return base

    def _run_easel_agent(self, job_id: str) -> None:
        job = self.get(job_id)
        folder = self.outputs / f"workflow-{job_id}"
        folder.mkdir(parents=True, exist_ok=True)
        job.setdefault("agent_receipts", {})
        job.setdefault("execution_receipts", [])
        job.setdefault("platform_outputs", {})
        try:
            if not self.gateway():
                self._mark(job, "discovery", "blocked", "BLOCKED：模型/研究网关未配置或不可用。")
                with self.lock:
                    job.update(status="blocked", current=None)
                    self._save(job)
                return

            discovery_path = folder / "01-discovery.md"
            discovery_stage = job["stages"]["discovery"]
            if not (discovery_stage.get("status") == "completed" and discovery_path.is_file() and discovery_path.read_text(encoding="utf-8").strip()):
                with self.lock:
                    job.update(status="running", current="discovery")
                    discovery_stage.update(status="running", started_at=time.time())
                    self._save(job)
                self._debug_event(job, 'stage_started', stage='discovery', message='开始发现与核验')
                hooks = self._stream_hooks(job, 'discovery')
                discovery = self._call_agent(
                    self._agent_prompt(job, "discovery"),
                    f"workflow-{job_id}-discovery-attempt-{job.get('attempt', 1)}",
                    on_delta=hooks[0], on_event=hooks[1],
                )
                blocked = self._blocked_reason(discovery)
                if blocked:
                    hooks[2]('blocked', blocked)
                    self._mark(job, "discovery", "blocked", blocked)
                    self._debug_event(job, 'stage_blocked', stage='discovery', message=blocked)
                    with self.lock:
                        job.update(status="blocked", current=None)
                        self._save(job)
                    return
                hooks[2]('completed')
                self._atomic_write(discovery_path, discovery)
                self._mark(job, "discovery", "completed", artifact=str(discovery_path.relative_to(self.outputs)))
                self._debug_event(job, 'stage_finished', stage='discovery', message='发现与核验完成')
                job["execution_receipts"].append({"stage": "discovery", "trace": self._last_agent_trace, "skills": list(job["stages"]["discovery"].get("skills", [])), "status": "completed"})

            for key in ("topic", "master"):
                path = folder / {"topic": "02-topic.md", "master": "03-master.md"}[key]
                stage = job["stages"][key]
                if stage.get("status") == "completed" and path.is_file() and path.read_text(encoding="utf-8").strip():
                    continue
                with self.lock:
                    job.update(status="running", current=key)
                    stage.update(status="running", started_at=time.time())
                    self._save(job)
                self._debug_event(job, 'stage_started', stage=key, message=f'开始{stage.get("label", key)}')
                hooks = self._stream_hooks(job, key)
                result = self._call_agent(
                    self._agent_prompt(job, key),
                    f"workflow-{job_id}-{key}-attempt-{job.get('attempt', 1)}",
                    on_delta=hooks[0], on_event=hooks[1],
                )
                blocked = self._blocked_reason(result)
                if blocked:
                    hooks[2]('blocked', blocked)
                    self._mark(job, key, "blocked", blocked)
                    self._debug_event(job, 'stage_blocked', stage=key, message=blocked)
                    with self.lock:
                        job.update(status="blocked", current=None)
                        self._save(job)
                    return
                hooks[2]('completed')
                self._atomic_write(path, result)
                self._mark(job, key, "completed", artifact=str(path.relative_to(self.outputs)))
                self._debug_event(job, 'stage_finished', stage=key, message=f'{stage.get("label", key)}完成')
                job["execution_receipts"].append({"stage": key, "trace": self._last_agent_trace, "skills": list(job["stages"][key].get("skills", [])), "status": "completed"})

            adaptation_report: list[str] = ["# Easel 平台产物\n"]
            adaptation_blocked = False
            for platform in job.get("platforms") or []:
                platform_dir = folder / platform
                platform_dir.mkdir(parents=True, exist_ok=True)
                with self.lock:
                    job.update(status="running", current="adaptation")
                    adaptation_stage = job["stages"]["adaptation"]
                    adaptation_stage.update(status="running", started_at=adaptation_stage.get("started_at") or time.time())
                    self._save(job)
                self._debug_event(job, 'stage_started', stage='adaptation', platform=platform, message=f'开始{TARGETS[platform]}平台适配')
                hooks = self._stream_hooks(job, 'adaptation', platform)
                session = f"workflow-{job_id}-{platform}-adaptation-attempt-{job.get('attempt', 1)}"
                response = self._call_agent(
                    self._agent_prompt(job, "adaptation", platform, f"outputs/workflow-{job_id}/{platform}"),
                    session, timeout=1800, on_delta=hooks[0], on_event=hooks[1],
                )
                agent_blocked = self._blocked_reason(response)
                receipt = self._receipt_from_response(response)
                skills_root = Path(__file__).resolve().parents[2] / "vendor" / "easel" / "skills"
                check = validate_platform(platform, platform_dir, skills_root, output_kind=job.get("output_kind", "standard"))
                platform_prefix = str(platform_dir.relative_to(self.outputs)).replace("\\", "/")
                check["artifacts"] = [f"{platform_prefix}/{path}" for path in check.get("artifacts", [])]
                if check.get("primary_text"):
                    check["primary_text"] = f"{platform_prefix}/{check['primary_text']}"
                receipt.update({
                    "schema_version": "1",
                    "platform": platform,
                    "pipeline": "easel-agent-v1",
                    "requested_skills": list(PLATFORM_PIPELINES[platform]["skills"]) + (["auto-short-video"] if platform == "douyin" and job.get("output_kind") == "video" else []),
                    "response_chars": len(response),
                    "trace": self._last_agent_trace,
                    **check,
                    "status": ("completed" if not agent_blocked and check.get("status") == "passed" and str(receipt.get("status") or "completed") not in {"blocked", "failed"} else "blocked"),
                    "reason": agent_blocked or ("；".join(check.get("missing", [])) if check.get("missing") else ""),
                    "content_status": "draft",
                    "published": False,
                    "human_review_required": True,
                })
                receipt_path = platform_dir / ".creatoros-agent.json"
                self._atomic_write(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2))
                job["agent_receipts"][platform] = receipt
                job["execution_receipts"].append({"stage": "adaptation", "platform": platform, "trace": receipt.get("trace", {}), "skills": receipt.get("requested_skills", []), "checks": receipt.get("checks", []), "status": receipt.get("status")})
                job["platform_outputs"][platform] = {
                    "directory": str(platform_dir.relative_to(self.outputs)),
                    "skill": PLATFORM_PIPELINES[platform]["skill"],
                    "media_kind": receipt.get("media_kind") or PLATFORM_PIPELINES[platform]["media_kind"],
                    "artifacts": receipt.get("artifacts", []),
                    "checks": receipt.get("checks", []),
                    "primary_text": receipt.get("primary_text", ""),
                    "copy_text": receipt.get("copy_text", ""),
                    "missing": receipt.get("missing", []),
                    "status": receipt["status"],
                }
                adaptation_report.append(f"- {TARGETS[platform]}：{receipt['status']}，Skill={PLATFORM_PIPELINES[platform]['skill']}，产物={len(receipt.get('artifacts', []))}")
                hooks[2]('completed' if receipt['status'] == 'completed' else 'blocked', receipt.get('reason', ''))
                self._debug_event(job, 'artifact_validation', stage='adaptation', platform=platform,
                                  message=f'{TARGETS[platform]}产物校验：{receipt["status"]}',
                                  detail={'missing': ','.join(receipt.get('missing', [])), 'artifacts': len(receipt.get('artifacts', []))})
                if receipt["status"] != "completed":
                    adaptation_blocked = True

            adaptation_path = folder / "04-adaptation.md"
            self._atomic_write(adaptation_path, "\n".join(adaptation_report))
            self._mark(job, "adaptation", "blocked" if adaptation_blocked else "completed", "；".join(
                f"{TARGETS[p]}：" + "、".join(job["agent_receipts"][p].get("missing", []))
                for p in job["platforms"] if job["agent_receipts"][p].get("missing")
            ), artifact=str(adaptation_path.relative_to(self.outputs)))
            self._debug_event(job, 'stage_blocked' if adaptation_blocked else 'stage_finished', stage='adaptation', message='平台适配未完成' if adaptation_blocked else '平台适配完成')
            if adaptation_blocked:
                with self.lock:
                    job.update(status="blocked", current=None, content_status="draft", published=False)
                    self._save(job)
                return

            quality_report: list[str] = ["# Easel 平台质量检查\n"]
            quality_blocked = False
            for platform in job.get("platforms") or []:
                with self.lock:
                    job.update(status="running", current="quality")
                    quality_stage = job["stages"]["quality"]
                    quality_stage.update(status="running", started_at=quality_stage.get("started_at") or time.time())
                    self._save(job)
                self._debug_event(job, 'stage_started', stage='quality', platform=platform, message=f'开始{TARGETS[platform]}质量检查')
                hooks = self._stream_hooks(job, 'quality', platform)
                response = self._call_agent(
                    self._agent_prompt(job, "quality", platform, f"outputs/workflow-{job_id}/{platform}"),
                    f"workflow-{job_id}-{platform}-quality-attempt-{job.get('attempt', 1)}",
                    timeout=900, on_delta=hooks[0], on_event=hooks[1],
                )
                path = folder / f"05-quality-{platform}.md"
                self._atomic_write(path, response)
                quality_blocked_reason = self._blocked_reason(response)
                platform_quality_blocked = bool(quality_blocked_reason or "BLOCKED" in response.upper() or "FAILED" in response.upper())
                hooks[2]('blocked' if platform_quality_blocked else 'completed', quality_blocked_reason)
                job["execution_receipts"].append({"stage": "quality", "platform": platform, "trace": self._last_agent_trace, "skills": list(QUALITY_SKILLS), "status": "blocked" if platform_quality_blocked else "completed"})
                if platform_quality_blocked:
                    quality_blocked = True
                quality_report.append(f"- {TARGETS[platform]}：报告已生成，需人工复核")
            quality_path = folder / "05-quality.md"
            self._atomic_write(quality_path, "\n".join(quality_report) + "\n\n内容状态：draft；human_review_required=true。")
            self._mark(job, "quality", "blocked" if quality_blocked else "completed", "质量报告包含 BLOCKED/FAILED" if quality_blocked else "需人工复核", artifact=str(quality_path.relative_to(self.outputs)))
            self._debug_event(job, 'stage_blocked' if quality_blocked else 'stage_finished', stage='quality', message='质量检查需要处理' if quality_blocked else '质量检查完成')
            if quality_blocked:
                with self.lock:
                    job.update(status="blocked", current=None, content_status="draft", published=False)
                    self._save(job)
                return

            with self.lock:
                job.update(status="running", current="archive")
                job["stages"]["archive"].update(status="running", started_at=time.time())
                self._save(job)
            self._debug_event(job, 'stage_started', stage='archive', message='开始归档交付')
            hooks = self._stream_hooks(job, 'archive')
            archive_response = self._call_agent(
                self._agent_prompt(job, "archive"),
                f"workflow-{job_id}-archive-attempt-{job.get('attempt', 1)}",
                timeout=900, on_delta=hooks[0], on_event=hooks[1],
            )
            archive_blocked = self._blocked_reason(archive_response)
            hooks[2]('blocked' if archive_blocked else 'completed', archive_blocked)
            archive_agent_path = folder / "06-archive-checklist.md"
            if not archive_agent_path.is_file():
                self._atomic_write(archive_agent_path, archive_response)
            job["execution_receipts"].append({"stage": "archive", "trace": self._last_agent_trace, "skills": list(ARCHIVE_SKILLS), "status": "blocked" if archive_blocked else "completed"})
            if archive_blocked:
                self._mark(job, "archive", "blocked", archive_blocked, artifact=str(archive_agent_path.relative_to(self.outputs)))
                self._debug_event(job, 'stage_blocked', stage='archive', message=archive_blocked)
                with self.lock:
                    job.update(status="blocked", current=None, content_status="draft", published=False)
                    self._save(job)
                return
            manifest = {
                "schema_version": "1",
                "title": job["topic"],
                "kind": "easel-platform-content",
                "status": "draft",
                "content_status": "draft",
                "published": False,
                "human_review_required": True,
                "execution_mode": "easel-agent-v1",
                "debug_mode": bool(job.get("debug_mode")),
                "debug_events": job.get("debug_events", [])[-200:],
                "platform_outputs": job["platform_outputs"],
                "agent_receipts": job["agent_receipts"],
                "execution_receipts": job.get("execution_receipts", []),
                "archive_skills": list(ARCHIVE_SKILLS),
            }
            archive_path = folder / "06-archive.md"
            self._atomic_write(archive_path, json.dumps(manifest, ensure_ascii=False, indent=2))
            self._atomic_write(folder / ".creatoros.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            self._mark(job, "archive", "completed", artifact=str(archive_path.relative_to(self.outputs)))
            self._debug_event(job, 'stage_finished', stage='archive', message='归档交付完成')
            with self.lock:
                job.update(status="completed", current=None, content_status="draft", published=False)
                self._save(job)
        except Exception as exc:
            with self.lock:
                current = job.get("current") or "discovery"
                job["stages"].setdefault(current, {}).update(status="failed", reason=self._failure_reason(exc), finished_at=time.time())
                job.setdefault('live_stream', {}).update(status='failed', complete=False, finished_at=time.time(), error=self._failure_reason(exc))
                job.update(status="failed", current=None, content_status="draft", published=False)
                self._save(job)
            self._debug_event(job, 'stage_failed', stage=current, message=self._failure_reason(exc))
