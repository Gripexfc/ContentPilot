"""Regression tests for the local-only write guard used by model settings."""

import io
import json
import urllib.error

from fastapi.testclient import TestClient

from creatoros.api.easel_bridge import _module as upstream


def test_loopback_origin_allows_vite_fallback_port():
    assert upstream._loopback_origin("http://127.0.0.1:5175") is True
    assert upstream._loopback_origin("http://localhost:5174") is True
    assert upstream._loopback_origin("http://[::1]:4173") is True


def test_loopback_origin_rejects_external_origin():
    assert upstream._loopback_origin("https://example.com") is False
    assert upstream._loopback_origin("http://192.168.1.12:5175") is False
    assert upstream._loopback_origin("not-an-origin") is False


def test_model_write_from_vite_fallback_origin_is_not_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(upstream, "_read_env", lambda: {})
    monkeypatch.setattr(upstream, "PROJECT_ROOT", tmp_path)
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/settings/models/selftest",
            json={"channel": "chat"},
            headers={"Origin": "http://127.0.0.1:5175"},
        )
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_model_write_from_external_origin_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(upstream, "_read_env", lambda: {})
    monkeypatch.setattr(upstream, "PROJECT_ROOT", tmp_path)
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/settings/models/selftest",
            json={"channel": "chat"},
            headers={"Origin": "https://example.com"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "仅允许从本机工作台操作。"


def test_model_selftest_uses_generation_probe_and_classifies_billing(monkeypatch):
    class BillingOpener:
        def open(self, request, timeout):
            assert request.full_url == "https://api.deepseek.com/chat/completions"
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["model"] == "deepseek-v4-pro"
            assert payload["max_tokens"] == 1
            raise urllib.error.HTTPError(
                request.full_url, 402, "billing", {}, io.BytesIO(b"provider detail"))

    monkeypatch.setattr(upstream, "_read_env", lambda: {
        "OPENAI_BASE_URL": "https://api.deepseek.com",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "deepseek-v4-pro",
    })
    monkeypatch.setattr(upstream, "_ssrf_safe", lambda _url: True)
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda _handler: BillingOpener())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/settings/models/selftest", json={"channel": "chat"},
                               headers={"Origin": "http://127.0.0.1:5173"})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["ok"] is False
    assert result["detail"] == "模型账户余额或额度不足"


def test_model_selftest_classifies_aliyun_arrearage_body(monkeypatch):
    class ArrearageOpener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 400, "bad request", {},
                io.BytesIO(b'{"code":"Arrearage","message":"Access denied, account overdue-payment"}'))

    monkeypatch.setattr(upstream, "_read_env", lambda: {
        "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "qwen3.8-flash",
    })
    monkeypatch.setattr(upstream, "_ssrf_safe", lambda _url: True)
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda _handler: ArrearageOpener())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/settings/models/selftest", json={"channel": "chat"},
                               headers={"Origin": "http://127.0.0.1:5173"})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["ok"] is False
    assert result["detail"] == "模型账户欠费或账户状态异常，请到服务商控制台处理欠费并开启可用额度"


def test_model_selftest_includes_selected_custom_primary_provider(monkeypatch, tmp_path):
    class SuccessResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class SuccessOpener:
        def open(self, request, timeout):
            assert request.full_url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["model"] == "qwen3.8-flash"
            assert request.headers["Authorization"] == "Bearer custom-test-key"
            return SuccessResponse()

    config_dir = tmp_path / "openclaw"
    config_dir.mkdir()
    (config_dir / "openclaw.json").write_text(json.dumps({
        "agents": {"defaults": {"model": {"primary": "aliyun/qwen3.8-flash"}}},
        "models": {"providers": {"aliyun": {
            "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "apiKey": "custom-test-key",
            "models": [{"id": "qwen3.8-flash", "api": "openai-completions"}],
        }}},
    }))
    monkeypatch.setattr(upstream, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(upstream, "_read_env", lambda: {})
    monkeypatch.setattr(upstream, "_ssrf_safe", lambda _url: True)
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda _handler: SuccessOpener())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post("/api/settings/models/selftest", json={"channel": "chat"},
                               headers={"Origin": "http://127.0.0.1:5173"})
    assert response.status_code == 200
    assert response.json()["results"] == [{
        "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "ok": True,
        "ms": response.json()["results"][0]["ms"],
    }]


class _DiscoveryResponse:
    status = 200

    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return self.payload


def test_model_discovery_fetches_and_deduplicates_remote_models(monkeypatch):
    requests = []

    class DiscoveryOpener:
        def open(self, request, timeout):
            requests.append((request, timeout))
            return _DiscoveryResponse(json.dumps({
                "data": [
                    {"id": "model-b"},
                    {"id": "model-a"},
                    {"id": "model-b"},
                    {"object": "model"},
                ],
            }).encode())

    monkeypatch.setattr(upstream, "_saved_model_discovery_target",
                        lambda _slot, _name: ("https://api.example.com/v1", "secret-model-key"))
    monkeypatch.setattr(upstream, "_ssrf_safe", lambda _url: True)
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda *_args, **_kwargs: DiscoveryOpener())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/settings/models/discover",
            json={"slot": "custom", "name": "snode", "baseUrl": "https://api.example.com/v1"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["models"] == ["model-b", "model-a"]
    assert response.json()["source"] == "remote"
    assert "secret-model-key" not in response.text
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == "https://api.example.com/v1/models"
    assert request.headers["Authorization"] == "Bearer secret-model-key"
    assert timeout == 15


def test_model_discovery_blocks_private_target_before_request(monkeypatch):
    attempted = []

    class ShouldNotOpen:
        def open(self, *_args, **_kwargs):
            attempted.append(True)
            raise AssertionError("private model target must not be requested")

    monkeypatch.setattr(upstream, "_saved_model_discovery_target",
                        lambda _slot, _name: ("http://169.254.169.254/latest", "secret-model-key"))
    monkeypatch.setattr(upstream, "_ssrf_safe", lambda _url: False)
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda *_args, **_kwargs: ShouldNotOpen())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/settings/models/discover",
            json={"slot": "custom", "name": "snode", "baseUrl": "http://169.254.169.254/latest"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["models"] == []
    assert body["available"] is False
    assert body["source"] == "none"
    assert "secret-model-key" not in response.text
    assert not attempted


def test_model_discovery_returns_non_secret_failure_for_provider_error(monkeypatch):
    class FailingOpener:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(
                request.full_url, 401, "unauthorized", {}, io.BytesIO(b"secret-model-key"))

    monkeypatch.setattr(upstream, "_saved_model_discovery_target",
                        lambda _slot, _name: ("https://api.example.com/v1", "secret-model-key"))
    monkeypatch.setattr(upstream, "_ssrf_safe", lambda _url: True)
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda *_args, **_kwargs: FailingOpener())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/settings/models/discover",
            json={"slot": "custom", "name": "snode", "baseUrl": "https://api.example.com/v1"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["models"] == []
    assert body["available"] is False
    assert body["source"] == "none"
    assert "HTTP 401" in body["detail"]
    assert "secret-model-key" not in response.text


def test_model_discovery_does_not_send_stored_key_to_different_endpoint(monkeypatch):
    attempted = []

    class ShouldNotOpen:
        def open(self, *_args, **_kwargs):
            attempted.append(True)
            raise AssertionError("a draft endpoint must not receive the stored provider key")

    monkeypatch.setattr(upstream, "_saved_model_discovery_target",
                        lambda _slot, _name: ("https://saved.example.com/v1", "secret-model-key"))
    monkeypatch.setattr(upstream.urllib.request, "build_opener", lambda *_args, **_kwargs: ShouldNotOpen())
    with TestClient(upstream.app, base_url="http://127.0.0.1:8000") as client:
        response = client.post(
            "/api/settings/models/discover",
            json={"slot": "custom", "name": "snode", "baseUrl": "https://other.example.com/v1"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["models"] == []
    assert body["available"] is False
    assert body["source"] == "none"
    assert "请先保存" in body["detail"]
    assert "secret-model-key" not in response.text
    assert not attempted
