from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from creatoros.db.models import ConnectorEvent, ConnectorState
from creatoros.time_utils import utc_iso
from creatoros.adapters.wechat import WeChatBrowserAdapter, WeChatAdapterError
from creatoros.config import Settings


DEFAULT_CONNECTORS = (
    ("wechat-oa", "wechat", "微信公众号"),
    ("xiaohongshu", "xiaohongshu", "小红书"),
    ("douyin", "douyin", "抖音"),
)


class ConnectorError(RuntimeError):
    code = "connector_error"


class ConnectorNotFound(ConnectorError):
    code = "connector_not_found"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read(item: ConnectorState) -> dict[str, Any]:
    return {
        "id": item.id,
        "connector_key": item.connector_key,
        "platform": item.platform,
        "label": item.label,
        "adapter_kind": item.adapter_kind,
        "state": item.state,
        "last_operation": item.last_operation,
        "last_error_code": item.last_error_code,
        "last_error": item.last_error,
        "updated_at": utc_iso(item.updated_at),
    }


def _ensure_defaults(session: Session, settings: Settings | None = None) -> list[ConnectorState]:
    existing = {item.connector_key: item for item in session.scalars(select(ConnectorState)).all()}
    changed = False
    for key, platform, label in DEFAULT_CONNECTORS:
        if key not in existing:
            adapter_kind = "browser" if key == "wechat-oa" and settings and settings.wechat_adapter == "browser" else "mock"
            item = ConnectorState(id=str(uuid4()), connector_key=key, platform=platform, label=label,
                                  adapter_kind=adapter_kind, state="not_configured", updated_at=_now())
            session.add(item)
            existing[key] = item
            changed = True
        elif settings and key == "wechat-oa":
            desired = "browser" if settings.wechat_adapter == "browser" else "mock"
            item = existing[key]
            if item.adapter_kind != desired:
                item.adapter_kind = desired
                item.state = "not_configured"
                item.last_operation = None
                item.last_error_code = None
                item.last_error = None
                item.updated_at = _now()
                changed = True
    if changed:
        session.commit()
    return list(existing.values())


def list_connectors(session: Session, settings: Settings | None = None) -> list[dict[str, Any]]:
    return [_read(item) for item in sorted(_ensure_defaults(session, settings), key=lambda row: row.connector_key)]


def _get(session: Session, connector_key: str, settings: Settings | None = None) -> ConnectorState:
    _ensure_defaults(session, settings)
    item = session.scalar(select(ConnectorState).where(ConnectorState.connector_key == connector_key))
    if item is None:
        raise ConnectorNotFound("连接器不存在")
    return item


def _transition(session: Session, item: ConnectorState, operation: str, state: str,
                *, success: bool = True, error_code: str | None = None, error: str | None = None) -> ConnectorState:
    before = item.state
    item.state = state
    item.last_operation = operation
    item.last_error_code = error_code
    item.last_error = error
    item.updated_at = _now()
    session.add(ConnectorEvent(id=str(uuid4()), connector_key=item.connector_key, operation=operation,
                               from_state=before, to_state=state, success=success,
                               error_code=error_code, created_at=item.updated_at))
    session.commit()
    return item


def configure(session: Session, connector_key: str, settings: Settings | None = None) -> dict[str, Any]:
    item = _get(session, connector_key, settings)
    if item.adapter_kind == "browser":
        try:
            WeChatBrowserAdapter(settings).preflight()
        except WeChatAdapterError as exc:
            return _read(_transition(session, item, "configure", "unsupported", success=False,
                                     error_code=exc.code, error=str(exc)))
    return _read(_transition(session, item, "configure", "configured"))


def connect(session: Session, connector_key: str, settings: Settings | None = None) -> dict[str, Any]:
    item = _get(session, connector_key, settings)
    if item.state == "not_configured":
        raise ConnectorError("连接器尚未配置")
    if item.adapter_kind == "browser":
        try:
            result = WeChatBrowserAdapter(settings).start_or_check_login()
        except WeChatAdapterError as exc:
            return _read(_transition(session, item, "connect", "unsupported", success=False,
                                     error_code=exc.code, error=str(exc)))
        state = result.get("state")
        if state == "success":
            return _read(_transition(session, item, "connect", "connected"))
        if state == "expired":
            return _read(_transition(session, item, "connect", "expired", success=False,
                                     error_code="wechat_login_expired", error=result.get("message")))
        if state == "error":
            return _read(_transition(session, item, "connect", "failed", success=False,
                                     error_code="wechat_login_failed", error=result.get("message")))
        return _read(_transition(session, item, "connect", "connecting", success=False,
                                 error_code="wechat_login_pending", error=result.get("message")))
    _transition(session, item, "connect", "connecting")
    return _read(_transition(session, item, "connect", "connected"))


def read_account(session: Session, connector_key: str, settings: Settings | None = None) -> dict[str, Any]:
    item = _get(session, connector_key, settings)
    if item.adapter_kind == "browser":
        try:
            account = WeChatBrowserAdapter(settings).whoami()
        except WeChatAdapterError as exc:
            return _read(_transition(session, item, "read", "unsupported", success=False,
                                     error_code=exc.code, error=str(exc)))
        if not account.get("logged_in"):
            return _read(_transition(session, item, "read", "expired", success=False,
                                     error_code="wechat_session_expired", error=account.get("message")))
        return _read(_transition(session, item, "read", "read_succeeded"))
    if item.state not in {"connected", "read_succeeded", "submit_succeeded"}:
        raise ConnectorError("请先完成连接")
    return _read(_transition(session, item, "read", "read_succeeded"))


def submit_draft(session: Session, connector_key: str, simulate_failure: bool = False,
                 settings: Settings | None = None) -> dict[str, Any]:
    item = _get(session, connector_key, settings)
    if item.adapter_kind == "browser":
        raise ConnectorError("真实公众号提交请从草稿中心发起，以保留封面、来源和回执")
    if item.state == "submit_succeeded" and not simulate_failure:
        return _read(item)
    if item.state in {"failed", "submit_succeeded"}:
        prior_read = session.scalar(select(ConnectorEvent).where(
            ConnectorEvent.connector_key == connector_key,
            ConnectorEvent.operation == "read",
            ConnectorEvent.success.is_(True),
        ).order_by(desc(ConnectorEvent.created_at)))
        if prior_read is None:
            raise ConnectorError("失败重试前仍需完成账号读取")
    elif item.state != "read_succeeded":
        raise ConnectorError("请先连接并读取账号")
    if simulate_failure:
        return _read(_transition(session, item, "submit", "failed", success=False,
                                 error_code="mock_submit_failed", error="Mock Connector 模拟提交失败，可重试"))
    return _read(_transition(session, item, "submit", "submit_succeeded"))
