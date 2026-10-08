"""Collect a minimal execution receipt from an OpenClaw session transcript.

The Agent's prose is not execution evidence. Only tool-call records appended by
this invocation are considered, and no arguments, outputs, prompts or session
paths are included in the receipt returned to the workbench.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any, Callable

_MAX_TRACE_BYTES = 16 * 1024 * 1024
_READ_TOOLS = {"read", "read_file", "read_text_file", "read_multiple_files"}
_EXEC_TOOLS = {"exec", "bash", "shell", "exec_command", "run_command", "execute"}
_SCRIPT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".sh"}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _unavailable(reason: str) -> dict[str, Any]:
    return {"source": "session_transcript", "available": False, "reason": reason,
            "skills_read": [], "skill_paths": [], "tools": [], "tool_calls": [], "scripts": [], "skill_sources": []}


def _snapshot(path: Path) -> tuple[int, int, int, bytes] | None:
    try:
        with path.open("rb") as stream:
            stat = path.stat()
            prefix = stream.read(min(stat.st_size, 4096))
        return stat.st_dev, stat.st_ino, stat.st_size, prefix
    except OSError:
        return None


def _new_records(path: Path, before: tuple[int, int, int, bytes] | None):
    """Fail closed if a transcript was replaced while the Agent was running."""
    try:
        with path.open("rb") as stream:
            stat = path.stat()
            offset = 0
            if before is not None:
                device, inode, offset, prefix = before
                if (stat.st_dev, stat.st_ino) != (device, inode) or stat.st_size < offset:
                    return [], "transcript_replaced"
                if stream.read(len(prefix)) != prefix:
                    return [], "transcript_replaced"
            if stat.st_size - offset > _MAX_TRACE_BYTES:
                return [], "transcript_too_large"
            stream.seek(offset)
            raw = stream.read(_MAX_TRACE_BYTES + 1)
    except OSError:
        return [], "transcript_unavailable"
    records = []
    malformed = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, ValueError):
            malformed += 1
            continue
        if isinstance(value, dict):
            records.append(value)
    if malformed and not records:
        return [], "invalid_transcript"
    return records, ""


class _Catalog:
    """Resolve only files from the explicitly supplied Easel Skill directory."""

    def __init__(self, skills_root: Path):
        self.root = Path(skills_root).resolve()
        self.skill_files: dict[Path, str] = {}
        self.aliases: dict[str, Path] = {}
        self.scripts: set[Path] = set()
        if not self.root.is_dir():
            return
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(self.root):
                continue
            if path.name == "SKILL.md" and _SAFE_NAME.fullmatch(path.parent.name):
                self.skill_files[resolved] = path.parent.name
            if path.suffix.lower() in _SCRIPT_SUFFIXES:
                self.scripts.add(resolved)
            relative = path.relative_to(self.root).as_posix()
            variants = {relative, "skills/" + relative, "workspace/skills/" + relative}
            if relative.startswith("openclaw/"):
                short = relative[len("openclaw/"):]
                variants.update({short, "skills/" + short, "workspace/skills/" + short})
            # Callers may supply skills/openclaw rather than its parent.
            elif self.root.name == "openclaw":
                variants.update({"skills/openclaw/" + relative, "openclaw/" + relative})
            for alias in variants:
                self.aliases[alias] = resolved

    def resolve(self, value: Any) -> Path | None:
        if not isinstance(value, str) or not value or "\x00" in value:
            return None
        path = Path(value)
        if ".." in path.parts:
            return None
        if path.is_absolute():
            try:
                resolved = path.resolve()
            except OSError:
                return None
            return resolved if resolved.is_relative_to(self.root) else None
        return self.aliases.get(path.as_posix())

    def skill(self, value: Any) -> tuple[str, Path] | None:
        path = self.resolve(value)
        if path in self.skill_files:
            return self.skill_files[path], path
        return None

    def script(self, value: Any) -> str | None:
        path = self.resolve(value)
        return path.name if path in self.scripts else None


def _arguments(call: dict) -> dict:
    value = call.get("arguments", call.get("input", {}))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _leaf_tool(name: str) -> str:
    return name.rsplit("__", 1)[-1].rsplit(".", 1)[-1].lower()


def _read_paths(args: dict) -> list[str]:
    paths = [args.get(key) for key in ("path", "file_path", "filePath")]
    if isinstance(args.get("paths"), list):
        paths.extend(args["paths"])
    return [path for path in paths if isinstance(path, str)]


def _invoked_scripts(args: dict, catalog: _Catalog) -> list[str]:
    command = args.get("command", args.get("cmd"))
    if isinstance(command, list):
        segments = [command]
    elif isinstance(command, str):
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
            lexer.whitespace_split = True
            segments: list[list[str]] = [[]]
            for token in lexer:
                if token and set(token) <= set(";&|"):
                    segments.append([])
                else:
                    segments[-1].append(token)
        except ValueError:
            return []
    else:
        return []
    found = []
    for tokens in segments:
        if not tokens or not all(isinstance(token, str) for token in tokens):
            continue
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens = tokens[1:]
        if not tokens:
            continue
        executable = Path(tokens[0]).name
        candidate = tokens[0]
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?|node|bash|sh|zsh", executable):
            # -c/-m execute arbitrary code/modules, not a recorded script file.
            if any(token in {"-c", "-m", "--eval", "-e"} for token in tokens[1:]):
                continue
            candidate = next((token for token in tokens[1:] if not token.startswith("-")), "")
        script = catalog.script(candidate)
        if script and script not in found:
            found.append(script)
    return found


def _result_status(message: dict) -> str:
    details = message.get("details") if isinstance(message.get("details"), dict) else {}
    if message.get("isError") is True or message.get("is_error") is True:
        return "failed"
    if str(message.get("status", details.get("status", ""))).lower() in {"error", "failed", "blocked", "cancelled"}:
        return "failed"
    exit_code = details.get("exitCode", details.get("exit_code"))
    if isinstance(exit_code, int) and exit_code != 0:
        return "failed"
    return "succeeded"


def _trace(records: list[dict], catalog: _Catalog) -> dict[str, Any]:
    calls: list[dict] = []
    results: dict[str, str] = {}
    for record in records:
        message = record.get("message", record)
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role in {"toolResult", "tool", "tool_result"}:
            call_id = message.get("toolCallId", message.get("tool_call_id", message.get("tool_use_id")))
            if isinstance(call_id, str):
                results[call_id] = _result_status(message)
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_result":
                call_id = item.get("tool_use_id")
                if isinstance(call_id, str):
                    results[call_id] = _result_status(item)
            elif role == "assistant" and item.get("type") in {"toolCall", "tool_use"}:
                name = item.get("name")
                if isinstance(name, str) and _SAFE_NAME.fullmatch(name):
                    calls.append(item)
    tools: list[str] = []
    tool_calls: list[dict] = []
    skill_paths: dict[str, Path] = {}
    scripts: list[dict] = []
    for call in calls:
        name = call["name"]
        if name not in tools:
            tools.append(name)
        status = results.get(call.get("id"), "unconfirmed")
        tool_calls.append({"tool": name, "status": status})
        args = _arguments(call)
        if _leaf_tool(name) in _READ_TOOLS and status == "succeeded":
            for path in _read_paths(args):
                matched = catalog.skill(path)
                if matched:
                    skill_paths[matched[0]] = matched[1]
        if _leaf_tool(name) in _EXEC_TOOLS:
            for script in _invoked_scripts(args, catalog):
                evidence = {"name": script, "status": status}
                if evidence not in scripts:
                    scripts.append(evidence)
    sources = []
    for name, path in skill_paths.items():
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        sources.append({"name": name, "sha256": digest})
    return {"source": "session_transcript", "available": True,
            "skills_read": list(skill_paths),
            "skill_paths": [path.relative_to(catalog.root).as_posix() for path in skill_paths.values()],
            "tools": tools, "tool_calls": tool_calls,
            "scripts": scripts, "skill_sources": sources}


def build_agent_runner(run_agent_sync: Callable, session_path_resolver: Callable[[str], Path], skills_root: Path):
    """Wrap the configured OpenClaw runner without trusting self-reported skills.

    ``session_path_resolver`` must use the same session key -> transcript UUID
    mapping as ``run_agent_sync``. A missing/unreadable transcript is represented
    explicitly; successful model text alone does not establish tool execution.
    """
    catalog = _Catalog(Path(skills_root))

    def run(prompt: str, timeout: int, session_id: str) -> dict[str, Any]:
        try:
            path = Path(session_path_resolver(session_id))
            before = _snapshot(path)
        except (OSError, TypeError, ValueError):
            path, before = None, None
        response = run_agent_sync(prompt, timeout, session_id=session_id)
        if path is None:
            trace = _unavailable("transcript_unavailable")
        else:
            records, reason = _new_records(path, before)
            trace = _unavailable(reason) if reason else _trace(records, catalog)
        return {"response": response, "trace": trace}

    return run
