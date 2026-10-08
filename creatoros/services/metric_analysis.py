"""Descriptive statistics only; preserve each observation's source and units."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Optional

ALIASES = {
    "曝光": "exposure", "曝光量": "exposure", "阅读": "reads", "阅读量": "reads",
    "播放": "plays", "播放量": "plays", "点赞": "likes", "评论": "comments",
    "收藏": "saves", "转发": "shares", "新增关注": "new_followers",
    "完读率": "completion_rate", "转化": "conversions",
}
COUNTS = {"exposure", "reads", "plays", "likes", "comments", "saves", "shares", "new_followers", "conversions"}


def number(value: Any, rate: bool = False) -> Optional[float]:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        text = str(value).strip()
        result = float(text[:-1]) / 100 if text.endswith("%") and rate else float(text.replace(",", ""))
        if not math.isfinite(result) or result < 0 or (rate and result > 1):
            return None
        return result
    except (TypeError, ValueError):
        return None


def normalized_metrics(raw: Dict[str, Any]) -> Dict[str, float]:
    result = {}
    for key, value in raw.items():
        key = ALIASES.get(key, key)
        if key not in COUNTS and key != "completion_rate":
            continue
        numeric = number(value, rate=key == "completion_rate")
        if numeric is not None:
            result[key] = numeric
    return result


def summarize_observations(rows):
    groups = defaultdict(lambda: defaultdict(list))
    by_platform, by_pillar = {}, {}
    observations = []
    scored = []
    for row in rows:
        by_platform[row.platform] = by_platform.get(row.platform, 0) + 1
        by_pillar[row.pillar or "未标注支柱"] = by_pillar.get(row.pillar or "未标注支柱", 0) + 1
        for key, value in normalized_metrics(row.metrics_json).items():
            groups[row.platform][key].append(value)
        normalized = normalized_metrics(row.metrics_json)
        observations.append({"id": row.id, "import_id": row.import_id, "content_ref": row.content_ref,
                             "title": row.title_ref or row.content_ref, "platform": row.platform,
                             "pillar": row.pillar, "content_type": row.content_type,
                             "published_at": row.published_at.isoformat() if row.published_at else None,
                             "observed_at": row.observed_at.isoformat(), "metrics": row.metrics_json,
                             "source_ref": row.source_ref})
        score = max((normalized.get(key, -1) for key in ("exposure", "reads", "plays")), default=-1)
        scored.append({"title": row.title_ref or row.content_ref, "platform": row.platform,
                       "metrics": row.metrics_json, "numeric_metrics": normalized,
                       "observed_at": row.observed_at.isoformat(), "score_basis": "曝光/阅读/播放", "score": score})
    statistics = {
        platform: {key: {"count": len(values), "min": min(values), "max": max(values),
                         "mean": sum(values) / len(values)} for key, values in metrics.items()}
        for platform, metrics in groups.items()
    }
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"by_platform": by_platform, "by_pillar": by_pillar,
            "metrics_by_platform": statistics,
            "observations": sorted(observations, key=lambda item: item["observed_at"], reverse=True)[:100],
            "top_content": scored[:10]}


PRIMARY_METRIC = {
    "wechat": ("reads", "阅读量"),
    "xiaohongshu": ("saves", "收藏量"),
    "douyin": ("completion_rate", "完播率"),
}


def performance_insights(rows, platform: str | None = None) -> dict[str, Any]:
    """Turn imported account observations into cautious, reviewable suggestions.

    This is deliberately descriptive: it compares a platform's own observations,
    requires repeated samples, and never mutates the profile automatically.
    """
    selected = [row for row in rows if not platform or row.platform == platform]
    by_platform: dict[str, list[Any]] = defaultdict(list)
    for row in selected:
        by_platform[row.platform].append(row)
    insights: list[dict[str, Any]] = []
    limitations: list[str] = [
        "这是账号内部的相关性提示，不是因果结论；付费流量、发布时间和外部事件仍需人工区分。",
        "候选经验不会自动写入画像，确认后才会进入后续内容生成。",
    ]
    for current_platform, platform_rows in sorted(by_platform.items()):
        primary_key, primary_label = PRIMARY_METRIC.get(current_platform, ("reads", "阅读量"))
        normalized_rows = [(row, normalized_metrics(row.metrics_json)) for row in platform_rows]
        metric_key = primary_key
        metric_label = primary_label
        if not any(primary_key in normalized for _, normalized in normalized_rows):
            fallback_labels = {
                "reads": "阅读量", "plays": "播放量", "exposure": "曝光量",
                "likes": "点赞量", "comments": "评论量", "saves": "收藏量",
                "shares": "转发量",
            }
            fallback_order = ("reads", "plays", "exposure", "likes", "comments", "saves", "shares")
            metric_key = max(fallback_order, key=lambda key: sum(key in normalized for _, normalized in normalized_rows))
            metric_label = fallback_labels[metric_key]
        scored = [
            (row, float(normalized[metric_key]))
            for row, normalized in normalized_rows
            if normalized.get(metric_key) is not None
        ]
        if len(scored) < 3:
            limitations.append(f"{current_platform} 有效样本仅 {len(scored)} 条，暂不生成自动优化建议。")
            continue
        overall = sum(value for _, value in scored) / len(scored)
        if overall <= 0:
            limitations.append(f"{current_platform} 的 {metric_label} 均值为 0，暂不比较内容分组。")
            continue
        groups: dict[tuple[str, str], list[tuple[Any, float]]] = defaultdict(list)
        for row, value in scored:
            dimension = "内容支柱" if row.pillar else "内容类型"
            label = row.pillar or row.content_type or "未标注"
            groups[(dimension, label)].append((row, value))
        for (dimension, label), group in groups.items():
            sample_count = len(group)
            if sample_count < 3:
                continue
            average = sum(value for _, value in group) / sample_count
            uplift = (average - overall) / overall
            if abs(uplift) < 0.15:
                continue
            direction = "高于" if uplift > 0 else "低于"
            confidence = "候选" if sample_count >= 5 else "观察"
            ready = sample_count >= 5 and uplift >= 0.15
            statement = (
                f"{current_platform} 的{dimension}“{label}”{metric_label}均值 {average:.0f}，"
                f"{direction}该账号同平台样本均值 {abs(uplift):.0%}；样本 {sample_count} 条。"
            )
            insights.append({
                "platform": current_platform,
                "dimension": dimension,
                "label": label,
                "metric": metric_key,
                "metric_label": metric_label,
                "sample_count": sample_count,
                "average": round(average, 3),
                "account_average": round(overall, 3),
                "relative_change": round(uplift, 4),
                "status": confidence,
                "ready_for_use": ready,
                "statement": statement,
                "evidence_observation_ids": [row.id for row, _ in group[:8]],
            })
    insights.sort(key=lambda item: (item["ready_for_use"], abs(item["relative_change"]), item["sample_count"]), reverse=True)
    if not insights:
        limitations.append("当前没有达到重复样本和差异阈值的内容模式；继续积累发布数据。")
    return {
        "insights": insights[:20],
        "usable": [item for item in insights if item["ready_for_use"]][:8],
        "limitations": limitations,
        "data_quality": {current_platform: len(rows) for current_platform, rows in sorted(by_platform.items())},
    }
