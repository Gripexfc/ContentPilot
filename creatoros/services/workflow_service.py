"""Persistent CreatorOS workflow shell with Easel/OpenClaw as the production route."""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

STAGES = [
    ('discovery', '发现与核验'),
    ('topic', '选题与结构'),
    ('master', '主稿'),
    ('adaptation', '平台适配'),
    ('quality', '质量检查'),
    ('archive', '归档交付'),
]
TARGETS = {'xiaohongshu': '小红书', 'douyin': '抖音', 'wechat-oa': '公众号'}
FINAL_ARTIFACTS = {
    'wechat-oa': '08-gzh-final.md',
    'xiaohongshu': '09-xhs-final.md',
    'douyin': '10-douyin-final.md',
}

# These are the same capability layers used by the reference Git project.  The
# list is persisted into each stage so a completed job can be audited instead
# of only showing an opaque model response.
DISCOVERY_SKILLS = ('skill-trending-topics', 'skill-news-intelligence')
TOPIC_SKILLS = ('skill-trend-rider', 'skill-topic-evaluator', 'skill-article-outline')
QUALITY_SKILLS = ('skill-quality-gate', 'skill-persona-check')
ARCHIVE_SKILLS = ('asset-manager', 'skill-publish-checklist')
PLATFORM_SKILLS = {
    'wechat-oa': 'social-content',
    'xiaohongshu': 'xhs-note-creator',
    'douyin': 'video-script',
}
# These are downstream format/editing skills.  They must not replace the
# research or writing skill for the whole workflow.
POSTPROCESS_SKILLS = {'gzh-design', 'text-polisher', 'post-formatter'}

INSTRUCTIONS = {
    'discovery': (
        '先执行 /skill-trending-topics 与 /skill-news-intelligence 的发现和研究职责；'
        '搜索当前一手资料，逐条写明来源链接、观察日期、事实和未核验缺口。'
        '最多核验 3 个一手来源、最多进行两轮检索；来源访问失败就记录 BLOCKED 并继续形成阶段结论，禁止反复重试。'
        '应在有限时间内写出简洁的研究报告，不能访问来源就说明阻断，禁止虚构亲测或来源。'
    ),
    'topic': (
        '先执行 /skill-trend-rider、/skill-topic-evaluator 和 /skill-article-outline；'
        '依据前一步研究选择读者任务、原创增量、标题方向和大纲。'
        '只读取前一步已经落盘的研究产物，不要重新联网检索、调用 web_search 或反复运行发现类工具；'
        '每个 Skill 最多执行一次，外部来源不可用时直接沿用已有事实并标记待核验，不要等待或询问用户。'
        '区分事实、作者材料、推断和待核验内容。'
    ),
    'master': (
        '执行所选平台的主创作 Skill，形成完整、可审校的母稿；'
        '只基于前序研究和大纲写作，不再进行联网研究或媒体处理；'
        '保留来源引用和事实边界，不虚构个人经历或运营效果。'
        '本工作流阶段契约优先于 Skill 中要求运行脚本的建议；禁止调用 exec、shell、python、node、npm、字数统计脚本或其他外部工具；'
        '不要尝试读写文件，直接在回复中一次性返回完整母稿，后端会负责落盘。'
    ),
    'adaptation': (
        '为每个目标平台分别执行对应平台 Skill，独立撰写标题、正文或脚本，不能复制同一正文。'
        '小红书标题最多20字正文1000字；抖音文案最多55字并交付分镜脚本；公众号标题最多64字、正文控制在1800至2500字。'
        '只改写前序母稿，不再联网检索、调用媒体工具、view_image、edit 或反复生成进度卡；'
        '每个已选平台只写入一次终稿文件，先在内存中完成全文再一次性写入；内容过长时主动压缩，不要请求继续生成。'
        '列出待制作图片和视频，不能声称媒体已生成。'
        '本工作流阶段契约优先于 Skill 中要求运行脚本的建议；禁止运行 exec、shell、python、node、npm 或字数统计脚本；只允许按上面的文件契约一次性写入终稿，'
        '不要为校验长度反复调用工具，长度不确定时直接压缩内容并继续。'
    ),
    'quality': (
        '执行 /skill-quality-gate 和 /skill-persona-check；逐项检查来源、事实边界、原创增量、'
        '平台长度、缺失媒体和画像一致性，输出具体问题清单。未做真人表达检测不得声称检测通过，'
        '只检查前序产物，不再联网检索或调用媒体工具；不要运行脚本、反复读取技能目录或请求继续生成。'
        '只输出不超过 500 字的短报告，使用“通过项 / 风险项 / 人工复核项”三段结构；最终内容状态只能是 draft。'
    ),
}


class WorkflowService:
    def __init__(self, outputs: Path, gateway, runner, session_runner=None, compose_runner=None, compose_stream_runner=None):
        self.outputs = outputs
        self.directory = outputs / '_workflow'
        self.gateway = gateway
        self.runner = runner
        # Production passes run_agent_sync here with a distinct transcript for
        # each stage and attempt. Tests and embedders may keep the old
        # one-argument runner.
        self.session_runner = session_runner
        # compact-v2 is retained as an explicit compatibility path for old
        # jobs/tests. New production jobs use EaselAgentWorkflowService.
        self.compose_runner = compose_runner
        # Optional streaming adapter for direct provider composition.  The
        # regular compose runner remains the compatibility path for tests and
        # embedders that only return a final string.
        self.compose_stream_runner = compose_stream_runner
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='creatoros-workflow')
        self.active = set()
        self.directory.mkdir(parents=True, exist_ok=True)
        # A process exit never turns an unfinished job into success.
        for path in self.directory.glob('*.json'):
            try:
                job = json.loads(path.read_text())
                if job.get('status') in {'running', 'queued'}:
                    job['status'] = 'interrupted'
                    for stage in job['stages'].values():
                        if stage['status'] == 'running':
                            stage.update(status='interrupted', reason='服务重启；可从此阶段重试。')
                    self._save(job)
            except (ValueError, KeyError):
                continue

    def _path(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{12}', job_id):
            raise KeyError(job_id)
        return self.directory / f'{job_id}.json'

    def _save(self, job):
        job['updated'] = time.time()
        path = self._path(job['id'])
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(path)

    def get(self, job_id):
        with self.lock:
            try:
                return json.loads(self._path(job_id).read_text())
            except FileNotFoundError:
                raise KeyError(job_id)

    def list(self):
        with self.lock:
            jobs = [json.loads(p.read_text()) for p in self.directory.glob('*.json')]
        return sorted(jobs, key=lambda j: j.get('created', 0), reverse=True)[:50]

    @staticmethod
    def _dedupe(items):
        return list(dict.fromkeys(item for item in items if item))

    def _stage_skills(self, job, key):
        platforms = job.get('platforms') or []
        selected = (job.get('skill') or '').strip()
        if key == 'discovery':
            return list(DISCOVERY_SKILLS)
        if key == 'topic':
            return list(TOPIC_SKILLS)
        if key == 'master':
            defaults = [PLATFORM_SKILLS.get(platform, 'social-content') for platform in platforms]
            # A layout/polish skill is applied after writing, never as the only
            # master writer.  Keep the user's choice as an explicit secondary
            # instruction when it is meaningful.
            writer = selected if selected and selected not in POSTPROCESS_SKILLS else ''
            return self._dedupe([writer, *defaults, 'social-content'])
        if key == 'adaptation':
            defaults = [PLATFORM_SKILLS.get(platform, 'social-content') for platform in platforms]
            return self._dedupe([selected, *defaults])
        if key == 'quality':
            return list(QUALITY_SKILLS if job.get('profile') else ('skill-quality-gate',))
        if key == 'archive':
            return list(ARCHIVE_SKILLS)
        return []

    def start(self, topic, platforms, profile='', skill='', revision=None, output_kind='standard', debug_mode=False):
        if not topic.strip() or not platforms or set(platforms) - TARGETS.keys():
            raise ValueError('请输入主题，发布目标仅支持公众号、小红书和抖音')
        normalized_revision = None
        if revision:
            if not isinstance(revision, dict):
                raise ValueError('修改请求格式不正确')
            draft = str(revision.get('draft') or '').strip()
            instruction = str(revision.get('instruction') or '').strip()
            if not draft or not instruction:
                raise ValueError('修改请求需要包含原稿和具体修改意见')
            normalized_revision = {'draft': draft[:8000], 'instruction': instruction[:1000]}
        stages = {}
        for key, label in STAGES:
            stages[key] = dict(label=label, status='pending', reason='', artifact=None, skills=[])
        job = dict(
            id=uuid4().hex[:12], topic=topic.strip(), platforms=list(dict.fromkeys(platforms)),
            profile=profile, skill=skill.strip(), revision=normalized_revision, output_kind=(output_kind if output_kind in {'standard', 'video'} else 'standard'), status='queued', current=None,
            created=time.time(), attempt_started=time.time(), attempt=1, stages=stages,
            execution_mode=getattr(self, 'default_execution_mode', None) or ('compact-v2' if self.compose_runner is not None else 'legacy-v1'),
            # Easel Agent jobs allow platform Skills, deterministic media checks,
            # and long-running renders. Compact and legacy jobs retain their
            # existing budgets for compatibility and explicit fast-draft use.
            budget_seconds=(1800 if getattr(self, 'default_execution_mode', None) == 'easel-agent-v1' else (420 if self.compose_runner is not None else 35 * 60)),
            # The selected platform's direct-composition text is checkpointed
            # here while the model is still streaming.  It is intentionally
            # separate from final artifacts so partial text can never be
            # mistaken for a completed draft.
            streaming_outputs={
                platform: self._new_stream_state()
                for platform in dict.fromkeys(platforms)
            },
            debug_mode=bool(debug_mode),
            debug_events=[],
            live_stream={
                'stage': None, 'platform': None, 'text': '', 'complete': False,
                'status': 'idle', 'started_at': None, 'updated_at': None,
                'finished_at': None, 'chars': 0,
            },
        )
        for key, _ in STAGES:
            job['stages'][key]['skills'] = self._stage_skills(job, key)
        with self.lock:
            self._save(job)
            self.active.add(job['id'])
        self.executor.submit(self._run, job['id'])
        return self.get(job['id'])

    def retry(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job_id not in self.active and job['status'] == 'completed':
                missing_final = self._missing_final_artifacts(job)
                if missing_final:
                    # Older jobs could be marked completed after writing only
                    # the adaptation report. Repair them through the normal
                    # retry path without changing any existing files.
                    job['status'] = 'failed'
                    job['stages']['adaptation'].update(
                        status='failed', reason='平台终稿未生成：' + '、'.join(missing_final),
                    )
            if job_id in self.active or job['status'] not in {'blocked', 'failed', 'interrupted'}:
                raise ValueError('仅阻断、失败或中断的作业可以重试')
            previous_started = job.get('attempt_started') or job.get('started_at') or job.get('created')
            job.setdefault('attempts', []).append({
                'attempt': job.get('attempt', 1),
                'status': job['status'],
                'stages': job['stages'],
                'started_at': previous_started,
                'finished_at': job.get('finished_at'),
                'duration_seconds': job.get('duration_seconds'),
            })
            job['attempt'] = job.get('attempt', 1) + 1
            job['attempt_started'] = time.time()
            job.pop('finished_at', None)
            job.pop('duration_seconds', None)
            job.pop('duration_ms', None)
            job['status'] = 'queued'
            # An explicit retry is the only place where a legacy failed job
            # may be upgraded. This lets a user recover an old master-stage
            # timeout with the compact path while preserving every old
            # artifact and attempt record. New background work is never
            # silently migrated.
            if self.compose_runner is not None:
                if job.get('execution_mode') != 'compact-v2':
                    job['migrated_from'] = job.get('migrated_from') or 'legacy-v1'
                job['execution_mode'] = 'compact-v2'
                job['budget_seconds'] = 420
                self._prepare_compact_retry(job)
                self._save(job)
                self.active.add(job_id)
                self.executor.submit(self._run, job_id)
                return self.get(job_id)
            job['stages'] = {k: dict(v) for k, v in job['stages'].items()}
            restart = False
            for key, _ in STAGES:
                stage = job['stages'][key]
                restart = restart or stage['status'] != 'completed'
                if restart:
                    # A repaired adaptation invalidates the old quality
                    # report too. Preserve files for diagnosis, but rerun
                    # downstream stages and exclude their stale prompt input.
                    stage.update(status='pending', reason='', artifact=None)
            self._save(job)
            self.active.add(job_id)
        self.executor.submit(self._run, job_id)
        return self.get(job_id)

    @staticmethod
    def _artifact_is_valid(outputs, artifact):
        if not artifact:
            return False
        path = outputs / artifact
        try:
            path.resolve().relative_to(outputs.resolve())
            return path.is_file() and not path.is_symlink() and bool(path.read_text(encoding='utf-8').strip())
        except (OSError, ValueError, UnicodeError):
            return False

    @staticmethod
    def _new_stream_state():
        return {
            'text': '',
            'complete': False,
            'started_at': None,
            'updated_at': None,
            'finished_at': None,
            'error': '',
        }

    def _debug_event(self, job, kind, *, stage=None, platform=None, message='', detail=None, at=None):
        with self.lock:
            self._debug_event_unlocked(job, kind, stage=stage, platform=platform,
                                       message=message, detail=detail, at=at)

    def _debug_event_unlocked(self, job, kind, *, stage=None, platform=None, message='', detail=None, at=None):
        """Persist a small, safe execution event for the optional debug view.

        Events intentionally contain labels and timings only. Prompts, model
        payloads, tool arguments and tool output are never copied into the
        workflow record. Lifecycle events are kept for every job; detailed
        runtime events are only emitted when debug mode is enabled.
        """
        if not job.get('debug_mode') and kind not in {'stage_started', 'stage_finished', 'stage_blocked', 'stage_failed'}:
            return
        now = float(at or time.time())
        stage_value = job.get('stages', {}).get(stage) if stage else None
        started = stage_value.get('started_at') if isinstance(stage_value, dict) else None
        event = {
            'id': uuid4().hex[:10],
            'at': now,
            'kind': str(kind),
            'level': 'error' if kind in {'stage_failed', 'stage_blocked'} else 'success' if kind == 'stage_finished' else 'info',
            'stage': stage,
            'platform': platform,
            'task': str(message)[:240],
            'message': str(message)[:240],
        }
        if started:
            event['elapsed_seconds'] = round(max(0.0, now - float(started)), 3)
            event['elapsed_ms'] = round(max(0.0, now - float(started)) * 1000)
        if isinstance(detail, dict) and job.get('debug_mode'):
            event['details'] = {str(k): str(v)[:240] for k, v in detail.items() if v is not None}
            if detail.get('tool'):
                event['tool'] = str(detail['tool'])[:120]
        if stage and isinstance(stage_value, dict):
            if kind in {'stage_started', 'agent_event'}:
                stage_value['current_task'] = str(message)[:240]
            elif kind in {'stage_finished', 'stage_blocked', 'stage_failed'}:
                stage_value['current_task'] = ''
        if kind in {'stage_started', 'agent_event'}:
            job['current_task'] = str(message)[:240]
        elif kind in {'stage_finished', 'stage_blocked', 'stage_failed'}:
            job['current_task'] = ''
        events = job.setdefault('debug_events', [])
        events.append(event)
        # A long agent session can emit many tool lifecycle events. Keep the
        # persisted job responsive and retain the newest evidence.
        if len(events) > 2000:
            del events[:-2000]
        self._save(job)

    def _begin_live_stream(self, job, stage, platform=None):
        now = time.time()
        job['live_stream'] = {
            'stage': stage, 'platform': platform, 'text': '', 'complete': False,
            'status': 'running', 'started_at': now, 'updated_at': now,
            'finished_at': None, 'chars': 0,
        }
        self._save(job)

    def _update_live_stream(self, job, text, *, complete=False, status='running', error=''):
        live = job.setdefault('live_stream', {})
        live.update(text=text, complete=bool(complete), status=status,
                    updated_at=time.time(), chars=len(text))
        if error:
            live['error'] = str(error)[:240]
        if complete:
            live['finished_at'] = live.get('updated_at')
        self._save(job)

    def _prepare_compact_retry(self, job):
        """Reset only the unfinished compact work while retaining evidence.

        A failed compact compose may have produced some platform files.  Those
        files are treated as completed checkpoints; only missing platforms are
        requested again.  Existing research and historical legacy attempts are
        never overwritten.
        """
        stages = job['stages']
        streaming = job.setdefault('streaming_outputs', {})
        research_ok = stages.get('discovery', {}).get('status') == 'completed' and self._artifact_is_valid(self.outputs, stages['discovery'].get('artifact'))
        if not research_ok:
            for key in ('discovery', 'topic', 'master', 'adaptation', 'quality', 'archive'):
                stages[key].update(
                    status='pending', reason='', artifact=None,
                    started_at=None, finished_at=None, duration_seconds=None, duration_ms=None,
                )
            job['streaming_outputs'] = {
                platform: self._new_stream_state()
                for platform in job.get('platforms') or []
            }
            return
        stages['discovery'].update(status='completed', reason='')
        research_path = self.outputs / stages['discovery']['artifact']
        if not self._artifact_is_valid(self.outputs, stages.get('topic', {}).get('artifact')):
            topic_artifact = research_path.parent / '02-topic.md'
            topic_artifact.write_text(
                'compact-v2 研究简报（由研究阶段产物整理，未新增模型调用）\n\n' + research_path.read_text(encoding='utf-8'),
                encoding='utf-8',
            )
            stages['topic'].update(status='completed', reason='', artifact=str(topic_artifact.relative_to(self.outputs)))
        for key in ('master', 'adaptation', 'quality', 'archive'):
            stages[key].update(
                status='pending', reason='', artifact=None,
                started_at=None, finished_at=None, duration_seconds=None, duration_ms=None,
            )
        # Preserve a successfully checkpointed platform on compose retry, but
        # discard partial text for platforms that still need a model call.
        folder = self.outputs / f'workflow-{job["id"]}'
        for platform in job.get('platforms') or []:
            filename = FINAL_ARTIFACTS[platform]
            path = folder / filename
            if self._artifact_is_valid(self.outputs, str(path.relative_to(self.outputs))) if path.is_file() else False:
                text = path.read_text(encoding='utf-8')
                state = streaming.setdefault(platform, self._new_stream_state())
                state.update(text=text, complete=True, error='', updated_at=time.time(), finished_at=state.get('finished_at') or time.time())
            else:
                streaming[platform] = self._new_stream_state()

    def _missing_final_artifacts(self, job):
        folder = self.outputs / f'workflow-{job["id"]}'
        missing = []
        for platform in job['platforms']:
            filename = FINAL_ARTIFACTS[platform]
            path = folder / filename
            try:
                path.resolve().relative_to(self.outputs.resolve())
                valid = path.is_file() and not path.is_symlink() and bool(path.read_text(encoding='utf-8').strip())
            except (OSError, ValueError, UnicodeError):
                valid = False
            if not valid:
                missing.append(filename)
        return missing

    def _invoke_runner(self, prompt, session_id):
        if self.session_runner is not None:
            return self.session_runner(prompt, session_id)
        try:
            return self.runner(prompt, session_id)
        except TypeError as exc:
            # Existing embedders use the original one-argument runner.  Only
            # fall back for a signature mismatch; model/runtime TypeErrors
            # raised inside a valid runner must still fail the stage.
            if 'positional argument' not in str(exc) and 'required positional' not in str(exc):
                raise
            return self.runner(prompt)

    @staticmethod
    def _blocked_reason(content):
        """Turn an explicit runner refusal into a durable blocked stage.

        The runner contract is still text for compatibility.  Models sometimes
        put a short preamble before the status (for example,
        ``结论：主题事实核验 BLOCKED。``), so inspect the opening status
        lines rather than only the first character of the response.  The body
        is preserved in the stage artifact only for completed content; blocked
        responses remain in the job reason and are retryable.
        """
        if isinstance(content, dict):
            status = str(content.get("status") or "").strip().lower()
            if status in {"blocked", "not_configured", "unsupported"}:
                return str(content.get("reason") or content.get("message") or status)
            return ""
        if not isinstance(content, str):
            return ""
        lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
        if not lines:
            return ""
        truncation = re.compile(
            r"reply truncated|output token limit|stopreason\s*[=:：]?\s*(?:max_tokens|length|model_length)|"
            r"被截断|输出.{0,8}(?:上限|限制)|达到.{0,8}token",
            re.IGNORECASE,
        )
        if truncation.search(content):
            return '模型输出被截断：已达到单次输出上限；实时预览已保留，请从当前阶段重试。'
        markers = ("BLOCKED", "NOT_CONFIGURED", "UNSUPPORTED")
        # Keep the scan near the response header.  This catches a status after
        # a one or two line explanation while avoiding ordinary prose that may
        # quote the marker later in a draft.
        context_words = re.compile(
            r"结论|阻断|缺口|不可|不能|无法|未配置|未开通|权限|失败|拒绝|状态|完成|主体|结果",
            re.IGNORECASE,
        )
        marker_pattern = re.compile(r"(?<![A-Z0-9_])(?:BLOCKED|NOT_CONFIGURED|UNSUPPORTED)(?![A-Z0-9_])", re.IGNORECASE)
        for line in lines[:8]:
            upper = line.upper()
            for marker in markers:
                if upper.startswith(marker):
                    return line
            match = marker_pattern.search(line)
            if match and (context_words.search(line) or match.end() >= len(line.rstrip("。.!！？:：；;"))):
                return line
        return ""

    @staticmethod
    def _failure_reason(exc):
        """Expose a safe, actionable class of runner failure to the UI.

        Runner exceptions can contain request details or local paths. Keep the
        durable job record useful without copying those details into a user
        visible error or a persisted artifact.
        """
        message = str(exc or '').lower()
        if 'thinking level' in message and 'not supported' in message:
            return '当前模型不支持所选思考档位，已停止本阶段；请使用兼容档位后重试。'
        if (
            ('stopreason' in message and 'length' in message)
            or 'context length' in message
            or 'maximum context' in message
            or 'prompt too long' in message
            or 'context-pressure' in message
            or 'estimatedprompttokens' in message
            or "couldn't generate a response" in message
        ):
            return '本阶段研究内容过长，超过模型单次处理上限；已保留已有阶段产物，可从当前阶段重试。'
        if 'timeout' in message or 'timed out' in message or '超时' in message:
            return '模型请求超时；请稍后重试，或先检查模型连接。'
        if 'model provider temporarily unavailable' in message or 'model provider connection failed' in message:
            return '模型服务暂时不可用或连接失败；请稍后重试，或检查服务商网络状态。'
        if (
            'model returned an invalid response' in message
            or 'model returned an empty response' in message
            or '平台成稿 json 缺少非空 content' in message
            or '平台成稿未返回有效内容' in message
        ):
            return '模型返回格式异常，未形成可编辑终稿；请稍后重试，当前主题和研究结果已保留。'
        if '归档前序产物缺失' in message:
            return '归档前检查发现阶段产物缺失；请从缺失阶段重试，完成后再归档。'
        if '平台终稿未生成' in message:
            return '平台终稿未生成；请从平台适配阶段重试，完成后再归档。'
        if (
            'arrearage' in message
            or 'overdue-payment' in message
            or 'overdue payment' in message
            or 'account overdue' in message
            or '欠费' in message
        ):
            return '模型账户欠费或账户状态异常；请到服务商控制台处理欠费并开启可用额度，或在连接与设置更换可用 API Key 后重试。'
        if (
            '402' in message
            or 'billing' in message
            or 'insufficient balance' in message
            or 'insufficient credit' in message
            or '余额不足' in message
            or '余额或额度' in message
            or 'temporarily disabled' in message
            or 'billing failure' in message
            or '额度' in message
            or '额度已用尽' in message
        ):
            return '模型账户余额或额度不足；请到服务商控制台充值，或在连接与设置更换可用 API Key 后重试。'
        if (
            'authentication failed' in message
            or 're-authenticate' in message
            or '认证或账户状态异常' in message
            or '账户状态异常' in message
        ):
            return '模型认证或账户状态异常；请到连接与设置检查 API Key，并在服务商控制台处理欠费或开通模型后重试。'
        if '429' in message or 'rate limit' in message or 'too many requests' in message or '请求过于频繁' in message:
            return '模型请求过于频繁；请稍后重试，或检查服务商的速率与额度限制。'
        if '400' in message or 'invalid parameter' in message or 'bad request' in message:
            return '模型请求参数不兼容；请在连接与设置检查模型名称和思考档位。'
        if (
            '403' in message
            or 'forbidden' in message
            or 'permission' in message
            or 'model not found' in message
            or 'model_not_found' in message
            or '模型未开通' in message
            or '模型不可用' in message
        ):
            return '当前模型未开通或没有调用权限；请在服务商控制台开启该模型，或在连接与设置更换可用模型。'
        if 'unauthorized' in message or 'authentication' in message or '401' in message or 'api key' in message:
            return '模型认证失败；请到连接与设置重新检查 API Key。'
        if 'no route-compatible authentication' in message or 'provider' in message and 'auth' in message:
            return '模型服务没有可用的认证通道；请到连接与设置检查服务商配置。'
        if 'aborted' in message or 'cancelled' in message or 'interrupted' in message:
            return '模型任务被中断；可以从本阶段继续重试。'
        if 'agent 执行失败' in message or 'agent' in message and ('失败' in message or 'failed' in message):
            return '研究代理调用失败；请检查当前模型网关和运行服务日志后重试。'
        return '本阶段调用模型失败；请检查连接与设置后重试。'

    def _local_quality_fallback(self, job):
        """Produce an honest mechanical review when the review model is out of credit.

        The fallback never claims that persona or human-expression review ran;
        it only confirms the files that are present and leaves the draft in a
        clearly review-required state so archive delivery remains usable.
        """
        folder = self.outputs / f'workflow-{job["id"]}'
        present = []
        missing = []
        for platform in job.get('platforms') or []:
            filename = FINAL_ARTIFACTS.get(platform)
            if not filename:
                continue
            path = folder / filename
            if path.is_file() and not path.is_symlink() and path.read_text(encoding='utf-8').strip():
                present.append(filename)
            else:
                missing.append(filename)
        return (
            '质量检查状态：需人工复核（模型审校因服务商额度不足未执行）。\n\n'
            f'通过项：已检查终稿文件存在且非空：{"、".join(present) or "无"}。\n'
            f'风险项：缺失终稿：{"、".join(missing) or "无"}；未执行来源、事实、画像和真人表达的模型审校。\n'
            '人工复核项：发布前请核对来源链接、价格与时间等事实，确认平台长度和个人表达，再决定是否发布。'
        )

    @staticmethod
    def _is_billing_error(exc):
        message = str(exc or '').lower()
        return any(marker in message for marker in (
            '402', '余额不足', '额度不足', '账户余额', 'insufficient balance', 'insufficient credit',
            'arrearage', 'overdue payment', 'billing failure', 'billing error',
        ))

    def _invoke_compose_runner(self, prompt, session_id, on_delta=None):
        if self.compose_runner is None:
            raise RuntimeError('compact compose runner 未配置')
        if on_delta is not None and self.compose_stream_runner is not None:
            try:
                return self.compose_stream_runner(prompt, session_id, on_delta)
            except TypeError as exc:
                # Keep compatibility with a two-argument stream adapter while
                # allowing TypeErrors raised by the actual model call to fail.
                if 'positional argument' not in str(exc) and 'required positional' not in str(exc):
                    raise
                return self.compose_stream_runner(prompt, session_id)
        try:
            return self.compose_runner(prompt, session_id)
        except TypeError:
            # Keep small embedders convenient while production uses the
            # session-aware signature for isolated transcripts.
            return self.compose_runner(prompt)

    @staticmethod
    def _compose_content(value, platform):
        """Normalize a compose response without accepting ambiguous envelopes.

        Plain text remains supported for lightweight adapters.  If a model
        returns JSON (including a fenced JSON response), it must contain a
        non-empty ``content``/``text`` field and, when present, the requested
        platform.  Statuses such as BLOCKED never become a draft artifact.
        """
        parsed = value
        if isinstance(value, str):
            stripped = value.strip()
            candidate = stripped
            if candidate.startswith('```'):
                lines = candidate.splitlines()
                if len(lines) >= 3:
                    candidate = '\n'.join(lines[1:-1]).strip()
            if candidate.startswith('{') and candidate.endswith('}'):
                try:
                    parsed = json.loads(candidate)
                except (TypeError, ValueError):
                    parsed = value
        if isinstance(parsed, dict):
            status = str(parsed.get('status') or '').strip().lower()
            if status in {'blocked', 'failed', 'unsupported'}:
                raise RuntimeError(str(parsed.get('reason') or parsed.get('message') or status))
            declared = str(parsed.get('platform') or '').strip()
            if declared and declared not in {platform, TARGETS.get(platform, '')}:
                raise RuntimeError('模型返回了错误的平台终稿')
            content = parsed.get('content') or parsed.get('text')
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError('平台成稿 JSON 缺少非空 content')
            return content.strip()
        if not isinstance(parsed, str) or not parsed.strip():
            raise RuntimeError('平台成稿未返回有效内容')
        return parsed.strip()

    def _compact_prompt(self, job, platform, research):
        target = TARGETS[platform]
        filename = FINAL_ARTIFACTS[platform]
        constraints = {
            'wechat-oa': '标题最多64字，正文约1800至2500字，适合公众号长文；自然收束，不添加关注/进群/点赞引流。',
            'xiaohongshu': '标题最多20字，正文不超过1000字；适合移动端分段，附话题和配图建议，但不要声称图片已生成。',
            'douyin': '提供不超过55字的发布文案，并包含可执行的开场、口播、分镜和字幕；不要声称视频或音频已生成。',
        }[platform]
        revision = job.get('revision') or {}
        revision_block = ''
        if revision:
            revision_block = (
                '这是一次针对现有草稿的修改。只按修改意见改动指出的部分，保留其他内容、事实边界和平台格式；'
                '不要把原稿当成新的研究主题，也不要凭空补写原稿没有的事实。\n'
                f'修改意见：{revision.get("instruction", "")}\n'
                f'原稿（最多 8000 字）：\n{revision.get("draft", "")}\n'
            )
        return (
            f'主题：{job["topic"]}\n画像：{job["profile"] or "通用"}\n'
            f'唯一目标平台：{target}（{platform}）\n'
            '阶段：compact-v2 直接成稿\n'
            '只返回该平台的一份可编辑正文，不要联网、不要调用 exec/shell/python/node/npm、不要写文件、不要发布。\n'
            f'平台约束：{constraints}\n'
            '正文必须保留事实与来源边界；来源不可核验时明确写待核验，不得虚构经历、数据、引用或发布结果。\n'
            f'平台终稿将由后端写入 {filename}；不要输出其他平台内容。\n'
            f'{revision_block}'
            '前置研究与简报如下：\n'
            f'{research[-50000:]}\n'
            '请直接返回完整终稿文本，不要解释生成过程。'
        )

    def _write_compact_artifact(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)

    def _run_compact(self, job_id):
        """Run compact-v2 without routing every stage through a model.

        Discovery is one bounded model call.  Topic/master/adaptation are
        materialized locally from that evidence and one compose call per
        selected platform.  Quality is deliberately mechanical and keeps the
        draft in human-review-required state.
        """
        job = self.get(job_id)
        folder = self.outputs / f'workflow-{job_id}'
        folder.mkdir(parents=True, exist_ok=True)

        def begin(key):
            with self.lock:
                now = time.time()
                stage = job['stages'][key]
                stage.update(status='running', reason='', started_at=now)
                if not job.get('started_at'):
                    job['started_at'] = now
                job.update(status='running', current=key)
                self._save(job)
            return now

        def finish(key, started, artifact=None, reason=''):
            with self.lock:
                finished = time.time()
                stage = job['stages'][key]
                stage.update(
                    status='completed', reason=reason,
                    finished_at=finished,
                    duration_seconds=round(finished - started, 3),
                    # Keep the old field for any diagnostic reader that used
                    # it before the compact timing contract was introduced.
                    duration_ms=round((finished - started) * 1000),
                )
                if artifact:
                    stage['artifact'] = artifact
                self._save(job)

        # One gateway check protects both model phases.  A missing gateway is
        # a blocked research stage, never a fake local success.
        if not self.gateway():
            with self.lock:
                job.update(status='blocked', current=None)
                job['stages']['discovery'].update(status='blocked', reason='BLOCKED：模型/研究网关未配置或不可用。配置后可从研究阶段重试，已有产物保留。')
                self._save(job)
            return

        research_stage = job['stages']['discovery']
        if research_stage.get('status') != 'completed' or not self._artifact_is_valid(self.outputs, research_stage.get('artifact')):
            started = begin('discovery')
            research_prompt = (
                f'主题：{job["topic"]}\n画像：{job["profile"] or "通用"}\n阶段：compact-v2 研究与简报\n'
                '只做一次有限研究：最多核验 3 个一手来源、最多两轮检索；不可访问就记录 BLOCKED 和缺口。'
                '输出一份简洁研究简报，包含事实、来源链接、观察日期、读者任务、核心承诺、平台写作注意事项和待核验项。'
                '不要写平台终稿，不要调用 exec/shell/python/node/npm，不要发布。\n'
                f'主题补充：{job["topic"]}'
            )
            try:
                content = self._invoke_runner(research_prompt, f'workflow-{job_id}-compact-research-attempt-{job.get("attempt", 1)}')
                blocked = self._blocked_reason(content)
                if blocked:
                    with self.lock:
                        finished = time.time()
                        research_stage.update(
                            status='blocked', reason=blocked, finished_at=finished,
                            duration_seconds=round(max(0.0, finished - started), 3),
                            duration_ms=round(max(0.0, finished - started) * 1000),
                        )
                        job.update(status='blocked', current=None)
                        self._save(job)
                    return
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError('研究阶段未返回有效内容')
                research_path = folder / '01-discovery.md'
                self._write_compact_artifact(research_path, content.strip())
                finish('discovery', started, str(research_path.relative_to(self.outputs)))
            except Exception as exc:
                with self.lock:
                    finished = time.time()
                    research_stage.update(
                        status='failed', reason=self._failure_reason(exc), finished_at=finished,
                        duration_seconds=round(max(0.0, finished - started), 3),
                        duration_ms=round(max(0.0, finished - started) * 1000),
                    )
                    job.update(status='failed', current=None)
                    self._save(job)
                return

        research_path = self.outputs / job['stages']['discovery']['artifact']
        research = research_path.read_text(encoding='utf-8')

        # Topic is a local checkpoint derived from research, so a compose
        # retry does not spend another model call or mutate prior evidence.
        topic_stage = job['stages']['topic']
        if topic_stage.get('status') != 'completed' or not self._artifact_is_valid(self.outputs, topic_stage.get('artifact')):
            started = begin('topic')
            topic_path = folder / '02-topic.md'
            self._write_compact_artifact(topic_path, 'compact-v2 研究简报（未新增模型调用）\n\n' + research)
            finish('topic', started, str(topic_path.relative_to(self.outputs)), '由研究阶段产物整理')

        # Compose only missing platform files.  Independent calls run in a
        # short local pool, capped at three, and each result is checkpointed
        # atomically before another platform is attempted.
        compose_started = begin('master')
        missing = []
        for platform in job.get('platforms') or []:
            path = folder / FINAL_ARTIFACTS[platform]
            if not (path.is_file() and not path.is_symlink() and path.read_text(encoding='utf-8').strip()):
                missing.append(platform)
        results = {}
        errors = {}

        def compose_one(platform):
            prompt = self._compact_prompt(job, platform, research)
            session_id = f'workflow-{job_id}-compact-compose-{platform}-attempt-{job.get("attempt", 1)}'
            state = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
            stream_buffer = {'text': str(state.get('text') or ''), 'last_saved': 0.0, 'last_chars': 0}
            started_at = time.time()

            def on_delta(delta):
                if not isinstance(delta, str) or not delta:
                    return
                stream_buffer['text'] += delta
                now = time.time()
                # Keep the job observable without writing the JSON file for
                # every token.  The character threshold keeps long outputs
                # responsive even when the provider emits bursts.
                if now - stream_buffer['last_saved'] < 0.2 and len(stream_buffer['text']) - stream_buffer['last_chars'] < 256:
                    return
                with self.lock:
                    current = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
                    current.update(
                        text=stream_buffer['text'], complete=False,
                        started_at=current.get('started_at') or started_at,
                        updated_at=now, chars=len(stream_buffer['text']), error='',
                    )
                    self._save(job)
                stream_buffer['last_saved'] = now
                stream_buffer['last_chars'] = len(stream_buffer['text'])

            value = self._invoke_compose_runner(
                prompt,
                session_id,
                on_delta=on_delta if self.compose_stream_runner is not None else None,
            )
            value = self._compose_content(value, platform)
            blocked = self._blocked_reason(value)
            if blocked:
                raise RuntimeError(blocked)
            # Flush the last short chunk and mark the preview complete only
            # after the full response has passed platform/content validation.
            with self.lock:
                finished_at = time.time()
                current = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
                current.update(
                    text=value, complete=True,
                    started_at=current.get('started_at') or started_at,
                    updated_at=finished_at, finished_at=finished_at,
                    chars=len(value), error='',
                )
                self._save(job)
            return value

        if missing:
            with ThreadPoolExecutor(max_workers=min(3, len(missing)), thread_name_prefix='creatoros-compose') as pool:
                futures = {pool.submit(compose_one, platform): platform for platform in missing}
                for future, platform in ((future, futures[future]) for future in futures):
                    try:
                        results[platform] = future.result()
                    except Exception as exc:
                        errors[platform] = self._failure_reason(exc)
                        with self.lock:
                            state = job.setdefault('streaming_outputs', {}).setdefault(platform, self._new_stream_state())
                            state.update(complete=False, updated_at=time.time(), error=errors[platform], chars=len(state.get('text') or ''))
                            self._save(job)
            for platform, content in results.items():
                self._write_compact_artifact(folder / FINAL_ARTIFACTS[platform], content)

        if errors:
            with self.lock:
                finished = time.time()
                job['stages']['master'].update(
                    status='failed',
                    reason='；'.join(f'{TARGETS[p]}：{r}' for p, r in errors.items()),
                    finished_at=finished,
                    duration_seconds=round(finished - compose_started, 3),
                    duration_ms=round((finished - compose_started) * 1000),
                )
                job.update(status='failed', current=None)
                self._save(job)
            return

        master_path = folder / '03-master.md'
        master_lines = ['compact-v2 直接成稿结果（平台终稿已分别落盘）', '']
        master_lines.extend(f'- {TARGETS[p]}：{FINAL_ARTIFACTS[p]}' for p in job['platforms'])
        self._write_compact_artifact(master_path, '\n'.join(master_lines))
        finish('master', compose_started, str(master_path.relative_to(self.outputs)), '由平台成稿调用完成')

        adaptation_started = begin('adaptation')
        adaptation_path = folder / '04-adaptation.md'
        self._write_compact_artifact(adaptation_path, 'compact-v2 平台终稿已按目标平台分别生成。\n\n' + '\n'.join(f'- {TARGETS[p]}：{FINAL_ARTIFACTS[p]}' for p in job['platforms']))
        finish('adaptation', adaptation_started, str(adaptation_path.relative_to(self.outputs)), '后端完成文件契约校验')

        quality_started = begin('quality')
        present, missing_final, length_warnings = [], [], []
        limits = {'xiaohongshu': 1000, 'douyin': 4000, 'wechat-oa': 2500}
        for platform in job['platforms']:
            path = folder / FINAL_ARTIFACTS[platform]
            if not path.is_file() or path.is_symlink() or not path.read_text(encoding='utf-8').strip():
                missing_final.append(FINAL_ARTIFACTS[platform])
                continue
            text = path.read_text(encoding='utf-8').strip()
            present.append(FINAL_ARTIFACTS[platform])
            if len(text) > limits[platform]:
                length_warnings.append(f'{FINAL_ARTIFACTS[platform]} 超过本地长度提示 {limits[platform]} 字')
        quality_path = folder / '05-quality.md'
        quality = (
            'compact-v2 质量检查：需人工复核\n\n'
            f'通过项：终稿文件存在且非空：{"、".join(present) or "无"}。\n'
            f'机械风险：{"、".join(missing_final + length_warnings) or "无"}。\n'
            '未执行项：来源事实、画像一致性、真人表达和发布前平台审核；模型自审不能替代人工验收。\n'
            '内容状态：draft；human_review_required=true。'
        )
        self._write_compact_artifact(quality_path, quality)
        finish('quality', quality_started, str(quality_path.relative_to(self.outputs)), '仅完成本地机械检查')

        archive_started = begin('archive')
        if missing_final:
            with self.lock:
                job['stages']['adaptation'].update(status='failed', reason='平台终稿未生成：' + '、'.join(missing_final))
                job.update(status='failed', current=None)
                self._save(job)
            return
        # Reuse the existing archive branch's safety checks by materializing a
        # compact completion and writing a minimal manifest here.
        archive_path = folder / '06-archive.md'
        archive_content = json.dumps({'content_status': 'draft', 'published': False, 'media_verified': False, 'human_review': 'required', 'execution_mode': 'compact-v2'}, ensure_ascii=False, indent=2)
        self._write_compact_artifact(archive_path, archive_content)
        manifest = {'title': job['topic'], 'kind': 'article', 'status': 'draft', 'summary': 'compact-v2 两阶段草稿；事实、媒体和真人表达仍需人工复核。', 'platform': ','.join(job['platforms']), 'execution_mode': 'compact-v2', 'deliverables': [FINAL_ARTIFACTS[p] for p in job['platforms']] + ['01-discovery.md', '02-topic.md', '03-master.md', '04-adaptation.md', '05-quality.md', '06-archive.md']}
        self._write_compact_artifact(folder / '.creatoros.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        finish('archive', archive_started, str(archive_path.relative_to(self.outputs)))
        with self.lock:
            job.update(status='completed', current=None, content_status='draft', published=False)
            self._save(job)

    def _run(self, job_id):
        try:
            job = self.get(job_id)
            if job.get('execution_mode') == getattr(self, 'default_execution_mode', '__no_easel_agent__') and hasattr(self, '_run_easel_agent'):
                self._run_easel_agent(job_id)
                return
            if job.get('execution_mode') == 'compact-v2' and self.compose_runner is not None:
                self._run_compact(job_id)
                return
            for index, (key, label) in enumerate(STAGES):
                if job['stages'][key]['status'] == 'completed':
                    continue
                with self.lock:
                    job.update(status='running', current=key)
                    job['stages'][key].update(status='running', reason='')
                    self._save(job)
                if key != 'archive' and not self.gateway():
                    with self.lock:
                        job.update(status='blocked', current=None)
                        job['stages'][key].update(status='blocked', reason='BLOCKED：模型/研究网关未配置或不可用。配置后可从本阶段重试，已有产物保留。')
                        self._save(job)
                    return
                folder = self.outputs / f'workflow-{job_id}'
                folder.mkdir(parents=True, exist_ok=True)
                if key == 'archive':
                    # Do not let the archive stage turn a partially written
                    # project into a successful workflow.  A prior stage can
                    # look completed in the JSON record after a manual
                    # restore or an interrupted filesystem write, so verify
                    # the actual artifacts immediately before creating the
                    # manifest.  The archive itself is the only stage that
                    # has not been materialized yet at this point.
                    missing = []
                    for prior_key, _ in STAGES[:-1]:
                        prior = job['stages'].get(prior_key) or {}
                        artifact = prior.get('artifact')
                        artifact_path = self.outputs / artifact if artifact else None
                        inside_outputs = False
                        if artifact_path:
                            try:
                                artifact_path.resolve(strict=False).relative_to(self.outputs.resolve())
                                inside_outputs = True
                            except ValueError:
                                inside_outputs = False
                        if (
                            prior.get('status') != 'completed'
                            or not artifact_path
                            or not inside_outputs
                            or not artifact_path.is_file()
                            or artifact_path.is_symlink()
                            or artifact_path.stat().st_size == 0
                        ):
                            missing.append(prior_key)
                    if missing:
                        raise RuntimeError('归档前序产物缺失：' + '、'.join(missing))
                    missing_final = self._missing_final_artifacts(job)
                    if missing_final:
                        # Make retry() restart at adaptation instead of
                        # repeatedly retrying archive against the same missing
                        # final files.  The adaptation report remains on disk
                        # for diagnosis, while its stage is marked incomplete.
                        with self.lock:
                            job['stages']['adaptation'].update(
                                status='failed',
                                reason='平台终稿未生成：' + '、'.join(missing_final),
                            )
                            self._save(job)
                        raise RuntimeError('平台终稿未生成：' + '、'.join(missing_final))
                    archive_artifact = f'{folder.relative_to(self.outputs).as_posix()}/{index + 1:02d}-{key}.md'
                    archive_stages = {stage_key: dict(value) for stage_key, value in job['stages'].items()}
                    # The archive document is being written in this branch;
                    # expose its final state in the manifest instead of the
                    # transient ``running``/empty artifact snapshot.
                    archive_stages[key].update(status='completed', artifact=archive_artifact, reason='')
                    final_deliverables = [FINAL_ARTIFACTS[p] for p in job['platforms']]
                    manifest = dict(
                        title=job['topic'], kind='article', status='draft',
                        summary='六阶段草稿已归档；事实、媒体和真人表达仍需人工复核。',
                        platform=','.join(job['platforms']),
                        skills={stage_key: value.get('skills', []) for stage_key, value in archive_stages.items()},
                        deliverables=[v['artifact'].split('/')[-1] for v in archive_stages.values() if v.get('artifact')] + final_deliverables,
                    )
                    (folder / '.creatoros.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
                    content = json.dumps({
                        'content_status': 'draft', 'published': False, 'media_verified': False,
                        'human_review': 'required', 'stages': archive_stages,
                    }, ensure_ascii=False, indent=2)
                else:
                    previous = '\n\n'.join(
                        (self.outputs / v['artifact']).read_text()
                        for v in job['stages'].values() if v.get('artifact')
                    )
                    skills = job['stages'][key].get('skills') or self._stage_skills(job, key)
                    skill_line = '、'.join(f'/{name}' for name in skills)
                    project_dir = folder.relative_to(self.outputs).as_posix()
                    selected_platforms = '、'.join(TARGETS[p] for p in job['platforms'])
                    final_contract = ''
                    if key == 'adaptation':
                        final_contract = (
                            '平台终稿文件契约（必须满足）：\n'
                            + '\n'.join(
                                f'- {TARGETS[p]}：outputs/{project_dir}/{FINAL_ARTIFACTS[p]}'
                                for p in job['platforms']
                            )
                            + '\n04-adaptation.md 仅是阶段报告；必须将每个已选平台的可编辑终稿以 UTF-8 写入上列文件，'
                            '文件必须非空。未选平台不得创建终稿文件；无法写入时明确 BLOCKED，不得声称适配完成。\n'
                        )
                    prompt = (
                        f'主题：{job["topic"]}\n画像：{job["profile"] or "通用"}\n'
                        f'目标平台（仅限这些，不得新增）：{selected_platforms}\n'
                        '平台硬约束：只处理本作业已选择的平台；未选平台不得生成、扩写、改写或补全任何内容，'
                        '即使前序产物提到其他平台，也必须忽略，不得默认输出三平台版本。\n'
                        f'阶段：{label}\n'
                        f'工作流项目目录：outputs/{project_dir}\n'
                        f'{final_contract}'
                        '先读取 workspace/AGENTS.md 和 workspace/SOUL.md，再按其中规则工作。\n'
                        '技能目录是 workspace/skills/<skill-name>，共享脚本是 workspace/shared/ 或 workspace/skills/shared/；不要猜测其他路径。\n'
                        f'本阶段必须路由并执行的 Skills：{skill_line}\n'
                        f'{INSTRUCTIONS[key]}\n'
                        '只做当前阶段，失败或证据不足时明确 BLOCKED；禁止登录、发布、发消息或改配置；禁止安装依赖、运行 pip/npm install 或修改运行环境，缺依赖直接 BLOCKED。'
                        f'\n前序产物：\n{previous[-60000:]}'
                    )
                    # Keep each stage in its own transcript.  The prompt still
                    # carries prior artifacts explicitly, but a shared
                    # OpenClaw transcript would accumulate every stage's
                    # thinking and eventually exceed the model context.  A
                    # retry gets a fresh transcript for the failed stage too.
                    session_id = f'workflow-{job_id}-{key}-attempt-{job.get("attempt", 1)}'
                    try:
                        content = self._invoke_runner(prompt, session_id)
                    except Exception as exc:
                        if key == 'quality' and self._is_billing_error(exc):
                            content = self._local_quality_fallback(job)
                        else:
                            raise
                    blocked_reason = self._blocked_reason(content)
                    if blocked_reason:
                        with self.lock:
                            job.update(status='blocked', current=None)
                            job['stages'][key].update(status='blocked', reason=blocked_reason)
                            self._save(job)
                        return
                    if not isinstance(content, str) or not content.strip():
                        raise RuntimeError('模型未返回有效内容')
                artifact = folder / f'{index + 1:02d}-{key}.md'
                artifact.write_text(content, encoding='utf-8')
                with self.lock:
                    job['stages'][key].update(status='completed', artifact=str(artifact.relative_to(self.outputs)))
                    self._save(job)
            with self.lock:
                job.update(status='completed', current=None, content_status='draft', published=False)
                self._save(job)
        except Exception as exc:
            with self.lock:
                job = self.get(job_id)
                key = job.get('current')
                if key:
                    job['stages'][key].update(status='failed', reason=self._failure_reason(exc))
                job.update(status='failed', current=None)
                self._save(job)
        finally:
            with self.lock:
                # Compact and legacy paths both settle through this finally
                # block. Freeze the server-side clock exactly once so a
                # completed card cannot keep counting in the browser.
                job = self.get(job_id)
                if job.get('status') not in {'queued', 'running'} and not job.get('finished_at'):
                    finished = time.time()
                    started = job.get('attempt_started') or job.get('started_at') or job.get('created') or finished
                    job['finished_at'] = finished
                    job['duration_seconds'] = round(max(0.0, finished - started), 3)
                    job['duration_ms'] = round(max(0.0, finished - started) * 1000)
                for stage in job.get('stages', {}).values():
                    stage_started = stage.get('started_at')
                    stage_finished = stage.get('finished_at')
                    if stage_started and stage_finished and stage.get('duration_seconds') is None:
                        stage_duration = round(max(0.0, stage_finished - stage_started), 3)
                        stage['duration_seconds'] = stage_duration
                        stage['duration_ms'] = round(stage_duration * 1000)
                self._save(job)
                self.active.discard(job_id)
