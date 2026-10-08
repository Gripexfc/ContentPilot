PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360606000000004000100ffe2f6b60000000049454e44ae426082"
)


def test_wechat_draft_cover_and_submit_retry(client):
    created = client.post("/api/v1/drafts", json={
        "title": "本地草稿", "digest": "摘要", "author": "作者", "content_html": "<p>正文</p>",
    })
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "writing"
    assert client.post(f"/api/v1/drafts/{draft['id']}/submit", json={}).status_code == 404

    invalid = client.post(f"/api/v1/drafts/{draft['id']}/cover", content=b"fake-image", headers={"content-type": "image/png", "x-filename": "cover.png"})
    assert invalid.status_code == 409
    cover = client.post(f"/api/v1/drafts/{draft['id']}/cover", content=PNG_1X1, headers={"content-type": "image/png", "x-filename": "cover.png"})
    assert cover.status_code == 201
    assert cover.json()["cover_url"].endswith("/cover")
    assert client.post("/api/v1/connectors/wechat-oa/configure").status_code == 200
    assert client.post("/api/v1/connectors/wechat-oa/connect").status_code == 200
    assert client.post("/api/v1/connectors/wechat-oa/read").status_code == 200
    failed = client.post(f"/api/v1/drafts/{draft['id']}/submit", json={"simulate_failure": True})
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["publish_error"]
    failed_detail = client.get(f"/api/v1/drafts/{draft['id']}").json()
    assert failed_detail["status"] == "failed"
    assert failed_detail["events"][-1]["to_status"] == "failed"
    retry = client.post(f"/api/v1/drafts/{draft['id']}/submit", json={"simulate_failure": False})
    assert retry.status_code == 200
    assert retry.json()["status"] == "submitted"
    detail = client.get(f"/api/v1/drafts/{draft['id']}").json()
    assert [event["operation"] for event in detail["events"]] == ["create", "cover_upload", "submit", "submit"]
    assert client.patch(f"/api/v1/drafts/{draft['id']}", json={"title": "不应覆盖", "digest": "", "author": "", "content_html": "<p>x</p>"}).status_code == 409
    assert client.post(f"/api/v1/drafts/{draft['id']}/cover", content=PNG_1X1, headers={"content-type": "image/png", "x-filename": "cover.png"}).status_code == 409
    copied = client.post(f"/api/v1/drafts/{draft['id']}/copy")
    assert copied.status_code == 201
    assert copied.json()["status"] == "writing"
    missing = copied.json()
    # A persisted path that no longer exists must block submission.
    client.app.state.settings.asset_dir.joinpath(missing["cover_path"]).unlink()
    assert client.post(f"/api/v1/drafts/{missing['id']}/submit", json={}).status_code == 404


def test_draft_from_saved_wechat_revision_is_traceable_and_idempotent(client):
    from tests.test_api import profile_payload

    assert client.post("/api/v1/profile/versions", json=profile_payload()).status_code == 201
    task = client.post("/api/v1/tasks", json={"title": "可追溯公众号草稿", "input_text": "素材"}).json()
    brief = client.post(f"/api/v1/tasks/{task['id']}/briefs").json()
    assert client.post(f"/api/v1/tasks/{task['id']}/briefs/{brief['id']}/confirm").status_code == 200
    artifacts = client.post(f"/api/v1/tasks/{task['id']}/generate").json()["artifacts"]
    wechat = next(item for item in artifacts if item["platform"] == "wechat")
    created = client.post(f"/api/v1/artifacts/{wechat['id']}/draft", json={"revision_id": wechat["current_revision_id"]})
    assert created.status_code == 201
    body = created.json()
    assert body["source_task_id"] == task["id"]
    assert body["source_artifact_id"] == wechat["id"]
    assert body["source_revision_id"] == wechat["current_revision_id"]
    duplicate = client.post(f"/api/v1/artifacts/{wechat['id']}/draft", json={"revision_id": wechat["current_revision_id"]})
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == body["id"]
    xhs = next(item for item in artifacts if item["platform"] == "xiaohongshu")
    assert client.post(f"/api/v1/artifacts/{xhs['id']}/draft", json={"revision_id": xhs["current_revision_id"]}).status_code == 409
