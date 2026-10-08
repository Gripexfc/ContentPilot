"""Bounded, tool-free text generation for the writing stages.

The research stages need the OpenClaw session runner because they may use the
configured research skills.  Writing stages only need a model response.  This
module talks to the already selected provider directly, with no tool schema,
no agent session, and one hard deadline around the whole request.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

try:  # Imported at module load so a missing optional dependency fails clearly.
    import httpx
except ImportError:  # pragma: no cover - exercised only in minimal installs
    httpx = None  # type: ignore[assignment]


DEFAULT_TOTAL_TIMEOUT = 180.0
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 120.0
_WRITE_TIMEOUT = 20.0
_POOL_TIMEOUT = 5.0


def _default_config_path() -> Path:
    runtime_root = os.environ.get("CREATOROS_RUNTIME_ROOT", "").strip()
    if runtime_root:
        return Path(runtime_root).expanduser() / "openclaw" / "openclaw.json"
    # creatoros/services/text_generation.py -> project root
    return Path(__file__).resolve().parents[2] / "runtime" / "openclaw" / "openclaw.json"


def _provider_config(config_path: Path) -> tuple[str, str, str, str]:
    """Return (kind, base_url, api_key, model) for the configured primary.

    Reading configuration remains server-side.  Error messages intentionally do
    not include a URL, key, request body, or provider response body.
    """
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("model provider configuration is unavailable") from exc

    primary = str(
        data.get("agents", {}).get("defaults", {}).get("model", {}).get("primary")
        or ""
    ).strip()
    if "/" not in primary:
        raise RuntimeError("model provider is not configured")
    provider_name, configured_model = (part.strip() for part in primary.split("/", 1))
    providers = data.get("models", {}).get("providers", {})
    provider = providers.get(provider_name) if isinstance(providers, dict) else None
    if not isinstance(provider, dict):
        raise RuntimeError("model provider is not configured")

    base_url = str(provider.get("baseUrl") or "").strip().rstrip("/")
    api_key = str(provider.get("apiKey") or "").strip()
    if not base_url or not api_key or api_key.startswith("${"):
        raise RuntimeError("model provider authentication is not configured")

    models = provider.get("models")
    model_rows = models if isinstance(models, list) else []
    first_model = model_rows[0] if model_rows else {}
    if not isinstance(first_model, dict):
        first_model = {}
    available_ids = {
        str(row.get("id") or "").strip()
        for row in model_rows
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    selected_model = next(
        (row for row in model_rows if isinstance(row, dict) and str(row.get("id") or "").strip() == configured_model),
        first_model,
    )
    model = configured_model if configured_model in available_ids else str(first_model.get("id") or configured_model).strip()
    if not model:
        raise RuntimeError("model provider is not configured")
    api = str(selected_model.get("api") or provider.get("api") or "").strip().lower()
    kind = "anthropic" if api in {"anthropic", "anthropic-messages", "messages"} else "openai"
    return kind, base_url, api_key, model


def _endpoint(kind: str, base_url: str) -> str:
    """Build the endpoint used by the existing provider settings contract."""
    if kind == "anthropic":
        return base_url if base_url.endswith("/messages") else (
            base_url + "/messages" if base_url.endswith("/v1") else base_url + "/v1/messages"
        )
    return base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"


def _text_from_openai(body: Any) -> str:
    choices = body.get("choices") if isinstance(body, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") if isinstance(item, dict) else str(item)
            for item in content
        ).strip()
    return ""


def _text_from_anthropic(body: Any) -> str:
    content = body.get("content") if isinstance(body, dict) else None
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") if isinstance(item, dict) else str(item)
            for item in content
        ).strip()
    return ""


def _raise_http_failure(status: int) -> None:
    if status in (401, 403):
        raise RuntimeError("model authentication failed (HTTP 401/403)")
    if status == 402:
        raise RuntimeError("model account balance or quota is insufficient (HTTP 402)")
    if status == 429:
        raise RuntimeError("model request rate limited (HTTP 429)")
    if status == 404:
        raise RuntimeError("model endpoint or model is unavailable (HTTP 404)")
    if status >= 500:
        raise RuntimeError("model provider temporarily unavailable")
    raise RuntimeError(f"model request rejected (HTTP {status})")


def _stream_delta(kind: str, payload: Any, on_delta: Callable[[str], None]) -> str:
    """Extract one provider SSE payload and forward any text delta.

    Providers use slightly different envelopes even when they expose the
    OpenAI-compatible endpoint.  Keep this parser deliberately small and
    ignore role/finish/reasoning-only events; the caller owns the accumulated
    text and the workflow checkpoint.
    """
    if not isinstance(payload, dict):
        return ""
    text = ""
    if kind == "anthropic":
        delta = payload.get("delta")
        if isinstance(delta, dict):
            value = delta.get("text")
            if isinstance(value, str):
                text = value
        if not text:
            # A few compatible gateways wrap Anthropic events in content.
            content = payload.get("content")
            if isinstance(content, list):
                text = "".join(
                    str(item.get("text") or "")
                    for item in content
                    if isinstance(item, dict)
                )
    else:
        choices = payload.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else {}
        delta = first.get("delta", {}) if isinstance(first, dict) else {}
        if isinstance(delta, dict):
            value = delta.get("content")
            if isinstance(value, str):
                text = value
            elif isinstance(value, list):
                text = "".join(
                    str(item.get("text") or "")
                    if isinstance(item, dict) else str(item)
                    for item in value
                )
    if text:
        on_delta(text)
    return text


def _stream_response(
    response: Any,
    kind: str,
    on_delta: Callable[[str], None],
    deadline: float,
) -> str:
    """Consume an SSE response and return exactly the text sent to callback."""
    chunks: list[str] = []
    data_lines: list[str] = []
    saw_done = False
    for raw_line in response.iter_lines():
        if time.monotonic() > deadline:
            raise RuntimeError("model request timed out")
        line = raw_line.decode("utf-8", "replace") if isinstance(raw_line, bytes) else str(raw_line)
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
        if line.strip():
            continue
        if not data_lines:
            continue
        data = "\n".join(data_lines).strip()
        data_lines = []
        if data == "[DONE]":
            saw_done = True
            break
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            continue
        chunk = _stream_delta(kind, payload, on_delta)
        if chunk:
            chunks.append(chunk)
    # Some test doubles and gateways omit the blank line after the last data
    # frame.  Flush it once the iterator ends without treating an empty stream
    # as successful.
    if data_lines and not saw_done:
        data = "\n".join(data_lines).strip()
        if data and data != "[DONE]":
            try:
                chunk = _stream_delta(kind, json.loads(data), on_delta)
            except (TypeError, ValueError):
                chunk = ""
            if chunk:
                chunks.append(chunk)
    text = "".join(chunks)
    if not text:
        raise RuntimeError("model returned an empty response")
    return text


def direct_text_generation(
    prompt: str,
    *,
    config_path: str | Path | None = None,
    timeout: float = DEFAULT_TOTAL_TIMEOUT,
    stage: str = "compose",
    session_id: str = "",
    on_delta: Callable[[str], None] | None = None,
) -> str:
    """Generate one text response without OpenClaw tools or agent sessions.

    ``session_id`` is accepted for the workflow runner's interface and audit
    correlation, but is never sent to the model provider.  When ``on_delta`` is
    supplied, the same request uses provider SSE and forwards each text delta
    while still returning the complete response.  The hard timeout is measured
    around the complete HTTP call so a slow provider cannot leave a writing
    stage waiting indefinitely.
    """
    del stage, session_id
    if not isinstance(prompt, str) or not prompt.strip():
        raise RuntimeError("model prompt is empty")
    if httpx is None:
        raise RuntimeError("text generation transport is unavailable")

    kind, base_url, api_key, model = _provider_config(Path(config_path) if config_path else _default_config_path())
    endpoint = _endpoint(kind, base_url)
    if kind == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 8192,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
            "stream": bool(on_delta),
        }
        parse = _text_from_anthropic
    else:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8192,
            "temperature": 0.2,
            "stream": bool(on_delta),
        }
        parse = _text_from_openai

    started = time.monotonic()
    # A single request has no retry loop, and every individual phase is below
    # the stage deadline.  This keeps normal long-form output viable while
    # bounding the complete call well below the workflow's 180-second cap.
    total_timeout = max(1.0, float(timeout))
    connect_timeout = min(_CONNECT_TIMEOUT, total_timeout * 0.15)
    write_timeout = min(_WRITE_TIMEOUT, total_timeout * 0.10)
    pool_timeout = min(_POOL_TIMEOUT, total_timeout * 0.05)
    read_timeout = max(0.5, total_timeout - connect_timeout - write_timeout - pool_timeout)
    request_timeout = httpx.Timeout(
        connect=connect_timeout,
        read=min(_READ_TIMEOUT, read_timeout),
        write=write_timeout,
        pool=pool_timeout,
    )
    try:
        with httpx.Client(timeout=request_timeout, follow_redirects=False) as client:
            if on_delta is None:
                response = client.post(endpoint, headers=headers, json=payload)
            else:
                with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    if response.status_code < 200 or response.status_code >= 300:
                        _raise_http_failure(response.status_code)
                    content_type = str(getattr(response, "headers", {}).get("content-type", "")).lower()
                    if "text/event-stream" in content_type:
                        text = _stream_response(response, kind, on_delta, started + max(1.0, float(timeout)))
                    else:
                        # A configured OpenAI-compatible gateway may ignore
                        # stream=true and return a normal JSON envelope.  Do
                        # not make a second model request; emit that response
                        # once so the UI still receives a complete result.
                        try:
                            body = response.json()
                        except ValueError as exc:
                            raise RuntimeError("model returned an invalid response") from exc
                        text = parse(body)
                        if not text:
                            raise RuntimeError("model returned an empty response")
                        on_delta(text)
                    if time.monotonic() - started > max(1.0, float(timeout)):
                        raise RuntimeError("model request timed out")
                    return text
    except httpx.TimeoutException as exc:
        raise RuntimeError("model request timed out") from exc
    except httpx.RequestError as exc:
        raise RuntimeError("model provider connection failed") from exc
    if time.monotonic() - started > max(1.0, float(timeout)):
        raise RuntimeError("model request timed out")
    if response.status_code < 200 or response.status_code >= 300:
        _raise_http_failure(response.status_code)
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("model returned an invalid response") from exc
    text = parse(body)
    if not text:
        raise RuntimeError("model returned an empty response")
    return text
