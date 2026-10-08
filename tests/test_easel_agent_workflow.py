"""Easel Agent orchestration tests; no model, browser, publisher or network is used."""
from __future__ import annotations

import time
from pathlib import Path

import creatoros.services.easel_agent_workflow as workflow_module
from creatoros.services.easel_agent_workflow import EaselAgentWorkflowService


def _wait(service, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job["status"] not in {"queued", "running"} and job_id not in service.active:
            return job
        time.sleep(0.01)
    raise AssertionError("easel agent workflow did not settle")


def test_easel_agent_platform_receipt_is_completion_evidence(tmp_path, monkeypatch):
    def validate(platform, directory, skills_root, output_kind="standard"):
        return {
            "status": "passed",
            "checks": [{"name": "fixture-check", "status": "passed"}],
            "missing": [],
            "artifacts": ["main.md"],
            "primary_text": "main.md",
            "copy_text": "可复制内容",
            "media_kind": "script" if platform == "douyin" else "article",
        }

    monkeypatch.setattr(workflow_module, "validate_platform", validate)

    def agent(prompt, timeout, session_id):
        job_id = session_id.split("-")[1]
        folder = tmp_path / f"workflow-{job_id}"
        if "发现与核验" in prompt:
            path = folder / "01-discovery.md"
        elif "选题与结构" in prompt:
            path = folder / "02-topic.md"
        elif "母稿" in prompt:
            path = folder / "03-master.md"
        elif "抖音" in prompt:
            path = folder / "douyin" / "main.md"
        elif "公众号" in prompt:
            path = folder / "wechat-oa" / "main.md"
        elif "质量检查" in prompt:
            path = folder / "05-quality.md"
        else:
            path = folder / "06-archive-checklist.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
        return {"response": '{"status":"completed"}', "trace": {"available": True, "skills_read": ["fixture"]}}

    service = EaselAgentWorkflowService(tmp_path, lambda: True, agent)
    try:
        job_id = service.start("主题", ["douyin", "wechat-oa"])["id"]
        job = _wait(service, job_id)
        assert job["status"] == "completed"
        assert job["execution_mode"] == "easel-agent-v1"
        assert all(item["status"] == "completed" for item in job["platform_outputs"].values())
        assert job["platform_outputs"]["douyin"]["primary_text"].endswith("/douyin/main.md")
        assert job["platform_outputs"]["douyin"]["copy_text"] == "可复制内容"
        assert any(item["trace"]["available"] for item in job["execution_receipts"])
        assert job_id not in service.active
    finally:
        service.executor.shutdown()
