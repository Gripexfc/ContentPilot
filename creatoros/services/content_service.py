from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from creatoros.adapters.demo_content import generate_content
from creatoros.db.models import (
    ArtifactRevision,
    Brief,
    ContentTask,
    CreatorProfile,
    CreatorProfileVersion,
    EditEvent,
    Memory,
    PlatformArtifact,
    TaskEvent,
    TaskInput,
)
from creatoros.domain.content import (ArtifactRevisionCreate, BriefRevisionCreate, ContentTaskCreate, MemoryDecision, PLATFORMS, QuickDraftCreate)
from creatoros.services.profile_service import _diff_values


class ContentServiceError(RuntimeError):
    code = "content_error"


class ContentTaskNotFound(ContentServiceError):
    code = "content_task_not_found"


class BriefNotFound(ContentServiceError):
    code = "brief_not_found"


class ArtifactNotFound(ContentServiceError):
    code = "artifact_not_found"


class MemoryNotFound(ContentServiceError):
    code = "memory_not_found"


class ContentConflict(ContentServiceError):
    code = "content_conflict"


class QuickDraftProfileRequired(ContentServiceError):
    code = "profile_required"


class InvalidContentState(ContentServiceError):
    code = "invalid_content_state"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _task_read(task: ContentTask) -> Dict[str, Any]:
    return {
        "id": task.id,
        "quick_draft_id": task.quick_draft_id,
        "profile_version_id": task.profile_version_id,
        "title": task.title,
        "status": task.status,
        "reader_problem": task.reader_problem,
        "author_angle": task.author_angle,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "archived_at": _iso(task.archived_at),
    }


def _brief_read(brief: Brief) -> Dict[str, Any]:
    return {
        "id": brief.id,
        "task_id": brief.task_id,
        "version_no": brief.version_no,
        "payload": brief.payload_json,
        "confirmation_status": brief.confirmation_status,
        "created_at": _iso(brief.created_at),
    }


def _revision_read(revision: ArtifactRevision) -> Dict[str, Any]:
    return {
        "id": revision.id,
        "revision_no": revision.revision_no,
        "parent_revision_id": revision.parent_revision_id,
        "content": revision.content_json,
        "profile_version_id": revision.profile_version_id,
        "brief_id": revision.brief_id,
        "source_ids": revision.source_ids_json,
        "memory_ids": revision.memory_ids_json,
        "generation_kind": revision.generation_kind,
        "created_at": _iso(revision.created_at),
    }


def _artifact_read(session: Session, artifact: PlatformArtifact) -> Dict[str, Any]:
    revision = session.get(ArtifactRevision, artifact.current_revision_id) if artifact.current_revision_id else None
    return {
        "id": artifact.id,
        "task_id": artifact.task_id,
        "platform": artifact.platform,
        "status": artifact.status,
        "current_revision_id": artifact.current_revision_id,
        "current_revision": _revision_read(revision) if revision else None,
        "created_at": _iso(artifact.created_at),
        "updated_at": _iso(artifact.updated_at),
    }


def _memory_read(memory: Memory) -> Dict[str, Any]:
    return {
        "id": memory.id,
        "kind": memory.kind,
        "statement": memory.statement,
        "source_event_id": memory.source_event_id,
        "confidence": memory.confidence,
        "scope": memory.scope_json,
        "confirmation_status": memory.confirmation_status,
        "confirmed_at": _iso(memory.confirmed_at),
        "created_at": _iso(memory.created_at),
    }


def _event(session: Session, task: ContentTask, event_type: str, from_status: Optional[str], to_status: Optional[str], payload: Dict[str, Any]) -> None:
    session.add(
        TaskEvent(
            id=str(uuid4()),
            task_id=task.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor="user",
            payload_json=payload,
            created_at=datetime.now(timezone.utc),
        )
    )


def _set_status(session: Session, task: ContentTask, status: str, event_type: str, payload: Dict[str, Any]) -> None:
    old = task.status
    if old == status:
        return
    task.status = status
    task.updated_at = datetime.now(timezone.utc)
    _event(session, task, event_type, old, status, payload)


def _current_brief(session: Session, task_id: str) -> Optional[Brief]:
    return session.scalar(
        select(Brief).where(Brief.task_id == task_id).order_by(desc(Brief.version_no)).limit(1)
    )


def _get_task(session: Session, task_id: str) -> ContentTask:
    task = session.get(ContentTask, task_id)
    if task is None:
        raise ContentTaskNotFound("内容任务不存在")
    return task


def create_task(session: Session, payload: ContentTaskCreate) -> ContentTask:
    with session.begin():
        profile = session.execute(select(CreatorProfile)).scalar_one_or_none()
        if profile is None or not profile.current_version_id:
            raise ContentConflict("请先创建并确认个人画像")
        version = session.get(CreatorProfileVersion, profile.current_version_id)
        if version is None:
            raise ContentConflict("个人画像当前版本不存在")
        now = datetime.now(timezone.utc)
        task = ContentTask(
            id=str(uuid4()),
            profile_version_id=version.id,
            title=payload.title.strip(),
            status="idea",
            reader_problem="",
            author_angle="",
            created_at=now,
            updated_at=now,
        )
        session.add(task)
        session.add(
            TaskInput(
                id=str(uuid4()),
                task_id=task.id,
                input_type=payload.input_type,
                text=payload.input_text,
                metadata_json=payload.input_metadata,
                parse_status="ready",
                created_at=now,
            )
        )
        session.flush()
        _event(session, task, "task_created", None, "idea", {"input_type": payload.input_type})
        return task


def _quick_draft_read(task: ContentTask, item: TaskInput, input_version: int) -> Dict[str, Any]:
    metadata = item.metadata_json or {}
    return {
        "quick_draft_id": task.quick_draft_id,
        "task_id": task.id,
        "input_id": item.id,
        "input_version": input_version,
        "title": task.title,
        "context": metadata.get("context", ""),
        "source": metadata.get("source", {}),
        "platform": metadata.get("platform", "wechat"),
        "mode": metadata.get("mode", "文章"),
        "skill": metadata.get("skill", ""),
        "workflow_id": metadata.get("workflow_id"),
        "output_artifact": metadata.get("output_artifact"),
        "output": item.text,
        "profile_version_id": task.profile_version_id,
        "persistence_state": "saved_input",
        "content_status": "draft",
        "publish_state": "not_started",
        "created_at": _iso(item.created_at),
        "updated_at": _iso(task.updated_at),
    }


def save_quick_draft(session: Session, payload: QuickDraftCreate) -> Dict[str, Any]:
    """Persist the raw quick workflow output without pretending it is an artifact.

    A confirmed profile is required because ContentTask deliberately keeps that
    provenance invariant. Re-saving identical output and metadata is idempotent;
    edited text or context becomes a new immutable TaskInput version.
    """
    with session.begin():
        profile = session.execute(select(CreatorProfile)).scalar_one_or_none()
        if profile is None or not profile.current_version_id:
            raise QuickDraftProfileRequired("请先创建并确认个人画像，再保存到内容库")
        version = session.get(CreatorProfileVersion, profile.current_version_id)
        if version is None or version.confirmation_status != "confirmed":
            raise QuickDraftProfileRequired("请先确认当前个人画像，再保存到内容库")
        task = session.scalar(select(ContentTask).where(ContentTask.quick_draft_id == payload.quick_draft_id))
        now = datetime.now(timezone.utc)
        content_hash = __import__("hashlib").sha256(payload.output.encode("utf-8")).hexdigest()
        metadata = {
            "quick_draft_id": payload.quick_draft_id,
            "context": payload.context,
            "source": payload.source,
            "platform": payload.platform,
            "mode": payload.mode,
            "skill": payload.skill,
            "workflow_id": payload.workflow_id,
            "output_artifact": payload.output_artifact,
            "content_sha256": content_hash,
        }
        if task is None:
            task = ContentTask(
                id=str(uuid4()), quick_draft_id=payload.quick_draft_id,
                profile_version_id=version.id, title=payload.topic,
                status="idea", reader_problem="", author_angle="",
                created_at=now, updated_at=now,
            )
            session.add(task)
            session.flush()
            _event(session, task, "quick_draft_saved", None, "idea", {"platform": payload.platform})
        elif task.status == "archived":
            raise InvalidContentState("内容任务已归档，请先重新打开")
        else:
            # A quick draft may be re-saved after the user edits its topic or
            # after the active profile changes. Keep the task's current
            # identity aligned with the latest save instead of leaving the
            # library title/profile stuck at the first version.
            task.title = payload.topic
            task.profile_version_id = version.id
            task.updated_at = now
        latest = session.scalar(
            select(TaskInput).where(TaskInput.task_id == task.id, TaskInput.input_type == "generated_markdown")
            .order_by(desc(TaskInput.created_at)).limit(1)
        )
        latest_metadata = (latest.metadata_json or {}) if latest else {}
        if latest and all(latest_metadata.get(key) == value for key, value in metadata.items()):
            input_version = int(latest_metadata.get("input_version", 1))
            return _quick_draft_read(task, latest, input_version)
        input_version = int((latest.metadata_json or {}).get("input_version", 0)) + 1 if latest else 1
        metadata["input_version"] = input_version
        item = TaskInput(
            id=str(uuid4()), task_id=task.id, input_type="generated_markdown",
            text=payload.output, metadata_json=metadata, parse_status="stored_only", created_at=now,
        )
        session.add(item)
        task.updated_at = now
        session.flush()
        _event(session, task, "quick_draft_saved", task.status, task.status,
               {"input_id": item.id, "input_version": input_version, "platform": payload.platform})
        return _quick_draft_read(task, item, input_version)


def list_quick_drafts(session: Session) -> List[Dict[str, Any]]:
    tasks = list(session.scalars(select(ContentTask).where(ContentTask.quick_draft_id.is_not(None)).order_by(desc(ContentTask.updated_at))))
    rows: List[Dict[str, Any]] = []
    for task in tasks:
        item = session.scalar(
            select(TaskInput).where(TaskInput.task_id == task.id, TaskInput.input_type == "generated_markdown")
            .order_by(desc(TaskInput.created_at)).limit(1)
        )
        if item is None:
            continue
        rows.append(_quick_draft_read(task, item, int((item.metadata_json or {}).get("input_version", 1))))
    return rows


def append_task_input(session: Session, task_id: str, input_type: str, text: str,
                      metadata: Optional[Dict[str, Any]] = None) -> TaskInput:
    """Append a user supplied source without rewriting the original task input."""
    with session.begin():
        task = _get_task(session, task_id)
        if task.status == "archived":
            raise InvalidContentState("任务已归档，请先重新打开")
        row = TaskInput(id=str(uuid4()), task_id=task.id, input_type=input_type,
                        text=text, metadata_json=metadata or {},
                        parse_status="stored_only" if input_type == "file" and not text else "ready",
                        created_at=datetime.now(timezone.utc))
        session.add(row)
        _event(session, task, "input_added", task.status, task.status,
               {"input_type": input_type, "metadata": metadata or {}})
        task.updated_at = datetime.now(timezone.utc)
        session.flush()
        return row


def export_artifact(session: Session, artifact_id: str, format_name: str) -> Tuple[str, str, str]:
    """Render a saved platform artifact for a user initiated local download."""
    artifact = session.get(PlatformArtifact, artifact_id)
    if artifact is None:
        raise ArtifactNotFound("平台产物不存在")
    revision = session.get(ArtifactRevision, artifact.current_revision_id) if artifact.current_revision_id else None
    if revision is None:
        raise ArtifactNotFound("平台产物没有当前版本")
    content = revision.content_json
    title = str(content.get("title") or (content.get("title_candidates") or ["未命名内容"])[0])
    if format_name == "json":
        return json.dumps({"platform": artifact.platform, "revision": _revision_read(revision)}, ensure_ascii=False, indent=2), "json", title
    if format_name == "html":
        body = []
        for key, value in content.items():
            if isinstance(value, list):
                value = "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in value) + "</ul>"
            else:
                value = f"<p>{html.escape(str(value))}</p>"
            body.append(f"<h2>{html.escape(str(key))}</h2>{value}")
        return "<!doctype html><meta charset='utf-8'><title>" + html.escape(title) + "</title><article><h1>" + html.escape(title) + "</h1>" + "".join(body) + "</article>", "html", title
    lines = [f"# {title}", "", f"平台：{artifact.platform}", f"版本：{revision.revision_no}", ""]
    for key, value in content.items():
        lines.append(f"## {key}")
        if isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines), "markdown", title


def list_tasks(session: Session) -> List[ContentTask]:
    return list(session.scalars(select(ContentTask).order_by(desc(ContentTask.updated_at))))


def get_task_detail(session: Session, task_id: str) -> Dict[str, Any]:
    task = _get_task(session, task_id)
    brief = _current_brief(session, task.id)
    artifacts = list(
        session.scalars(
            select(PlatformArtifact).where(PlatformArtifact.task_id == task.id).order_by(PlatformArtifact.platform)
        )
    )
    memories = list(
        session.scalars(
            select(Memory)
            .join(EditEvent, Memory.source_event_id == EditEvent.id)
            .join(ArtifactRevision, EditEvent.artifact_revision_id == ArtifactRevision.id)
            .join(PlatformArtifact, ArtifactRevision.artifact_id == PlatformArtifact.id)
            .where(PlatformArtifact.task_id == task.id)
            .order_by(desc(Memory.created_at))
        )
    )
    return {
        "task": _task_read(task),
        "latest_brief": _brief_read(brief) if brief else None,
        "artifacts": [_artifact_read(session, item) for item in artifacts],
        "memories": [_memory_read(item) for item in memories],
        "inputs": [{"id": row.id, "text": row.text, "input_type": row.input_type,
                    "metadata": row.metadata_json, "parse_status": row.parse_status,
                    "created_at": _iso(row.created_at)} for row in session.scalars(select(TaskInput).where(TaskInput.task_id == task.id))],
        "events": [{"id": row.id, "event_type": row.event_type, "from_status": row.from_status, "to_status": row.to_status, "payload": row.payload_json, "created_at": _iso(row.created_at)} for row in session.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.created_at))],
        "briefs": [_brief_read(row) for row in session.scalars(select(Brief).where(Brief.task_id == task.id).order_by(desc(Brief.version_no)))],
    }


def create_brief(session: Session, task_id: str) -> Brief:
    with session.begin():
        task = _get_task(session, task_id)
        profile_version = session.get(CreatorProfileVersion, task.profile_version_id)
        if profile_version is None:
            raise ContentConflict("任务绑定的画像版本不存在")
        inputs = list(session.scalars(select(TaskInput).where(TaskInput.task_id == task.id).order_by(TaskInput.created_at)))
        latest = _current_brief(session, task.id)
        if latest is not None:
            return latest
        next_no = 1
        snapshot = profile_version.snapshot_json
        readers = snapshot.get("readers") or []
        reader_problem = readers[0].get("name", "目标读者") if readers and isinstance(readers[0], dict) else "目标读者"
        author_angle = (snapshot.get("pillars") or ["从个人经验出发拆解问题"])[0]
        payload = {
            "task_title": task.title,
            "reader_problem": f"{reader_problem}需要判断“{task.title}”是否值得关注，以及下一步怎么做。",
            "author_angle": f"{author_angle}：把事实、作者判断和待验证内容分开。",
            "facts": [],
            "sources": [str(row.metadata_json.get("canonical_url") or row.metadata_json.get("original_name") or row.text)
                        for row in inputs if row.input_type in {"url", "hotspot", "file"}],
            "input_ids": [row.id for row in inputs],
            "research_gaps": ["补充一手来源", "核对关键数据、政策、价格或版本信息"],
            "platform_plan": {
                "wechat": "长文解释，保留事实引用和自然结尾",
                "xiaohongshu": "移动端卡片，先给结论路径再给行动",
                "douyin": "3秒问题钩子，口播与分镜分开",
            },
            "input_excerpt": "\n\n".join(row.text[:1000] for row in inputs if row.text)[:4000],
            "profile_version_id": profile_version.id,
            "memory_ids": [],
            "reference_to_original": "来源为用户提供的原始输入；保存链接或文件不代表完成事实核验。",
        }
        brief = Brief(
            id=str(uuid4()),
            task_id=task.id,
            version_no=next_no,
            payload_json=payload,
            confirmation_status="draft",
            created_at=datetime.now(timezone.utc),
        )
        session.add(brief)
        task.reader_problem = payload["reader_problem"]
        task.author_angle = payload["author_angle"]
        _set_status(session, task, "researching", "brief_research_started", {"brief_id": brief.id})
        _set_status(session, task, "briefed", "brief_created", {"brief_id": brief.id, "version_no": next_no})
        session.flush()
        return brief


def confirm_brief(session: Session, task_id: str, brief_id: str) -> Brief:
    with session.begin():
        task = _get_task(session, task_id)
        brief = session.get(Brief, brief_id)
        if brief is None or brief.task_id != task.id:
            raise BriefNotFound("内容简报不存在")
        latest = _current_brief(session, task.id)
        if latest is None or latest.id != brief.id:
            raise ContentConflict("只能确认当前最新的内容简报")
        if brief.confirmation_status == "confirmed":
            return brief
        brief.confirmation_status = "confirmed"
        if task.status not in {"briefed", "drafting", "adapted", "reviewing", "archived"}:
            raise InvalidContentState("当前任务还不能确认简报")
        task.updated_at = datetime.now(timezone.utc)
        _event(session, task, "brief_confirmed", task.status, task.status, {"brief_id": brief.id})
        return brief


def generate_artifacts(session: Session, task_id: str) -> List[PlatformArtifact]:
    with session.begin():
        task = _get_task(session, task_id)
        brief = _current_brief(session, task.id)
        if brief is None:
            raise BriefNotFound("请先生成内容简报")
        if brief.confirmation_status != "confirmed":
            raise InvalidContentState("请先确认内容简报，再生成三平台版本")
        if task.status == "archived":
            raise InvalidContentState("任务已归档，请先重新打开")
        existing = list(session.scalars(select(PlatformArtifact).where(PlatformArtifact.task_id == task.id)))
        if existing:
            raise ContentConflict("已有平台版本，请打开编辑，模板生成不会覆盖已有内容")
        profile_version = session.get(CreatorProfileVersion, task.profile_version_id)
        if profile_version is None:
            raise ContentConflict("任务绑定的画像版本不存在")
        confirmed_memories = list(session.scalars(select(Memory).where(
            Memory.confirmation_status == "confirmed", Memory.revoked_at.is_(None)
        ).order_by(Memory.created_at)))
        memories_by_platform: dict[str, list[dict[str, Any]]] = {platform: [] for platform in PLATFORMS}
        for memory in confirmed_memories:
            scope = memory.scope_json or {}
            scoped_platform = scope.get("platform")
            if scoped_platform in PLATFORMS:
                memories_by_platform[scoped_platform].append(_memory_read(memory) | {"id": memory.id})
            elif not scoped_platform or scoped_platform == "all":
                for platform in PLATFORMS:
                    memories_by_platform[platform].append(_memory_read(memory) | {"id": memory.id})
        generated = generate_content(
            title=task.title,
            input_text=brief.payload_json.get("input_excerpt", ""),
            profile=profile_version.snapshot_json,
            brief=brief.payload_json,
            memories=memories_by_platform["wechat"],
        )
        _set_status(session, task, "drafting", "draft_generation_started", {"adapter": "demo_deterministic"})
        now = datetime.now(timezone.utc)
        artifacts: List[PlatformArtifact] = []
        for platform in PLATFORMS:
            artifact = PlatformArtifact(
                id=str(uuid4()),
                task_id=task.id,
                platform=platform,
                status="generated",
                current_revision_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(artifact)
            session.flush()
            # Each platform gets the same deterministic input but only the
            # confirmed memories whose scope matches that platform.
            if platform != "wechat":
                generated[platform] = generate_content(
                    title=task.title,
                    input_text=brief.payload_json.get("input_excerpt", ""),
                    profile=profile_version.snapshot_json,
                    brief=brief.payload_json,
                    memories=memories_by_platform[platform],
                )[platform]
            revision = ArtifactRevision(
                id=str(uuid4()),
                artifact_id=artifact.id,
                revision_no=1,
                parent_revision_id=None,
                content_json=generated[platform],
                profile_version_id=profile_version.id,
                brief_id=brief.id,
                source_ids_json=brief.payload_json.get("input_ids", []),
                memory_ids_json=[item["id"] for item in memories_by_platform[platform]],
                generation_kind="demo_deterministic",
                created_at=now,
            )
            session.add(revision)
            session.flush()
            artifact.current_revision_id = revision.id
            artifacts.append(artifact)
        _set_status(session, task, "adapted", "platform_adapted", {"platforms": list(PLATFORMS)})
        return artifacts


def edit_artifact(session: Session, artifact_id: str, payload: ArtifactRevisionCreate) -> Tuple[PlatformArtifact, Memory]:
    with session.begin():
        artifact = session.get(PlatformArtifact, artifact_id)
        if artifact is None:
            raise ArtifactNotFound("平台产物不存在")
        current = session.get(ArtifactRevision, artifact.current_revision_id) if artifact.current_revision_id else None
        if current is None:
            raise ArtifactNotFound("平台产物没有当前版本")
        task = _get_task(session, artifact.task_id)
        if task.status == "archived":
            raise InvalidContentState("任务已归档，请先重新打开")
        if current.id != payload.base_revision_id:
            raise ContentConflict("产物已被其他页面修改，请先读取最新版本；你的编辑仍保留在表单中")
        changes: List[Dict[str, Any]] = []
        _diff_values(current.content_json, payload.content, "", changes)
        if not changes:
            raise ContentConflict("没有检测到用户修改")
        revision_no = int(
            session.scalar(
                select(ArtifactRevision.revision_no)
                .where(ArtifactRevision.artifact_id == artifact.id)
                .order_by(desc(ArtifactRevision.revision_no))
                .limit(1)
            )
            or 0
        ) + 1
        now = datetime.now(timezone.utc)
        revision = ArtifactRevision(
            id=str(uuid4()),
            artifact_id=artifact.id,
            revision_no=revision_no,
            parent_revision_id=current.id,
            content_json=payload.content,
            profile_version_id=current.profile_version_id,
            brief_id=current.brief_id,
            source_ids_json=current.source_ids_json,
            memory_ids_json=current.memory_ids_json,
            generation_kind="user_edit",
            created_at=now,
        )
        session.add(revision)
        session.flush()
        events: List[EditEvent] = []
        for change in changes:
            event = EditEvent(
                id=str(uuid4()),
                artifact_revision_id=revision.id,
                path=change["path"],
                before_json=change["before"],
                after_json=change["after"],
                reason=payload.reason,
                actor="user",
                created_at=now,
            )
            session.add(event)
            events.append(event)
        session.flush()
        statement = payload.reason.strip() or f"本次修改了 {artifact.platform} 的 {changes[0]['path']}；是否适合以后复用，需由用户判断。"
        memory = Memory(
            id=str(uuid4()),
            kind="edit_preference",
            statement=statement,
            source_event_id=events[0].id,
            confidence=0.6,
            scope_json={"platform": artifact.platform, "task_id": artifact.task_id, "field_paths": [item["path"] for item in changes]},
            confirmation_status="proposed",
            confirmed_at=None,
            revoked_at=None,
            created_at=now,
        )
        session.add(memory)
        changed = session.execute(update(PlatformArtifact).where(
            PlatformArtifact.id == artifact.id,
            PlatformArtifact.current_revision_id == payload.base_revision_id,
        ).values(current_revision_id=revision.id))
        if changed.rowcount != 1:
            raise ContentConflict("产物已更新，请读取最新版本后重试")
        artifact.current_revision_id = revision.id
        artifact.status = "edited"
        artifact.updated_at = now
        _set_status(session, task, "reviewing", "review_started", {})
        _event(session, task, "artifact_edited", task.status, task.status, {"artifact_id": artifact.id, "revision_id": revision.id, "memory_id": memory.id})
        task.updated_at = now
        session.flush()
        return artifact, memory


def list_memories(session: Session, task_id: Optional[str] = None) -> List[Memory]:
    query = select(Memory).order_by(desc(Memory.created_at))
    if task_id:
        query = (
            query.join(EditEvent, Memory.source_event_id == EditEvent.id)
            .join(ArtifactRevision, EditEvent.artifact_revision_id == ArtifactRevision.id)
            .join(PlatformArtifact, ArtifactRevision.artifact_id == PlatformArtifact.id)
            .where(PlatformArtifact.task_id == task_id)
        )
    return list(session.scalars(query))


def accept_memory(session: Session, memory_id: str) -> Memory:
    return decide_memory(session, memory_id, MemoryDecision(action="accept"))


def decide_memory(session: Session, memory_id: str, payload: MemoryDecision) -> Memory:
    with session.begin():
        memory = session.get(Memory, memory_id)
        if memory is None:
            raise MemoryNotFound("能力记忆不存在")
        allowed = {"accept": {"proposed"}, "reject": {"proposed"}, "revoke": {"confirmed"}, "edit": {"proposed"}}
        if memory.confirmation_status not in allowed[payload.action]:
            raise InvalidContentState("记忆状态已变化，请刷新；编辑只适用于待确认建议")
        before = {"status": memory.confirmation_status, "statement": memory.statement}
        now = datetime.now(timezone.utc)
        if payload.action == "edit":
            if not payload.statement:
                raise ContentConflict("请填写修改后的记忆")
            memory.statement = payload.statement
        else:
            memory.confirmation_status = {"accept": "confirmed", "reject": "rejected", "revoke": "revoked"}[payload.action]
            if payload.action == "accept":
                memory.confirmed_at = now
            if payload.action == "revoke":
                memory.revoked_at = now
        task = _get_task(session, memory.scope_json["task_id"])
        _event(session, task, "memory_" + payload.action, task.status, task.status, {
            "memory_id": memory.id, "before": before,
            "after": {"status": memory.confirmation_status, "statement": memory.statement},
        })
        return memory


def revise_brief(session: Session, task_id: str, payload: BriefRevisionCreate) -> Brief:
    with session.begin():
        task = _get_task(session, task_id)
        latest = _current_brief(session, task_id)
        if latest is None or latest.id != payload.base_brief_id:
            raise ContentConflict("简报已更新，请刷新后重试")
        if task.status not in {"idea", "researching", "briefed"}:
            raise InvalidContentState("已有产物的任务保留原简报；新选题请创建新任务")
        body = dict(latest.payload_json)
        body.update(payload.model_dump(exclude={"base_brief_id"}))
        body["evidence_status"] = "user_supplied_unverified"
        brief = Brief(id=str(uuid4()), task_id=task.id, version_no=latest.version_no + 1,
                      payload_json=body, confirmation_status="draft", created_at=datetime.now(timezone.utc))
        session.add(brief)
        task.reader_problem = payload.reader_problem
        task.author_angle = payload.author_angle
        task.updated_at = datetime.now(timezone.utc)
        _event(session, task, "brief_edited", task.status, task.status, {"brief_id": brief.id, "parent_brief_id": latest.id})
        return brief


def artifact_history(session: Session, artifact_id: str) -> List[Dict[str, Any]]:
    if session.get(PlatformArtifact, artifact_id) is None:
        raise ArtifactNotFound("平台产物不存在")
    result = []
    for row in session.scalars(select(ArtifactRevision).where(ArtifactRevision.artifact_id == artifact_id).order_by(desc(ArtifactRevision.revision_no))):
        record = _revision_read(row)
        record["edits"] = [{"id": e.id, "path": e.path, "before": e.before_json, "after": e.after_json, "reason": e.reason} for e in session.scalars(select(EditEvent).where(EditEvent.artifact_revision_id == row.id))]
        result.append(record)
    return result


def change_task_status(session: Session, task_id: str, status: str) -> ContentTask:
    with session.begin():
        task = _get_task(session, task_id)
        allowed = {"adapted": {"reviewing"}, "reviewing": {"archived"}, "archived": {"reviewing"}}
        if status not in allowed.get(task.status, set()):
            raise InvalidContentState("请先完成三平台草稿，再审阅和归档")
        _set_status(session, task, status, "task_status_changed", {})
        task.archived_at = datetime.now(timezone.utc) if status == "archived" else None
        return task
