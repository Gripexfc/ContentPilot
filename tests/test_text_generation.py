import json

import pytest

from creatoros.services import text_generation as tg


def write_config(path, *, api="openai-completions", base="https://example.test/v1"):
    path.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"model": {"primary": "demo/model-1"}}},
                "models": {
                    "providers": {
                        "demo": {
                            "baseUrl": base,
                            "apiKey": "server-side-secret",
                            "models": [{"id": "model-1", "api": api}],
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_provider_config_and_endpoints(tmp_path):
    config = tmp_path / "openclaw.json"
    write_config(config)
    kind, base, key, model = tg._provider_config(config)
    assert (kind, base, model) == ("openai", "https://example.test/v1", "model-1")
    assert key == "server-side-secret"
    assert tg._endpoint(kind, base).endswith("/v1/chat/completions")
    assert tg._endpoint("anthropic", "https://example.test/v1").endswith("/v1/messages")


def test_openai_generation_sends_one_tool_free_request(tmp_path, monkeypatch):
    config = tmp_path / "openclaw.json"
    write_config(config)
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "完成的母稿"}}]}

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, endpoint, *, headers, json):
            calls.append((endpoint, headers, json))
            return Response()

    monkeypatch.setattr(tg.httpx, "Client", Client)
    assert tg.direct_text_generation("写一篇稿", config_path=config) == "完成的母稿"
    endpoint, headers, payload = calls[0]
    assert endpoint.endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer server-side-secret"
    assert payload["messages"] == [{"role": "user", "content": "写一篇稿"}]
    assert "tools" not in payload
    assert payload["stream"] is False


def test_anthropic_response_is_normalized(tmp_path, monkeypatch):
    config = tmp_path / "openclaw.json"
    write_config(config, api="anthropic-messages", base="https://example.test")

    class Response:
        status_code = 200

        def json(self):
            return {"content": [{"type": "text", "text": "第一段"}, {"text": "第二段"}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, endpoint, **_kwargs):
            assert endpoint.endswith("/v1/messages")
            return Response()

    monkeypatch.setattr(tg.httpx, "Client", Client)
    assert tg.direct_text_generation("写作", config_path=config) == "第一段第二段"


def test_http_failure_is_categorized_without_response_body(tmp_path, monkeypatch):
    config = tmp_path / "openclaw.json"
    write_config(config)

    class Response:
        status_code = 429

        def json(self):
            return {"error": "secret provider detail"}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(tg.httpx, "Client", Client)
    with pytest.raises(RuntimeError, match="rate limited") as error:
        tg.direct_text_generation("写作", config_path=config)
    assert "secret provider detail" not in str(error.value)


def test_openai_streaming_forwards_deltas_from_one_request(tmp_path, monkeypatch):
    config = tmp_path / "openclaw.json"
    write_config(config)
    calls = []
    received = []

    class Response:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        def iter_lines(self):
            yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "第一段"}}]})
            yield ''
            yield 'data: ' + json.dumps({"choices": [{"delta": {"content": "第二段"}}]})
            yield ''
            yield 'data: [DONE]'
            yield ''

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, method, endpoint, *, headers, json):
            calls.append((method, endpoint, headers, json))
            return ResponseContext(Response())

    class ResponseContext:
        def __init__(self, response):
            self.response = response

        def __enter__(self):
            return self.response

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(tg.httpx, "Client", Client)
    result = tg.direct_text_generation("写作", config_path=config, on_delta=received.append)
    assert result == "第一段第二段"
    assert received == ["第一段", "第二段"]
    assert len(calls) == 1
    assert calls[0][3]["stream"] is True
