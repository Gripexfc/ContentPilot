from __future__ import annotations

from datetime import datetime, timezone
import html
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from creatoros.config import Settings
from creatoros.adapters.wechat import WeChatAdapterError, WeChatBrowserAdapter
from creatoros.db.models import ArtifactRevision, ConnectorState, Draft, DraftEvent, PlatformArtifact
from creatoros.domain.drafts import DraftCreate, DraftUpdate
from creatoros.services.connector_service import ConnectorError, submit_draft as submit_mock_connector
from creatoros.time_utils import utc_iso


class DraftError(RuntimeError):
    code = "draft_error"


class DraftNotFound(DraftError):
    code = "draft_not_found"


class DraftCoverMissing(DraftError):
    code = "draft_cover_missing"


class DraftSourceError(DraftError):
    code = "draft_source_error"


class DraftCoverInvalid(DraftError):
    code = "draft_cover_invalid"


MAX_COVER_BYTES = 10 * 1024 * 1024
ALLOWED_COVER_TYPES = {"png", "jpeg", "webp"}


def _image_kind(content: bytes) -> str | None:
    """Validate a real image header and return its supported type."""
    if content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24 and content[12:16] == b"IHDR":
        width = int.from_bytes(content[16:20], "big")
        height = int.from_bytes(content[20:24], "big")
        return "png" if width and height else None
    if content.startswith(b"\xff\xd8\xff"):
        # JPEG SOF markers carry dimensions; reject a truncated signature.
        index = 2
        while index + 9 < len(content):
            if content[index] != 0xFF:
                index += 1
                continue
            marker = content[index + 1]
            index += 2
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(content):
                break
            length = int.from_bytes(content[index:index + 2], "big")
            if length < 2 or index + length > len(content):
                break
            if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
                height = int.from_bytes(content[index + 3:index + 5], "big")
                width = int.from_bytes(content[index + 5:index + 7], "big")
                return "jpeg" if width and height else None
            index += length
        return None
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP" and len(content) >= 30:
        if content[12:16] == b"VP8X":
            width = 1 + int.from_bytes(content[24:27], "little")
            height = 1 + int.from_bytes(content[27:30], "little")
            return "webp" if width and height else None
        if content[12:16] in {b"VP8 ", b"VP8L"}:
            return "webp"
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_draft(session: Session, draft_id: str) -> Draft:
    item = session.get(Draft, draft_id)
    if item is None:
        raise DraftNotFound("公众号草稿不存在")
    return item


def _read(item: Draft, settings: Settings) -> dict[str, Any]:
    return {
        "id": item.id, "title": item.title, "digest": item.digest, "author": item.author,
        "content_html": item.content_html, "cover_path": item.cover_path,
        "cover_url": f"/api/v1/drafts/{item.id}/cover" if item.cover_path else None,
        "status": item.status, "submitted_at": utc_iso(item.submitted_at),
        "publish_error": item.publish_error, "created_at": utc_iso(item.created_at),
        "updated_at": utc_iso(item.updated_at),
        "remote_id": item.remote_id,
        "submission_receipt": item.submission_receipt_json or None,
        "source_task_id": item.source_task_id, "source_artifact_id": item.source_artifact_id,
        "source_revision_id": item.source_revision_id,
    }


def _event_read(item: DraftEvent) -> dict[str, Any]:
    return {"id": item.id, "operation": item.operation, "from_status": item.from_status,
            "to_status": item.to_status, "success": item.success, "error": item.error,
            "created_at": utc_iso(item.created_at)}


def _record(session: Session, item: Draft, operation: str, state: str, *, success: bool = True, error: Optional[str] = None) -> None:
    session.add(DraftEvent(id=str(uuid4()), draft_id=item.id, operation=operation,
                           from_status=item.status, to_status=state, success=success,
                           error=error, created_at=_now()))
    item.status = state
    item.updated_at = _now()
    item.publish_error = error


def list_drafts(session: Session, settings: Settings) -> list[dict[str, Any]]:
    return [_read(item, settings) for item in session.scalars(select(Draft).order_by(desc(Draft.updated_at))).all()]


def create_draft(session: Session, settings: Settings, payload: DraftCreate) -> dict[str, Any]:
    now = _now()
    item = Draft(id=str(uuid4()), title=payload.title, digest=payload.digest, author=payload.author,
                 content_html=payload.content_html, status="writing", created_at=now, updated_at=now)
    session.add(item)
    session.flush()
    session.add(DraftEvent(id=str(uuid4()), draft_id=item.id, operation="create", from_status=None,
                           to_status="writing", success=True, created_at=now))
    session.commit()
    return _read(item, settings)


def _wechat_html(content: dict[str, Any]) -> str:
    """Render only the saved structured revision into safe, simple HTML."""
    def text(value: Any) -> str:
        return html.escape(str(value or "")).replace("\n", "<br>")

    blocks = []
    for section in content.get("sections", []):
        if not isinstance(section, dict):
            continue
        heading = text(section.get("heading"))
        body = text(section.get("body"))
        if heading:
            blocks.append(f"<h2>{heading}</h2>")
        if body:
            blocks.append(f"<p>{body}</p>")
    if not blocks and content.get("body"):
        blocks.append(f"<p>{text(content.get('body'))}</p>")
    return "\n".join(blocks)


def create_draft_from_artifact(session: Session, settings: Settings, artifact_id: str, revision_id: str) -> dict[str, Any]:
    artifact = session.get(PlatformArtifact, artifact_id)
    revision = session.get(ArtifactRevision, revision_id)
    if artifact is None or revision is None or revision.artifact_id != artifact_id:
        raise DraftSourceError("公众号产物版本不存在")
    if artifact.platform != "wechat":
        raise DraftSourceError("只有公众号产物可以保存为公众号草稿")
    if artifact.current_revision_id != revision_id:
        raise DraftSourceError("只能从已保存的当前公众号版本创建草稿")
    existing = session.scalar(select(Draft).where(Draft.source_revision_id == revision_id))
    if existing is not None:
        return _read(existing, settings)
    content = revision.content_json or {}
    title = str(content.get("title") or (content.get("title_candidates") or ["未命名文章"])[0])[:64]
    digest = str(content.get("summary") or "")[:120]
    now = _now()
    item = Draft(id=str(uuid4()), title=title, digest=digest, author="", content_html=_wechat_html(content),
                 status="writing", source_task_id=artifact.task_id, source_artifact_id=artifact.id,
                 source_revision_id=revision.id, created_at=now, updated_at=now)
    session.add(item)
    session.flush()
    session.add(DraftEvent(id=str(uuid4()), draft_id=item.id, operation="create_from_artifact", from_status=None,
                           to_status="writing", success=True, created_at=now))
    session.commit()
    return _read(item, settings)


def copy_draft(session: Session, settings: Settings, draft_id: str) -> dict[str, Any]:
    source = get_draft(session, draft_id)
    now = _now()
    item = Draft(id=str(uuid4()), title=source.title, digest=source.digest, author=source.author,
                 content_html=source.content_html, cover_path=source.cover_path, status="writing",
                 source_task_id=source.source_task_id, source_artifact_id=source.source_artifact_id,
                 source_revision_id=source.source_revision_id, created_at=now, updated_at=now)
    session.add(item)
    session.flush()
    session.add(DraftEvent(id=str(uuid4()), draft_id=item.id, operation="copy", from_status=source.status,
                           to_status="writing", success=True, created_at=now))
    session.commit()
    return _read(item, settings)


def update_draft(session: Session, settings: Settings, draft_id: str, payload: DraftUpdate) -> dict[str, Any]:
    item = get_draft(session, draft_id)
    if item.status == "submitted":
        raise DraftError("已提交草稿不可直接覆盖，请复制为新草稿")
    item.title, item.digest, item.author, item.content_html = payload.title, payload.digest, payload.author, payload.content_html
    _record(session, item, "edit", "ready" if item.content_html.strip() else "writing")
    session.commit()
    return _read(item, settings)


def detail(session: Session, settings: Settings, draft_id: str) -> dict[str, Any]:
    item = get_draft(session, draft_id)
    events = session.scalars(select(DraftEvent).where(DraftEvent.draft_id == item.id).order_by(DraftEvent.created_at)).all()
    result = _read(item, settings)
    result["events"] = [_event_read(event) for event in events]
    return result


def set_cover(session: Session, settings: Settings, draft_id: str, settings_root: Path, filename: str, content: bytes) -> dict[str, Any]:
    item = get_draft(session, draft_id)
    if item.status == "submitted":
        raise DraftError("已提交草稿不可更换封面，请复制为新草稿")
    if not content:
        raise DraftCoverMissing("封面文件为空")
    if len(content) > MAX_COVER_BYTES:
        raise DraftCoverInvalid("封面不能超过 10 MB")
    kind = _image_kind(content)
    if kind not in ALLOWED_COVER_TYPES:
        raise DraftCoverInvalid("封面必须是可读取的 PNG、JPEG 或 WebP 图片")
    relative = Path("drafts") / item.id / f"cover-{uuid4().hex[:12]}-{Path(filename).name[:160]}"
    target = settings_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    item.cover_path = str(relative)
    item.updated_at = _now()
    session.add(DraftEvent(id=str(uuid4()), draft_id=item.id, operation="cover_upload", from_status=item.status,
                           to_status=item.status, success=True, created_at=item.updated_at))
    session.commit()
    return _read(item, settings)


def cover_path(session: Session, settings: Settings, draft_id: str) -> Path:
    item = get_draft(session, draft_id)
    if not item.cover_path:
        raise DraftCoverMissing("草稿还没有封面")
    root = settings.asset_dir.resolve()
    target = (root / item.cover_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise DraftCoverMissing("封面文件缺失，请重新上传")
    return target


def submit_draft(session: Session, settings: Settings, draft_id: str, *, failed: bool = False) -> dict[str, Any]:
    item = get_draft(session, draft_id)
    cover_path(session, settings, draft_id)
    if item.status == "submitted":
        return _read(item, settings)
    connector = session.scalar(select(ConnectorState).where(ConnectorState.connector_key == "wechat-oa"))
    if connector is None:
        # Ensure the local connector row exists before reporting a recoverable
        # configuration error.
        from creatoros.services.connector_service import _get
        connector = _get(session, "wechat-oa", settings)
    if connector.adapter_kind == "browser":
        if failed:
            _record(session, item, "submit", "failed", success=False, error="模拟提交失败，可重试")
            session.commit()
            return _read(item, settings)
        if connector.state not in {"read_succeeded", "submit_succeeded"}:
            error = ConnectorError("请先在设置与连接器中完成真实登录并读取账号")
            _record(session, item, "submit", "failed", success=False, error=str(error))
            session.commit()
            raise error
        if item.status == "submitted" and item.remote_id:
            return _read(item, settings)
        try:
            receipt = WeChatBrowserAdapter(settings).publish_draft(
                item.content_html, cover_path(session, settings, draft_id), item.title, item.digest, item.author
            )
        except WeChatAdapterError as exc:
            _record(session, item, "submit", "failed", success=False, error=str(exc))
            session.commit()
            raise ConnectorError(str(exc)) from exc
        now = _now()
        item.remote_id = receipt.get("remote_id") or None
        item.submission_receipt_json = receipt
        _record(session, item, "submit", "submitted")
        item.submitted_at = now
        session.commit()
        return _read(item, settings)
    try:
        submit_mock_connector(session, "wechat-oa", simulate_failure=failed, settings=settings)
    except ConnectorError as exc:
        _record(session, item, "submit", "failed", success=False, error=str(exc))
        session.commit()
        raise
    if failed:
        _record(session, item, "submit", "failed", success=False, error="Mock Connector 模拟提交失败，可重试")
    else:
        now = _now()
        _record(session, item, "submit", "submitted")
        item.submitted_at = now
    session.commit()
    return _read(item, settings)
