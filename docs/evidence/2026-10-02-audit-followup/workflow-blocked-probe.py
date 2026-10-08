"""Read-only source audit; synthetic runner only, no model or platform calls.

Run from CreatorOS with .venv312/bin/python and redirect stdout to a JSON file
if a persistent receipt is desired. Workflow files go to a fresh temp directory.
This records current behavior, rather than treating the known bug as a passing
product acceptance test.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from creatoros.services.workflow_service import WorkflowService  # noqa: E402


def probe(gateway_online: bool) -> dict:
    calls = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return "BLOCKED：测试夹具，原始来源不可访问，不能继续正文生成。"

    with tempfile.TemporaryDirectory(prefix="creatoros-blocked-audit-") as directory:
        service = WorkflowService(Path(directory), lambda: gateway_online, runner)
        try:
            job_id = service.start("合成审计夹具，不是真实文章", ["wechat-oa"])["id"]
        finally:
            service.executor.shutdown(wait=True)
        job = service.get(job_id)
        return {
            "gateway_fixture": gateway_online,
            "runner_fixture": "explicit BLOCKED text",
            "runner_calls": len(calls),
            "job_status": job["status"],
            "stage_statuses": {key: value["status"] for key, value in job["stages"].items()},
            "content_status": job.get("content_status"),
            "published": job.get("published"),
            "expected": {"job_status": "blocked", "runner_calls": 1 if gateway_online else 0},
            "matches_expected": job["status"] == "blocked" and len(calls) == (1 if gateway_online else 0),
        }


source = ROOT / "creatoros/services/workflow_service.py"
print(json.dumps({
    "observed_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    "kind": "synthetic_service_probe",
    "external_calls": False,
    "source": str(source.relative_to(ROOT)),
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "cases": [probe(False), probe(True)],
}, ensure_ascii=False, indent=2))
