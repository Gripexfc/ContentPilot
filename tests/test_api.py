def profile_payload(name: str = "本地作者", pillar: str = "工程实践") -> dict:
    return {
        "snapshot": {
            "identity": {"display_name": name, "profession": "独立创作者"},
            "experiences": [],
            "domains": ["内容产品"],
            "pillars": [pillar],
            "readers": [{"name": "需要方法的创作者", "problems": ["缺少可执行步骤"]}],
            "voice": {"tone": "具体、克制", "examples": []},
            "boundaries": {"forbidden_words": ["绝对"], "sensitive_topics": [], "unwanted_expressions": []},
            "platforms": {
                "wechat": {"positioning": "长文解释", "audience": "专业读者", "format_preferences": [], "tone": "克制"},
                "xiaohongshu": {"positioning": "卡片方法", "audience": "移动端读者", "format_preferences": [], "tone": "清楚"},
                "douyin": {"positioning": "短视频拆解", "audience": "需要快速理解的人", "format_preferences": [], "tone": "直接"},
            },
            "goals": {"priorities": ["知识沉淀"]},
            "evidence_refs": [],
        },
        "change_summary": "初次建立画像",
    }


def test_status_and_profile_round_trip(client):
    status = client.get("/api/v1/status")
    assert status.status_code == 200
    assert status.json()["scope"] == "local-first"

    created = client.post("/api/v1/profile/versions", json=profile_payload())
    assert created.status_code == 201
    version = created.json()
    assert version["version_no"] == 1

    current = client.get("/api/v1/profile")
    assert current.status_code == 200
    assert current.json()["current_version_id"] == version["id"]

    versions = client.get("/api/v1/profile/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 1


def test_overview_snapshot_exposes_recovery_counts(client):
    empty = client.get("/api/v1/overview")
    assert empty.status_code == 200
    assert empty.json()["active_task_count"] == 0
    assert empty.json()["pending_source_count"] == 0
    assert empty.json()["last_metric_imported_at"] is None

    assert client.post("/api/v1/profile/versions", json=profile_payload()).status_code == 201
    task = client.post("/api/v1/tasks", json={"title": "总览快照任务", "input_text": "素材"})
    assert task.status_code == 201
    hotspot = client.post("/api/v1/hotspots", json={
        "title": "待核验线索", "canonical_url": "https://example.com/overview",
        "source_name": "手动来源", "summary": "尚未核验", "fact_status": "unverified",
        "heat_status": "unknown", "needs_human_review": True,
    })
    assert hotspot.status_code == 201
    snapshot = client.get("/api/v1/overview")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["active_task_count"] == 1
    assert body["pending_source_count"] == 1
    assert body["read_at"]


def test_empty_profile_has_recoverable_error(client):
    response = client.get("/api/v1/profile")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "profile_not_found"
    task = client.post("/api/v1/tasks", json={"title": "没有画像的主题", "input_text": ""})
    assert task.status_code == 409
    assert task.json()["detail"]["code"] == "content_conflict"


def test_quick_draft_requires_profile_and_persists_idempotently(client):
    payload = {
        "quick_draft_id": "browser-draft-1",
        "topic": "把保存做成可恢复的内容",
        "context": "用户提供的补充素材",
        "source": {"title": "热点线索", "url": "https://example.com/source"},
        "platform": "wechat",
        "mode": "文章",
        "skill": "social-content",
        "workflow_id": "0123456789ab",
        "output": "第一版草稿",
    }
    blocked = client.post("/api/v1/quick-drafts", json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "profile_required"

    assert client.post("/api/v1/profile/versions", json=profile_payload()).status_code == 201
    saved = client.post("/api/v1/quick-drafts", json=payload)
    assert saved.status_code == 201
    first = saved.json()
    assert first["input_version"] == 1
    assert first["persistence_state"] == "saved_input"
    assert first["content_status"] == "draft"
    assert first["publish_state"] == "not_started"
    assert first["context"] == payload["context"]
    assert first["source"] == payload["source"]
    assert first["workflow_id"] == payload["workflow_id"]

    repeated = client.post("/api/v1/quick-drafts", json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["task_id"] == first["task_id"]
    assert repeated.json()["input_id"] == first["input_id"]
    assert repeated.json()["input_version"] == 1

    edited = dict(payload, topic="更新后的内容主题", output="第二版草稿：用户编辑")
    saved_again = client.post("/api/v1/quick-drafts", json=edited)
    assert saved_again.status_code == 201
    second = saved_again.json()
    assert second["task_id"] == first["task_id"]
    assert second["input_id"] != first["input_id"]
    assert second["input_version"] == 2
    assert second["title"] == edited["topic"]

    listed = client.get("/api/v1/quick-drafts")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["title"] == edited["topic"]
    assert listed.json()[0]["output"] == "第二版草稿：用户编辑"
    detail = client.get(f"/api/v1/tasks/{first['task_id']}")
    assert detail.status_code == 200
    assert [row["input_type"] for row in detail.json()["inputs"]].count("generated_markdown") == 2

    # Updating context or provenance must persist even when the draft text is
    # unchanged, and must not rewrite the metadata of an older input version.
    current_payload = edited
    current = second
    metadata_edits = {
        "context": "补充核验后的素材",
        "source": {"label": "一手来源", "url": "https://example.com/verified"},
        "platform": "xiaohongshu",
        "mode": "配图",
        "skill": "updated-skill",
        "workflow_id": "abcdef012345",
        "output_artifact": "workflow-abcdef012345/09-xhs-final.md",
    }
    for field, value in metadata_edits.items():
        current_payload = dict(current_payload, **{field: value})
        updated = client.post("/api/v1/quick-drafts", json=current_payload)
        assert updated.status_code == 201
        updated_body = updated.json()
        assert updated_body[field] == value
        assert updated_body["input_version"] == current["input_version"] + 1
        assert updated_body["input_id"] != current["input_id"]
        assert updated_body["output"] == second["output"]
        current = updated_body

    combined_payload = dict(current_payload, mode="内容+配图")
    combined = client.post("/api/v1/quick-drafts", json=combined_payload)
    assert combined.status_code == 201
    assert combined.json()["mode"] == "内容+配图"
    assert combined.json()["input_version"] == current["input_version"] + 1
    current_payload = combined_payload
    current = combined.json()

    unchanged = client.post("/api/v1/quick-drafts", json=current_payload).json()
    assert unchanged["input_id"] == current["input_id"]
    assert unchanged["input_version"] == current["input_version"]
    inputs = client.get(f"/api/v1/tasks/{first['task_id']}").json()["inputs"]
    original = next(row for row in inputs if row["id"] == first["input_id"])
    assert original["metadata"]["context"] == payload["context"]
    assert original["metadata"]["source"] == payload["source"]
    assert original["metadata"]["workflow_id"] == payload["workflow_id"]
    latest = client.get("/api/v1/quick-drafts").json()[0]
    assert latest["input_id"] == current["input_id"]
    assert latest["output_artifact"] == metadata_edits["output_artifact"]


def test_profile_conflict_and_restore(client):
    first = client.post("/api/v1/profile/versions", json=profile_payload()).json()
    second_payload = profile_payload(pillar="内容系统")
    second_payload["base_version_id"] = first["id"]
    second = client.post("/api/v1/profile/versions", json=second_payload)
    assert second.status_code == 201

    stale_payload = profile_payload(pillar="过期修改")
    stale_payload["base_version_id"] = first["id"]
    conflict = client.post("/api/v1/profile/versions", json=stale_payload)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "profile_version_conflict"

    restored = client.post(f"/api/v1/profile/restore/{first['id']}")
    assert restored.status_code == 201
    assert restored.json()["version_no"] == 3

    diff = client.get(f"/api/v1/profile/versions/{first['id']}/diff/{second.json()['id']}")
    assert diff.status_code == 200
    assert any(item["path"] == "pillars" for item in diff.json()["changes"])


def test_content_vertical_slice_and_memory_confirmation(client):
    profile = client.post("/api/v1/profile/versions", json=profile_payload())
    assert profile.status_code == 201

    task = client.post(
        "/api/v1/tasks",
        json={"title": "如何把一个主题拆成可验证的内容", "input_text": "手动主题：从事实到行动"},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    brief = client.post(f"/api/v1/tasks/{task_id}/briefs")
    assert brief.status_code == 201
    brief_body = brief.json()
    assert brief_body["confirmation_status"] == "draft"
    blocked = client.post(f"/api/v1/tasks/{task_id}/generate")
    assert blocked.status_code == 409

    confirmed = client.post(f"/api/v1/tasks/{task_id}/briefs/{brief_body['id']}/confirm")
    assert confirmed.status_code == 200
    generated = client.post(f"/api/v1/tasks/{task_id}/generate")
    assert generated.status_code == 201
    artifacts = generated.json()["artifacts"]
    assert {item["platform"] for item in artifacts} == {"wechat", "xiaohongshu", "douyin"}
    contents = [item["current_revision"]["content"] for item in artifacts]
    assert len({str(item) for item in contents}) == 3

    detail = client.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["task"]["status"] == "adapted"
    wechat = next(item for item in artifacts if item["platform"] == "wechat")
    content = dict(wechat["current_revision"]["content"])
    content["summary"] = content["summary"] + " 用户补充了一句自己的判断。"
    edited = client.post(
        f"/api/v1/artifacts/{wechat['id']}/revisions",
        json={"content": content, "reason": "保留更具体的作者判断", "base_revision_id": wechat["current_revision"]["id"]},
    )
    assert edited.status_code == 201
    assert edited.json()["current_revision"]["revision_no"] == 2

    memories = client.get(f"/api/v1/memories?task_id={task_id}")
    assert memories.status_code == 200
    memory = memories.json()[0]
    assert memory["confirmation_status"] == "proposed"
    accepted = client.post(f"/api/v1/memories/{memory['id']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["confirmation_status"] == "confirmed"


def test_content_revisions_are_editable_and_status_is_explicit(client):
    assert client.post("/api/v1/profile/versions", json=profile_payload()).status_code == 201
    task = client.post("/api/v1/tasks", json={"title": "可继续的任务", "input_text": "原始素材"}).json()
    brief = client.post(f"/api/v1/tasks/{task['id']}/briefs").json()
    revised = client.post(f"/api/v1/tasks/{task['id']}/brief-revisions", json={
        "base_brief_id": brief["id"],
        "reader_problem": "读者要解决一个具体问题",
        "author_angle": "作者提供一条真实经验",
        "facts": ["待核验事实"],
        "sources": ["https://example.com/source"],
        "research_gaps": ["确认原始来源"],
    })
    assert revised.status_code == 201
    assert revised.json()["version_no"] == 2
    assert client.post(f"/api/v1/tasks/{task['id']}/briefs/{revised.json()['id']}/confirm").status_code == 200
    generated = client.post(f"/api/v1/tasks/{task['id']}/generate").json()
    artifact = generated["artifacts"][0]
    content = artifact["current_revision"]["content"]
    content["title"] = "用户真正修改的标题"
    updated = client.post(f"/api/v1/artifacts/{artifact['id']}/revisions", json={
        "content": content,
        "reason": "标题要更具体",
        "base_revision_id": artifact["current_revision"]["id"],
    })
    assert updated.status_code == 201
    history = client.get(f"/api/v1/artifacts/{artifact['id']}/revisions")
    assert history.status_code == 200
    assert history.json()[0]["edits"]
    assert client.get(f"/api/v1/tasks/{task['id']}").json()["task"]["status"] == "reviewing"
    assert client.post(f"/api/v1/tasks/{task['id']}/status", json={"status": "archived"}).status_code == 200
    blocked = client.post(f"/api/v1/tasks/{task['id']}/generate")
    assert blocked.status_code == 409


def test_confirmed_memory_is_scoped_to_later_generation_and_revoke_stops_it(client):
    assert client.post("/api/v1/profile/versions", json=profile_payload()).status_code == 201

    def make_task():
        task = client.post("/api/v1/tasks", json={"title": "跨任务记忆验证", "input_text": "同一输入"}).json()
        brief = client.post(f"/api/v1/tasks/{task['id']}/briefs").json()
        assert client.post(f"/api/v1/tasks/{task['id']}/briefs/{brief['id']}/confirm").status_code == 200
        generated = client.post(f"/api/v1/tasks/{task['id']}/generate").json()
        return task, next(item for item in generated["artifacts"] if item["platform"] == "wechat")

    first_task, first_artifact = make_task()
    edited = dict(first_artifact["current_revision"]["content"])
    edited["summary"] += "（真实现场优先）"
    assert client.post(f"/api/v1/artifacts/{first_artifact['id']}/revisions", json={
        "content": edited, "reason": "公众号开头保留真实现场",
        "base_revision_id": first_artifact["current_revision"]["id"],
    }).status_code == 201
    memory = client.get(f"/api/v1/memories?task_id={first_task['id']}").json()[0]
    assert client.post(f"/api/v1/memories/{memory['id']}/accept").json()["confirmation_status"] == "confirmed"

    _, second_artifact = make_task()
    assert second_artifact["current_revision"]["memory_ids"] == [memory["id"]]
    assert second_artifact["current_revision"]["content"]["memory_guidance"] == ["公众号开头保留真实现场"]
    assert client.post(f"/api/v1/memories/{memory['id']}/decisions", json={"action": "revoke"}).json()["confirmation_status"] == "revoked"

    _, third_artifact = make_task()
    assert third_artifact["current_revision"]["memory_ids"] == []


def test_hotspot_and_metrics_import_are_traceable(client):
    hotspot = client.post("/api/v1/hotspots", json={
        "title": "官方公告线索",
        "canonical_url": "https://example.com/official-notice",
        "source_name": "官方公告",
        "source_kind": "official",
        "summary": "公告中的可核验摘要",
        "fact_status": "unverified",
        "heat_status": "unknown",
        "platform_fit": {"wechat": True, "xiaohongshu": False, "douyin": False},
        "needs_human_review": True,
        "evidence": [{"evidence_type": "original_link", "source_url": "https://example.com/official-notice", "claim": "待人工核验", "value": {}, "verification_status": "unverified"}],
    })
    assert hotspot.status_code == 201
    assert hotspot.json()["fact_status"] == "unverified"
    assert hotspot.json()["evidence"][0]["verification_status"] == "unverified"
    assert client.get("/api/v1/hotspots").status_code == 200

    imported = client.post("/api/v1/metrics/imports", json={
        "platform": "wechat",
        "source_type": "manual_json",
        "observed_at": "2026-09-30T00:00:00Z",
        "original_name": "metrics.json",
        "rows": [{"title": "一次复盘", "pillar": "工程实践", "阅读": 1200, "点赞": 42}],
    })
    assert imported.status_code == 201
    assert imported.json()["row_count"] == 1
    summary = client.get("/api/v1/metrics/summary")
    assert summary.status_code == 200
    assert summary.json()["observation_count"] == 1
    assert summary.json()["by_platform"]["wechat"] == 1
    assert summary.json()["limitations"]


def test_hotspot_can_start_task_and_artifact_can_be_exported(client, app_settings):
    assert client.post("/api/v1/profile/versions", json=profile_payload()).status_code == 201
    hotspot = client.post("/api/v1/hotspots", json={
        "title": "可进入工作台的热点", "canonical_url": "https://example.com/hotspot",
        "source_name": "用户手动来源", "summary": "待核验摘要", "fact_status": "unverified",
        "heat_status": "unknown", "needs_human_review": True,
    }).json()
    made = client.post(f"/api/v1/hotspots/{hotspot['id']}/task")
    assert made.status_code == 201
    detail = client.get(f"/api/v1/tasks/{made.json()['id']}").json()
    assert detail["inputs"][0]["input_type"] == "hotspot"
    uploaded = client.post(f"/api/v1/tasks/{made.json()['id']}/inputs/file", content=b"# local note", headers={"content-type": "text/markdown", "x-filename": "note.md"})
    assert uploaded.status_code == 201
    assert uploaded.json()["metadata"]["original_name"] == "note.md"
    brief = client.post(f"/api/v1/tasks/{made.json()['id']}/briefs").json()
    assert client.post(f"/api/v1/tasks/{made.json()['id']}/briefs/{brief['id']}/confirm").status_code == 200
    artifact = client.post(f"/api/v1/tasks/{made.json()['id']}/generate").json()["artifacts"][0]
    exported = client.get(f"/api/v1/artifacts/{artifact['id']}/export?format=markdown")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/markdown")
    assert "Content-Disposition" in exported.headers
    assert client.get(f"/api/v1/artifacts/{artifact['id']}/export?format=json").headers["content-type"].startswith("application/json")
    assert client.get(f"/api/v1/artifacts/{artifact['id']}/export?format=html").headers["content-type"].startswith("text/html")


def test_performance_insights_require_repeated_samples_and_are_cautious(client):
    rows = []
    for index in range(5):
        rows.append({"title": f"方法文章 {index}", "pillar": "方法", "阅读": 220})
        rows.append({"title": f"观点文章 {index}", "pillar": "观点", "阅读": 100})
    imported = client.post("/api/v1/metrics/imports", json={
        "platform": "wechat", "source_type": "manual_json",
        "observed_at": "2026-09-30T00:00:00Z", "original_name": "insights.json", "rows": rows,
    })
    assert imported.status_code == 201
    response = client.get("/api/v1/metrics/insights?platform=wechat")
    assert response.status_code == 200
    body = response.json()
    assert body["usable"]
    assert body["usable"][0]["label"] == "方法"
    assert body["usable"][0]["sample_count"] == 5
    assert any("相关性提示" in item for item in body["limitations"])
    assert client.get("/api/v1/metrics/insights?platform=weibo").status_code == 422


def test_metric_summary_is_descriptive_and_excludes_acceptance_batches(client):
    for source_type, title, value in (("manual_json", "真实导入一", 10), ("manual_json", "真实导入二", 20), ("acceptance_test", "演练数据", 999)):
        response = client.post("/api/v1/metrics/imports", json={
            "platform": "wechat", "source_type": source_type,
            "observed_at": "2026-09-30T00:00:00Z", "original_name": f"{source_type}.json",
            "rows": [{"title": title, "pillar": "工程实践", "阅读": value}],
        })
        assert response.status_code == 201
    summary = client.get("/api/v1/metrics/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["observation_count"] == 2
    assert body["data_quality"]["acceptance_test_imports"] == 1
    assert body["metrics_by_platform"]["wechat"]["reads"]["max"] == 20
    assert body["top_content"][0]["title"] == "真实导入二"
