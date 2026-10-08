from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from creatoros.db.models import CreatorProfile, CreatorProfileVersion
from creatoros.domain.profile import ProfileSnapshot, ProfileVersionCreate


class ProfileServiceError(RuntimeError):
    code = "profile_error"


class ProfileNotFound(ProfileServiceError):
    code = "profile_not_found"


class ProfileVersionNotFound(ProfileServiceError):
    code = "profile_version_not_found"


class ProfileConflict(ProfileServiceError):
    code = "profile_version_conflict"


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _snapshot(version: CreatorProfileVersion) -> ProfileSnapshot:
    return ProfileSnapshot.model_validate(version.snapshot_json)


def _version_read(version: CreatorProfileVersion) -> Dict[str, Any]:
    return {
        "id": version.id,
        "profile_id": version.profile_id,
        "version_no": version.version_no,
        "parent_version_id": version.parent_version_id,
        "snapshot": _snapshot(version),
        "change_summary": version.change_summary,
        "confirmation_status": version.confirmation_status,
        "confirmed_at": _iso(version.confirmed_at),
        "created_at": version.created_at.isoformat(),
    }


def get_profile(session: Session) -> Tuple[CreatorProfile, CreatorProfileVersion]:
    profile = session.execute(select(CreatorProfile)).scalar_one_or_none()
    if profile is None or not profile.current_version_id:
        raise ProfileNotFound("还没有个人画像")
    version = session.get(CreatorProfileVersion, profile.current_version_id)
    if version is None:
        raise ProfileNotFound("个人画像当前版本不存在")
    return profile, version


def list_versions(session: Session) -> List[CreatorProfileVersion]:
    profile = session.execute(select(CreatorProfile)).scalar_one_or_none()
    if profile is None:
        return []
    return list(
        session.scalars(
            select(CreatorProfileVersion)
            .where(CreatorProfileVersion.profile_id == profile.id)
            .order_by(desc(CreatorProfileVersion.version_no))
        )
    )


def create_version(session: Session, payload: ProfileVersionCreate) -> CreatorProfileVersion:
    try:
        with session.begin():
            profile = session.execute(select(CreatorProfile)).scalar_one_or_none()
            if profile is None:
                if payload.base_version_id:
                    raise ProfileConflict("初次创建画像不能带已有版本基线")
                profile = CreatorProfile(id=str(uuid4()))
                session.add(profile)
                session.flush()
                version_no = 1
                parent_id = None
            else:
                if payload.base_version_id and payload.base_version_id != profile.current_version_id:
                    raise ProfileConflict("画像已产生新版本，请先刷新后再保存")
                parent_id = profile.current_version_id
                latest = session.scalar(
                    select(CreatorProfileVersion.version_no)
                    .where(CreatorProfileVersion.profile_id == profile.id)
                    .order_by(desc(CreatorProfileVersion.version_no))
                    .limit(1)
                )
                version_no = int(latest or 0) + 1

            now = datetime.now(timezone.utc)
            version = CreatorProfileVersion(
                id=str(uuid4()),
                profile_id=profile.id,
                version_no=version_no,
                parent_version_id=parent_id,
                snapshot_json=payload.snapshot.model_dump(mode="json"),
                change_summary=payload.change_summary,
                confirmation_status="confirmed",
                confirmed_at=now,
                created_at=now,
            )
            session.add(version)
            session.flush()
            profile.current_version_id = version.id
            profile.updated_at = now
            return version
    except ProfileServiceError:
        session.rollback()
        raise


def restore_version(session: Session, version_id: str, change_summary: str = "从历史版本恢复") -> CreatorProfileVersion:
    profile, current = get_profile(session)
    target = session.get(CreatorProfileVersion, version_id)
    if target is None or target.profile_id != profile.id:
        raise ProfileVersionNotFound("要恢复的画像版本不存在")
    target_snapshot = _snapshot(target)
    current_id = current.id
    # get_profile/read operations start a SQLAlchemy transaction; close it before
    # create_version opens its own atomic write transaction.
    session.rollback()
    payload = ProfileVersionCreate(
        snapshot=target_snapshot,
        change_summary=change_summary,
        base_version_id=current_id,
    )
    return create_version(session, payload)


def diff_versions(session: Session, left_id: str, right_id: str) -> List[Dict[str, Any]]:
    left = session.get(CreatorProfileVersion, left_id)
    right = session.get(CreatorProfileVersion, right_id)
    if left is None or right is None or left.profile_id != right.profile_id:
        raise ProfileVersionNotFound("比较的画像版本不存在")
    changes: List[Dict[str, Any]] = []
    _diff_values(left.snapshot_json, right.snapshot_json, "", changes)
    return changes


def _diff_values(left: Any, right: Any, path: str, changes: List[Dict[str, Any]]) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else key
            if key not in left:
                changes.append({"path": child, "before": None, "after": right[key]})
            elif key not in right:
                changes.append({"path": child, "before": left[key], "after": None})
            else:
                _diff_values(left[key], right[key], child, changes)
        return
    if left != right:
        changes.append({"path": path, "before": left, "after": right})
