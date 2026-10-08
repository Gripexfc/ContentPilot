from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import quote, unquote
from uuid import uuid4
from typing import Iterator, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from creatoros import __version__
from creatoros.config import Settings, load_settings
from creatoros.db.migrations import run_migrations
from creatoros.db.session import build_engine, session_dependency, session_factory
from creatoros.db.models import ConnectorState, ContentTask, Draft, Hotspot, Memory, MetricImport, TaskInput
from creatoros.domain.profile import (
    ProfileDiffRead,
    ProfileRead,
    ProfileVersionCreate,
    ProfileVersionRead,
    ProfileVersionSummary,
)
from creatoros.domain.content import (
    BriefRevisionCreate, MemoryDecision, TaskStatusUpdate,
    ArtifactRead,
    ArtifactRevisionCreate,
    BriefRead,
    ContentTaskCreate,
    QuickDraftCreate,
    QuickDraftRead,
    ContentTaskDetail,
    ContentTaskRead,
    GenerationResult,
    MemoryRead,
)
from creatoros.domain.ops import HotspotCreate, HotspotRead, MetricImportCreate, MetricImportRead, MetricSummary, MetricInclusion, OverviewRead
from creatoros.domain.ops import TrendsRead
from creatoros.services.trend_service import TREND_SOURCES, TrendService
from creatoros.domain.connectors import ConnectorAction, ConnectorRead
from creatoros.domain.drafts import DraftCreate, DraftDetail, DraftFromArtifact, DraftRead, DraftSubmit, DraftUpdate
from creatoros.services.content_service import (
    revise_brief, artifact_history, decide_memory, change_task_status,
    ArtifactNotFound,
    BriefNotFound,
    ContentConflict,
    ContentTaskNotFound,
    InvalidContentState,
    MemoryNotFound,
    accept_memory,
    confirm_brief,
    create_brief,
    create_task,
    edit_artifact,
    generate_artifacts,
    get_task_detail,
    list_memories,
    list_tasks,
    list_quick_drafts,
    save_quick_draft,
    QuickDraftProfileRequired,
    _artifact_read, _get_task, append_task_input, export_artifact,
    _brief_read,
    _memory_read,
    _task_read,
)
from creatoros.services.profile_service import (
    ProfileConflict,
    ProfileNotFound,
    ProfileVersionNotFound,
    create_version,
    diff_versions,
    get_profile,
    list_versions,
    restore_version,
    _version_read,
)
from creatoros.services.ops_service import MetricImportNotFound, _hotspot_read, _metric_read, create_hotspot, import_metrics, list_hotspots, list_metric_imports, metric_performance_insights, metric_summary, set_import_inclusion
from creatoros.services.connector_service import ConnectorError, ConnectorNotFound, configure, connect, list_connectors, read_account, submit_draft
from creatoros.adapters.wechat import WeChatAdapterError, WeChatBrowserAdapter
from creatoros.services.draft_service import DraftCoverMissing, DraftError, DraftNotFound, _read as draft_read, cover_path, copy_draft, create_draft, create_draft_from_artifact, detail as draft_detail, list_drafts, set_cover, submit_draft as submit_wechat_draft, update_draft


class ContentPilotDraftCreate(BaseModel):
    """Payload accepted by the original ContentPilot API.

    CreatorOS keeps its richer draft model, but this compatibility surface
    must accept the exact fields sent by the ContentPilot workbench, including
    a user-selected cover path.
    """

    title: str = Field(min_length=1, max_length=64)
    digest: str = Field(default="", max_length=120)
    author: str = Field(default="", max_length=32)
    content_html: str = ""
    cover_path: str = ""


class ContentPilotDraftRead(BaseModel):
    """The response shape used by ContentPilot's single-page editor."""

    id: str
    title: str
    digest: str = ""
    author: str = ""
    content_html: str = ""
    cover_path: str = ""
    status: Literal["writing", "ready", "submitted", "failed"] = "writing"
    created_at: str
    updated_at: str
    submitted_at: str = ""
    publish_error: str = ""
    # Keep the richer CreatorOS fields on this shared route for existing API
    # clients.  ContentPilot simply ignores fields it does not use.
    cover_url: Optional[str] = None
    remote_id: Optional[str] = None
    submission_receipt: Optional[dict[str, object]] = None
    source_task_id: Optional[str] = None
    source_artifact_id: Optional[str] = None
    source_revision_id: Optional[str] = None


def _contentpilot_draft(value: dict[str, object]) -> dict[str, object]:
    """Normalize CreatorOS nullable draft fields to ContentPilot defaults."""

    normalized = dict(value)
    for key in ("cover_path", "submitted_at", "publish_error"):
        if not normalized.get(key):
            normalized[key] = ""
    return normalized


def create_app(settings: Optional[Settings] = None, initialize: bool = True) -> FastAPI:
    resolved = settings or load_settings()
    engine = build_engine(resolved)
    factory = session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        resolved.ensure_dirs()
        if initialize:
            run_migrations(resolved)
        yield
        engine.dispose()

    app = FastAPI(title="CreatorOS API", version=__version__, lifespan=lifespan)
    app.state.settings = resolved
    app.state.engine = engine
    app.state.trend_service = TrendService()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.frontend_origin, "http://localhost:5173"],
        # Vite moves to the next loopback port when 5173 is occupied. Keep
        # direct local API access working for those fallback ports as well.
        allow_origin_regex=r"^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?$",
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Filename"],
    )

    def db() -> Iterator[Session]:
        yield from session_dependency(factory)

    @app.exception_handler(ProfileNotFound)
    async def profile_not_found(_request: Request, exc: ProfileNotFound):
        return JSONResponse(status_code=404, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(ProfileVersionNotFound)
    async def profile_version_not_found(_request: Request, exc: ProfileVersionNotFound):
        return JSONResponse(status_code=404, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(ProfileConflict)
    async def profile_conflict(_request: Request, exc: ProfileConflict):
        return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(ContentTaskNotFound)
    @app.exception_handler(BriefNotFound)
    @app.exception_handler(ArtifactNotFound)
    @app.exception_handler(MemoryNotFound)
    async def content_not_found(_request: Request, exc: Exception):
        code = getattr(exc, "code", "content_not_found")
        return JSONResponse(status_code=404, content={"detail": {"code": code, "message": str(exc)}})

    @app.exception_handler(ContentConflict)
    @app.exception_handler(InvalidContentState)
    @app.exception_handler(QuickDraftProfileRequired)
    async def content_conflict(_request: Request, exc: Exception):
        code = getattr(exc, "code", "content_conflict")
        return JSONResponse(status_code=409, content={"detail": {"code": code, "message": str(exc)}})

    @app.exception_handler(MetricImportNotFound)
    async def metric_import_not_found(_request: Request, exc: MetricImportNotFound):
        return JSONResponse(status_code=404, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(ConnectorNotFound)
    async def connector_not_found(_request: Request, exc: ConnectorNotFound):
        return JSONResponse(status_code=404, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(ConnectorError)
    async def connector_error(_request: Request, exc: ConnectorError):
        return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(DraftNotFound)
    @app.exception_handler(DraftCoverMissing)
    async def draft_missing(_request: Request, exc: Exception):
        code = getattr(exc, "code", "draft_error")
        return JSONResponse(status_code=404, content={"detail": {"code": code, "message": str(exc)}})

    @app.exception_handler(DraftError)
    async def draft_error(_request: Request, exc: DraftError):
        return JSONResponse(status_code=409, content={"detail": {"code": exc.code, "message": str(exc)}})

    @app.get("/", include_in_schema=False)
    def root():
        frontend = resolved.project_root / "web" / "frontend" / "dist" / "index.html"
        if frontend.is_file():
            return FileResponse(frontend)
        return {"name": "CreatorOS", "message": "前端尚未构建，请运行 web/frontend/npm run build"}

    frontend_assets = resolved.project_root / "web" / "frontend" / "dist" / "assets"
    if frontend_assets.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_assets), name="frontend-assets")
    frontend_brand = resolved.project_root / "web" / "frontend" / "dist" / "brand"
    if frontend_brand.is_dir():
        app.mount("/brand", StaticFiles(directory=frontend_brand), name="frontend-brand")

    @app.get("/api/v1/status")
    def status() -> dict[str, object]:
        return {
            "name": "CreatorOS",
            "version": __version__,
            "scope": "local-first",
            "data_dir": str(resolved.data_dir),
            "initialized": resolved.database_path.exists(),
        }

    @app.get("/api/v1/overview", response_model=OverviewRead)
    def overview(session: Session = Depends(db)) -> dict[str, object]:
        active_tasks = session.scalar(select(func.count()).select_from(ContentTask).where(ContentTask.status != "archived")) or 0
        task_count = session.scalar(select(func.count()).select_from(ContentTask)) or 0
        pending_memories = session.scalar(select(func.count()).select_from(Memory).where(Memory.confirmation_status == "proposed")) or 0
        pending_sources = session.scalar(
            select(func.count()).select_from(Hotspot).where(
                (Hotspot.needs_human_review.is_(True)) | (Hotspot.fact_status != "verified")
            )
        ) or 0
        draft_count = session.scalar(select(func.count()).select_from(Draft)) or 0
        pending_drafts = session.scalar(select(func.count()).select_from(Draft).where(Draft.status != "submitted")) or 0
        metric_import_count = session.scalar(select(func.count()).select_from(MetricImport)) or 0
        latest_import = session.scalar(select(MetricImport.imported_at).order_by(desc(MetricImport.imported_at)).limit(1))
        from datetime import datetime, timezone
        return {
            "active_task_count": int(active_tasks), "task_count": int(task_count),
            "pending_memory_count": int(pending_memories), "pending_source_count": int(pending_sources),
            "draft_count": int(draft_count), "pending_draft_count": int(pending_drafts),
            "metric_import_count": int(metric_import_count),
            "last_metric_imported_at": latest_import.isoformat() if latest_import else None,
            "read_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/v1/connectors", response_model=list[ConnectorRead])
    def connectors(session: Session = Depends(db)) -> list[dict[str, object]]:
        return list_connectors(session, resolved)

    @app.post("/api/v1/connectors/{connector_key}/configure", response_model=ConnectorRead)
    def configure_connector(connector_key: str, session: Session = Depends(db)) -> dict[str, object]:
        return configure(session, connector_key, resolved)

    @app.post("/api/v1/connectors/{connector_key}/connect", response_model=ConnectorRead)
    def connect_connector(connector_key: str, session: Session = Depends(db)) -> dict[str, object]:
        return connect(session, connector_key, resolved)

    @app.post("/api/v1/connectors/{connector_key}/read", response_model=ConnectorRead)
    def read_connector(connector_key: str, session: Session = Depends(db)) -> dict[str, object]:
        return read_account(session, connector_key, resolved)

    @app.post("/api/v1/connectors/{connector_key}/submit", response_model=ConnectorRead)
    def submit_connector(connector_key: str, payload: ConnectorAction, session: Session = Depends(db)) -> dict[str, object]:
        return submit_draft(session, connector_key, payload.simulate_failure, resolved)

    @app.get("/api/v1/analytics/wechat")
    def wechat_analytics(session: Session = Depends(db)) -> dict[str, object]:
        """Read account data only through the opt-in real browser adapter."""
        list_connectors(session, resolved)
        connector = session.scalar(select(ConnectorState).where(ConnectorState.connector_key == "wechat-oa"))
        if connector is None or connector.adapter_kind != "browser":
            raise ConnectorError("真实公众号数据读取未启用；当前可使用 CSV/JSON 主动导入")
        try:
            return WeChatBrowserAdapter(resolved).fetch_stats()
        except WeChatAdapterError as exc:
            raise ConnectorError(str(exc)) from exc

    # ContentPilot compatibility surface.  These routes deliberately use the
    # real browser adapter directly, so the single-page ContentPilot workbench
    # never turns the local mock connector into a false account or publish
    # success.  CreatorOS's existing connector routes remain available for its
    # own API clients and regression tests.
    @app.get("/api/v1/account")
    def contentpilot_account() -> dict[str, object]:
        try:
            account = WeChatBrowserAdapter(resolved).whoami()
            return {
                "platform": "wechat-oa",
                "name": "微信公众号",
                "logged_in": bool(account.get("logged_in")),
                "nickname": "",
                "message": str(account.get("message") or "尚未连接公众号"),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except WeChatAdapterError as exc:
            return {
                "platform": "wechat-oa",
                "name": "微信公众号",
                "logged_in": False,
                "nickname": "",
                "message": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    @app.post("/api/v1/account/login")
    def contentpilot_account_login() -> dict[str, str]:
        try:
            return WeChatBrowserAdapter(resolved).start_or_check_login()
        except WeChatAdapterError as exc:
            return {"state": "error", "message": str(exc)}

    @app.get("/api/v1/account/login/status")
    def contentpilot_account_login_status() -> dict[str, str]:
        try:
            return WeChatBrowserAdapter(resolved)._read_status()
        except WeChatAdapterError as exc:
            return {"state": "error", "message": str(exc)}

    @app.get("/api/v1/drafts", response_model=list[ContentPilotDraftRead])
    def drafts(session: Session = Depends(db)) -> list[dict[str, object]]:
        return [_contentpilot_draft(item) for item in list_drafts(session, resolved)]

    @app.post("/api/v1/drafts", response_model=ContentPilotDraftRead, status_code=201)
    def draft_create(payload: ContentPilotDraftCreate, session: Session = Depends(db)) -> dict[str, object]:
        created = create_draft(
            session,
            resolved,
            DraftCreate(
                title=payload.title,
                digest=payload.digest,
                author=payload.author,
                content_html=payload.content_html,
            ),
        )
        # ContentPilot stores the path supplied by its editor.  Keep the same
        # value for display and let the real adapter validate it at publish
        # time; CreatorOS's upload endpoint remains the safe local alternative.
        if payload.cover_path:
            item = session.get(Draft, created["id"])
            if item is not None:
                item.cover_path = payload.cover_path
                item.updated_at = datetime.now(timezone.utc)
                session.commit()
                return _contentpilot_draft(draft_read(item, resolved))
        return _contentpilot_draft(created)

    @app.post("/api/v1/drafts/{draft_id}/publish")
    def contentpilot_publish(draft_id: str, session: Session = Depends(db)) -> dict[str, object]:
        item = session.get(Draft, draft_id)
        if item is None:
            raise DraftNotFound("文章草稿不存在")
        if item.status == "submitted":
            return {"success": True, "media_id": item.remote_id or ""}
        if not item.cover_path:
            item.status = "failed"
            item.publish_error = "提交公众号草稿前需要有效的封面文件"
            item.updated_at = datetime.now(timezone.utc)
            session.commit()
            raise DraftCoverMissing(item.publish_error)
        candidate = Path(item.cover_path).expanduser()
        if not candidate.is_absolute():
            candidate = (resolved.asset_dir / candidate).resolve()
        try:
            receipt = WeChatBrowserAdapter(resolved).publish_draft(
                item.content_html,
                candidate,
                item.title,
                item.digest,
                item.author,
            )
        except WeChatAdapterError as exc:
            item.status = "failed"
            item.publish_error = str(exc)
            item.updated_at = datetime.now(timezone.utc)
            session.commit()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        item.status = "submitted"
        item.submitted_at = datetime.now(timezone.utc)
        item.remote_id = str(receipt.get("remote_id") or receipt.get("media_id") or "") or None
        item.submission_receipt_json = receipt
        item.publish_error = None
        item.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"success": True, "media_id": item.remote_id or ""}

    @app.get("/api/v1/analytics")
    def contentpilot_analytics() -> dict[str, object]:
        try:
            return WeChatBrowserAdapter(resolved).fetch_stats()
        except WeChatAdapterError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/artifacts/{artifact_id}/draft", response_model=DraftRead, status_code=201)
    def artifact_draft(artifact_id: str, payload: DraftFromArtifact, session: Session = Depends(db)) -> dict[str, object]:
        return create_draft_from_artifact(session, resolved, artifact_id, payload.revision_id)

    @app.get("/api/v1/drafts/{draft_id}", response_model=DraftDetail)
    def draft_get(draft_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return draft_detail(session, resolved, draft_id)

    @app.patch("/api/v1/drafts/{draft_id}", response_model=DraftRead)
    def draft_update(draft_id: str, payload: DraftUpdate, session: Session = Depends(db)) -> dict[str, object]:
        return update_draft(session, resolved, draft_id, payload)

    @app.post("/api/v1/drafts/{draft_id}/copy", response_model=DraftRead, status_code=201)
    def draft_copy(draft_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return copy_draft(session, resolved, draft_id)

    @app.post("/api/v1/drafts/{draft_id}/cover", response_model=DraftRead, status_code=201)
    async def draft_cover(draft_id: str, request: Request, session: Session = Depends(db)) -> dict[str, object]:
        body = await request.body()
        return set_cover(session, resolved, draft_id, resolved.asset_dir, unquote(request.headers.get("x-filename", "cover")), body)

    @app.get("/api/v1/drafts/{draft_id}/cover")
    def draft_cover_get(draft_id: str, session: Session = Depends(db)):
        target = cover_path(session, resolved, draft_id)
        return FileResponse(target)

    @app.post("/api/v1/drafts/{draft_id}/submit", response_model=DraftRead)
    def draft_submit(draft_id: str, payload: DraftSubmit, session: Session = Depends(db)) -> dict[str, object]:
        return submit_wechat_draft(session, resolved, draft_id, failed=payload.simulate_failure)

    @app.get("/api/v1/profile", response_model=ProfileRead)
    def profile(session: Session = Depends(db)) -> dict[str, object]:
        current_profile, current_version = get_profile(session)
        return {
            "id": current_profile.id,
            "current_version_id": current_version.id,
            "current_version": _version_read(current_version),
        }

    @app.get("/api/v1/profile/versions", response_model=list[ProfileVersionSummary])
    def profile_versions(session: Session = Depends(db)) -> list[dict[str, object]]:
        return [
            {
                "id": item.id,
                "version_no": item.version_no,
                "parent_version_id": item.parent_version_id,
                "change_summary": item.change_summary,
                "confirmation_status": item.confirmation_status,
                "created_at": item.created_at.isoformat(),
            }
            for item in list_versions(session)
        ]

    @app.get("/api/v1/profile/versions/{version_id}/diff/{other_id}", response_model=ProfileDiffRead)
    def profile_diff(version_id: str, other_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return {
            "left_version_id": version_id,
            "right_version_id": other_id,
            "changes": diff_versions(session, version_id, other_id),
        }

    @app.get("/api/v1/profile/versions/{version_id}", response_model=ProfileVersionRead)
    def profile_version(version_id: str, session: Session = Depends(db)) -> dict[str, object]:
        versions = {item.id: item for item in list_versions(session)}
        item = versions.get(version_id)
        if item is None:
            raise ProfileVersionNotFound("个人画像版本不存在")
        return _version_read(item)

    @app.post("/api/v1/profile/versions", response_model=ProfileVersionRead, status_code=201)
    def create_profile_version(payload: ProfileVersionCreate, session: Session = Depends(db)) -> dict[str, object]:
        return _version_read(create_version(session, payload))

    @app.post("/api/v1/profile/restore/{version_id}", response_model=ProfileVersionRead, status_code=201)
    def restore_profile_version(version_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return _version_read(restore_version(session, version_id))

    @app.post("/api/v1/tasks", response_model=ContentTaskRead, status_code=201)
    def create_content_task(payload: ContentTaskCreate, session: Session = Depends(db)) -> dict[str, object]:
        return _task_read(create_task(session, payload))

    @app.get("/api/v1/tasks", response_model=list[ContentTaskRead])
    def content_tasks(session: Session = Depends(db)) -> list[dict[str, object]]:
        return [_task_read(item) for item in list_tasks(session)]

    @app.post("/api/v1/quick-drafts", response_model=QuickDraftRead, status_code=201)
    def save_quick_draft_route(payload: QuickDraftCreate, session: Session = Depends(db)) -> dict[str, object]:
        return save_quick_draft(session, payload)

    @app.get("/api/v1/quick-drafts", response_model=list[QuickDraftRead])
    def quick_drafts(session: Session = Depends(db)) -> list[dict[str, object]]:
        return list_quick_drafts(session)

    @app.get("/api/v1/tasks/{task_id}", response_model=ContentTaskDetail)
    def content_task(task_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return get_task_detail(session, task_id)

    @app.post("/api/v1/tasks/{task_id}/inputs/file", status_code=201)
    async def upload_task_input(task_id: str, request: Request, session: Session = Depends(db)) -> dict[str, object]:
        """Save a user-selected file in the local asset directory.

        Raw request bytes are used deliberately so the basic install does not
        need a multipart parser. The UI sends the original name in a header;
        it is metadata only and never used as a path.
        """
        task = _get_task(session, task_id)
        if task.status == "archived":
            raise InvalidContentState("任务已归档，请先重新打开")
        stored_task_id = task.id
        session.rollback()
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 25 * 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": {"code": "asset_too_large", "message": "单个文件不能超过 25 MB"}})
            body.extend(chunk)
        if not body:
            return JSONResponse(status_code=400, content={"detail": {"code": "empty_asset", "message": "文件为空"}})
        if len(body) > 25 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": {"code": "asset_too_large", "message": "单个文件不能超过 25 MB"}})
        original = unquote(request.headers.get("x-filename", "asset"))[:300]
        safe = re.sub(r"[^\w.\-一-龥 ]", "_", Path(original).name).strip() or "asset"
        relative = Path("tasks") / stored_task_id / f"{uuid4().hex[:12]}-{safe}"
        task_dir = request.app.state.settings.asset_dir / relative.parent
        task_dir.mkdir(parents=True, exist_ok=True)
        target = request.app.state.settings.asset_dir / relative
        try:
            target.write_bytes(body)
            text = ""
            if Path(safe).suffix.lower() in {".md", ".markdown", ".txt"}:
                try:
                    text = body.decode("utf-8-sig")[:10000]
                except UnicodeDecodeError:
                    pass
            input_row = append_task_input(session, task_id, "file", text, {
                "path": str(relative), "original_name": original,
                "mime_type": request.headers.get("content-type", "application/octet-stream"),
                "size_bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "extraction": "text_excerpt" if text else "stored_only",
            })
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {"id": input_row.id, "input_type": input_row.input_type, "metadata": input_row.metadata_json,
                "parse_status": input_row.parse_status, "created_at": input_row.created_at.isoformat()}

    @app.get("/api/v1/inputs/{input_id}/download")
    def download_input(input_id: str, session: Session = Depends(db)):
        row = session.get(TaskInput, input_id)
        if row is None or row.input_type != "file":
            raise ContentTaskNotFound("文件输入不存在")
        root = resolved.asset_dir.resolve()
        target = (root / row.metadata_json.get("path", "")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ContentTaskNotFound("本地文件缺失，请重新上传")
        return FileResponse(target, filename=row.metadata_json.get("original_name", "asset"), media_type="application/octet-stream")

    @app.post("/api/v1/tasks/{task_id}/briefs", response_model=BriefRead, status_code=201)
    def content_brief(task_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return _brief_read(create_brief(session, task_id))

    @app.post("/api/v1/tasks/{task_id}/briefs/{brief_id}/confirm", response_model=BriefRead)
    def confirm_content_brief(task_id: str, brief_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return _brief_read(confirm_brief(session, task_id, brief_id))

    @app.post("/api/v1/tasks/{task_id}/generate", response_model=GenerationResult, status_code=201)
    def generate_content_artifacts(task_id: str, session: Session = Depends(db)) -> dict[str, object]:
        artifacts = generate_artifacts(session, task_id)
        detail = get_task_detail(session, task_id)
        return {"task": detail["task"], "artifacts": [_artifact_read(session, item) for item in artifacts]}

    @app.post("/api/v1/artifacts/{artifact_id}/revisions", response_model=ArtifactRead, status_code=201)
    def create_artifact_revision(
        artifact_id: str, payload: ArtifactRevisionCreate, session: Session = Depends(db)
    ) -> dict[str, object]:
        artifact, _memory = edit_artifact(session, artifact_id, payload)
        return _artifact_read(session, artifact)

    @app.get("/api/v1/memories", response_model=list[MemoryRead])
    def memories(task_id: Optional[str] = None, session: Session = Depends(db)) -> list[dict[str, object]]:
        return [_memory_read(item) for item in list_memories(session, task_id)]

    @app.post("/api/v1/memories/{memory_id}/accept", response_model=MemoryRead)
    def accept_content_memory(memory_id: str, session: Session = Depends(db)) -> dict[str, object]:
        return _memory_read(accept_memory(session, memory_id))

    @app.post("/api/v1/tasks/{task_id}/brief-revisions", response_model=BriefRead, status_code=201)
    def edit_content_brief(task_id: str, payload: BriefRevisionCreate, session: Session = Depends(db)):
        return _brief_read(revise_brief(session, task_id, payload))

    @app.get("/api/v1/artifacts/{artifact_id}/revisions")
    def content_history(artifact_id: str, session: Session = Depends(db)):
        return artifact_history(session, artifact_id)

    @app.get("/api/v1/artifacts/{artifact_id}/export")
    def artifact_export(artifact_id: str, format: str = "markdown", session: Session = Depends(db)) -> Response:
        if format not in {"markdown", "json", "html"}:
            return JSONResponse(status_code=400, content={"detail": {"code": "unsupported_export", "message": "仅支持 markdown、json、html"}})
        body, suffix, title = export_artifact(session, artifact_id, format)
        media = {"markdown": "text/markdown; charset=utf-8", "json": "application/json; charset=utf-8", "html": "text/html; charset=utf-8"}[suffix]
        filename = re.sub(r"[^\w.\-一-龥 ]", "_", title).strip() or "creatoros-export"
        extension = suffix if suffix != "markdown" else "md"
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "creatoros-export"
        disposition = f'attachment; filename="{ascii_name}.{extension}"; filename*=UTF-8\'\'{quote(filename)}.{extension}'
        return Response(content=body, media_type=media, headers={"Content-Disposition": disposition})

    @app.post("/api/v1/memories/{memory_id}/decisions", response_model=MemoryRead)
    def memory_decision(memory_id: str, payload: MemoryDecision, session: Session = Depends(db)):
        return _memory_read(decide_memory(session, memory_id, payload))

    @app.post("/api/v1/tasks/{task_id}/status", response_model=ContentTaskRead)
    def task_state(task_id: str, payload: TaskStatusUpdate, session: Session = Depends(db)):
        return _task_read(change_task_status(session, task_id, payload.status))

    @app.get("/api/v1/trends", response_model=TrendsRead)
    def trends(
        platforms: str = Query(default="douyin,weibo,zhihu", max_length=100),
        limit: int = Query(default=12, ge=1, le=30),
        refresh: bool = False,
    ):
        selected = list(dict.fromkeys(platform.strip() for platform in platforms.split(",")))
        if not selected or any(platform not in TREND_SOURCES for platform in selected):
            raise HTTPException(status_code=422, detail="热榜来源仅支持：" + ", ".join(TREND_SOURCES))
        return app.state.trend_service.get_trends(selected, limit=limit, refresh=refresh)

    @app.post("/api/v1/hotspots", response_model=HotspotRead, status_code=201)
    def add_hotspot(payload: HotspotCreate, session: Session = Depends(db)) -> dict[str, object]:
        item = create_hotspot(session, payload)
        return _hotspot_read(session, item)

    @app.get("/api/v1/hotspots", response_model=list[HotspotRead])
    def hotspots(session: Session = Depends(db)) -> list[dict[str, object]]:
        return list_hotspots(session)

    @app.post("/api/v1/hotspots/{hotspot_id}/task", response_model=ContentTaskRead, status_code=201)
    def task_from_hotspot(hotspot_id: str, session: Session = Depends(db)) -> dict[str, object]:
        item = session.get(Hotspot, hotspot_id)
        if item is None:
            return JSONResponse(status_code=404, content={"detail": {"code": "hotspot_not_found", "message": "热点线索不存在"}})
        payload = ContentTaskCreate(
            title=item.title[:200],
            input_text=f"原始链接：{item.canonical_url}\n\n来源摘要：{item.summary}",
            input_type="hotspot",
            input_metadata={"hotspot_id": item.id, "source_name": item.source_name, "canonical_url": item.canonical_url},
        )
        session.rollback()
        return _task_read(create_task(session, payload))

    @app.post("/api/v1/metrics/imports", response_model=MetricImportRead, status_code=201)
    def add_metric_import(payload: MetricImportCreate, session: Session = Depends(db)) -> dict[str, object]:
        return _metric_read(import_metrics(session, payload))

    @app.get("/api/v1/metrics/imports", response_model=list[MetricImportRead])
    def metric_imports(session: Session = Depends(db)) -> list[dict[str, object]]:
        return list_metric_imports(session)

    @app.get("/api/v1/metrics/summary", response_model=MetricSummary)
    def metrics_summary(session: Session = Depends(db)) -> dict[str, object]:
        return metric_summary(session)

    @app.get("/api/v1/metrics/insights")
    def metrics_insights(platform: Optional[str] = Query(default=None), session: Session = Depends(db)) -> dict[str, object]:
        if platform is not None and platform not in {"wechat", "xiaohongshu", "douyin"}:
            raise HTTPException(status_code=422, detail="不支持的平台")
        return metric_performance_insights(session, platform=platform)

    @app.post("/api/v1/metrics/imports/{import_id}/inclusion", response_model=MetricImportRead)
    def metric_inclusion(import_id: str, payload: MetricInclusion, session: Session = Depends(db)):
        return _metric_read(set_import_inclusion(session, import_id, payload.included))

    return app


# Preserve the original route closures and lifespan, including its database setup.
legacy_app = create_app()
from creatoros.api.easel_bridge import official_app
_old_lifespan = official_app.router.lifespan_context
@asynccontextmanager
async def combined_lifespan(app):
    async with legacy_app.router.lifespan_context(legacy_app):
        async with _old_lifespan(app):
            yield

official_app.router.lifespan_context = combined_lifespan
official_app.exception_handlers.update(legacy_app.exception_handlers)
official_app.router.routes[0:0] = [r for r in legacy_app.routes if getattr(r, 'path', '').startswith('/api/v1')]
# Keep the historical bookmark working, but point it at the CreatorOS-owned UI.
@official_app.get('/legacy.html', include_in_schema=False)
def legacy_page():
    return FileResponse(Path(__file__).resolve().parents[2] / 'web/frontend/dist/index.html')
app = official_app
