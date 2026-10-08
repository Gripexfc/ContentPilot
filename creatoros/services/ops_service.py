from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from creatoros.db.models import Hotspot, HotspotEvidence, MetricImport, MetricObservation
from creatoros.domain.ops import HotspotCreate, MetricImportCreate
from creatoros.services.metric_analysis import performance_insights


class MetricImportNotFound(RuntimeError):
    code = "metric_import_not_found"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _hotspot_read(session: Session, item: Hotspot) -> Dict[str, Any]:
    evidence = session.scalars(select(HotspotEvidence).where(HotspotEvidence.hotspot_id == item.id)).all()
    return {
        "id": item.id, "title": item.title, "canonical_url": item.canonical_url,
        "source_name": item.source_name, "source_kind": item.source_kind,
        "published_at": _iso(item.published_at), "fetched_at": item.fetched_at.isoformat(),
        "summary": item.summary, "fact_status": item.fact_status, "heat_status": item.heat_status,
        "relevance_score": item.relevance_score, "relevance_reason": item.relevance_reason,
        "platform_fit": item.platform_fit_json, "needs_human_review": item.needs_human_review,
        "evidence": [{"id": e.id, "evidence_type": e.evidence_type, "source_url": e.source_url,
                       "claim": e.claim, "value": e.value_json, "verification_status": e.verification_status,
                       "checked_at": _iso(e.checked_at)} for e in evidence],
        "created_at": item.created_at.isoformat(),
    }


def create_hotspot(session: Session, payload: HotspotCreate) -> Hotspot:
    now = datetime.now(timezone.utc)
    with session.begin():
        item = Hotspot(id=str(uuid4()), title=payload.title, canonical_url=payload.canonical_url,
                       source_name=payload.source_name, source_kind=payload.source_kind,
                       published_at=payload.published_at, fetched_at=now, summary=payload.summary,
                       fact_status=payload.fact_status, heat_status=payload.heat_status,
                       relevance_score=payload.relevance_score, relevance_reason=payload.relevance_reason,
                       platform_fit_json=payload.platform_fit, needs_human_review=payload.needs_human_review,
                       created_at=now)
        session.add(item)
        for raw in payload.evidence:
            session.add(HotspotEvidence(id=str(uuid4()), hotspot_id=item.id,
                        evidence_type=str(raw.get("evidence_type", "source")),
                        source_url=str(raw.get("source_url", payload.canonical_url)),
                        claim=str(raw.get("claim", "")), value_json=raw.get("value", {}),
                        verification_status=str(raw.get("verification_status", "unverified")),
                        checked_at=now if raw.get("verification_status") == "verified" else None))
        session.flush()
        return item


def list_hotspots(session: Session) -> List[Dict[str, Any]]:
    return [_hotspot_read(session, item) for item in session.scalars(select(Hotspot).order_by(desc(Hotspot.fetched_at)))]


def _row_hash(row: Dict[str, Any]) -> str:
    normalized = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def import_metrics(session: Session, payload: MetricImportCreate) -> MetricImport:
    now = datetime.now(timezone.utc)
    errors: List[Dict[str, Any]] = []
    with session.begin():
        item = MetricImport(id=str(uuid4()), platform=payload.platform, source_type=payload.source_type,
                            imported_at=now, observed_at=payload.observed_at, status="ready",
                            original_name=payload.original_name, row_count=0, error_json={})
        session.add(item)
        seen = set()
        for index, row in enumerate(payload.rows):
            row_hash = _row_hash(row)
            if row_hash in seen:
                continue
            seen.add(row_hash)
            title = str(row.get("title", row.get("标题", "")))
            content_ref = str(row.get("content_ref", row.get("内容ID", row.get("content_id", ""))))
            pillar = str(row.get("pillar", row.get("内容支柱", "")))
            if not title and not content_ref:
                errors.append({"row": index + 1, "message": "缺少 title 或 content_ref，已跳过"})
                continue
            known = {"title", "标题", "content_ref", "content_id", "内容ID", "pillar", "内容支柱",
                     "published_at", "发布时间", "content_type", "内容类型", "source_ref", "数据来源"}
            metrics = {str(k): v for k, v in row.items() if k not in known}
            published_raw = row.get("published_at", row.get("发布时间"))
            published = None
            if isinstance(published_raw, str) and published_raw.strip():
                try:
                    published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                except ValueError:
                    errors.append({"row": index + 1, "message": "发布时间无法解析，保留为空"})
            session.add(MetricObservation(id=str(uuid4()), import_id=item.id, platform=payload.platform,
                         content_ref=content_ref, title_ref=title, published_at=published,
                         content_type=str(row.get("content_type", row.get("内容类型", ""))), pillar=pillar,
                         metrics_json=metrics, source_ref=str(row.get("source_ref", row.get("数据来源", payload.source_type))),
                         observed_at=payload.observed_at, row_hash=row_hash))
            item.row_count += 1
        if errors:
            item.status = "ready_with_warnings"
            item.error_json = {"warnings": errors}
        session.flush()
        return item


def _metric_read(item: MetricImport) -> Dict[str, Any]:
    return {"id": item.id, "platform": item.platform, "source_type": item.source_type,
            "imported_at": item.imported_at.isoformat(), "observed_at": item.observed_at.isoformat(),
            "status": item.status, "original_name": item.original_name, "row_count": item.row_count,
            "error": item.error_json}


def list_metric_imports(session: Session) -> List[Dict[str, Any]]:
    return [_metric_read(item) for item in session.scalars(select(MetricImport).order_by(desc(MetricImport.imported_at)))]


def metric_performance_insights(session: Session, platform: str | None = None) -> Dict[str, Any]:
    batches = list(session.scalars(select(MetricImport)))
    excluded = {item.id for item in batches if item.source_type == "acceptance_test" or item.status == "excluded"}
    rows = list(session.scalars(select(MetricObservation).where(~MetricObservation.import_id.in_(excluded)))) if excluded else list(session.scalars(select(MetricObservation)))
    return performance_insights(rows, platform=platform)


def metric_summary(session: Session) -> Dict[str, Any]:
    from creatoros.services.metric_analysis import summarize_observations
    batches = list(session.scalars(select(MetricImport)))
    excluded = {item.id for item in batches if item.source_type == "acceptance_test" or item.status == "excluded"}
    rows = [item for item in session.scalars(select(MetricObservation)) if item.import_id not in excluded]
    return {
        "observation_count": len(rows), "import_count": len(batches) - len(excluded),
        **summarize_observations(rows),
        "data_quality": {"acceptance_test_imports": sum(item.source_type == "acceptance_test" for item in batches),
                         "excluded_imports": len(excluded), "real_imports": len(batches) - len(excluded)},
        "limitations": ["仅分析用户导入数据，来源真实性需人工确认；无行业基准、增长率或因果结论。",
                        "按平台和同名指标分别统计最小值、最大值与均值，缺失值不计为零，完读率不相加。",
                        "观察值可能包含同一内容在不同时间的累计快照，不代表新增流量；重复观察不相加。",
                        "演练和已排除的批次保留溯源记录，但不进入表现统计。"],
    }


def set_import_inclusion(session: Session, import_id: str, included: bool) -> MetricImport:
    with session.begin():
        item = session.get(MetricImport, import_id)
        if item is None:
            raise MetricImportNotFound("导入批次不存在")
        item.status = ("ready_with_warnings" if item.error_json.get("warnings") else "ready") if included else "excluded"
        return item
