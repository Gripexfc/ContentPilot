import json
from pathlib import Path

from creatoros.services.easel_agent_runner import build_agent_runner


def _write_record(stream: Path, value: dict) -> None:
    with stream.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def test_runner_returns_transcript_backed_skill_and_script_evidence(tmp_path):
    skills = tmp_path / "skills"
    skill = skills / "xhs-note-creator" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: xhs-note-creator\n---\n# skill\n", encoding="utf-8")
    script = skills / "shared" / "scripts" / "validate_meta.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('ok')\n", encoding="utf-8")
    transcript = tmp_path / "session.jsonl"

    def runner(_prompt, timeout, session_id=None):
        assert timeout == 40
        assert session_id == "session-1"
        _write_record(transcript, {
            "type": "message",
            "message": {"role": "assistant", "content": [{
                "type": "tool_use", "id": "read-1", "name": "read",
                "input": {"path": "xhs-note-creator/SKILL.md", "api_key": "SECRET"},
            }]},
        })
        _write_record(transcript, {
            "type": "message",
            "message": {"role": "toolResult", "toolCallId": "read-1", "isError": False},
        })
        _write_record(transcript, {
            "type": "message",
            "message": {"role": "assistant", "content": [{
                "type": "tool_use", "id": "exec-1", "name": "exec",
                "input": {"command": "python skills/shared/scripts/validate_meta.py --token SECRET"},
            }]},
        })
        _write_record(transcript, {
            "type": "message",
            "message": {"role": "toolResult", "toolCallId": "exec-1", "details": {"exitCode": 0}},
        })
        return "完成\nAPI_KEY=SECRET"

    run = build_agent_runner(runner, lambda _session: transcript, skills)
    result = run("prompt", 40, "session-1")
    trace = result["trace"]
    assert result["response"].startswith("完成")
    assert trace["available"] is True
    assert trace["skills_read"] == ["xhs-note-creator"]
    assert trace["skill_paths"] == ["xhs-note-creator/SKILL.md"]
    assert trace["tool_calls"] == [
        {"tool": "read", "status": "succeeded"},
        {"tool": "exec", "status": "succeeded"},
    ]
    assert trace["scripts"] == [{"name": "validate_meta.py", "status": "succeeded"}]
    assert trace["skill_sources"][0]["name"] == "xhs-note-creator"
    assert len(trace["skill_sources"][0]["sha256"]) == 64
    serialized = json.dumps(trace, ensure_ascii=False)
    assert "SECRET" not in serialized
    assert "command" not in serialized


def test_runner_marks_missing_transcript_without_claiming_execution(tmp_path):
    run = build_agent_runner(
        lambda _prompt, _timeout, session_id=None: "我执行了 /xhs-note-creator",
        lambda _session: tmp_path / "missing.jsonl",
        tmp_path / "skills",
    )
    result = run("prompt", 10, "missing")
    assert result["response"].startswith("我执行")
    assert result["trace"]["available"] is False
    assert result["trace"]["skills_read"] == []


def test_runner_does_not_accept_failed_tool_result(tmp_path):
    skill = tmp_path / "skills" / "video-script" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# video\n", encoding="utf-8")
    transcript = tmp_path / "session.jsonl"

    def runner(_prompt, _timeout, session_id=None):
        _write_record(transcript, {"message": {"role": "assistant", "content": [{
            "type": "toolCall", "id": "r", "name": "read",
            "arguments": {"path": "video-script/SKILL.md"},
        }]}})
        _write_record(transcript, {"message": {"role": "toolResult", "toolCallId": "r", "isError": True}})
        return "失败"

    run = build_agent_runner(runner, lambda _session: transcript, tmp_path / "skills")
    trace = run("prompt", 10, "session")["trace"]
    assert trace["skills_read"] == []
    assert trace["tool_calls"] == [{"tool": "read", "status": "failed"}]
