def test_mock_connector_state_machine_and_retry(client):
    response = client.get("/api/v1/connectors")
    assert response.status_code == 200
    assert {item["state"] for item in response.json()} == {"not_configured"}

    assert client.post("/api/v1/connectors/wechat-oa/connect").status_code == 409
    assert client.post("/api/v1/connectors/wechat-oa/configure").json()["state"] == "configured"
    assert client.post("/api/v1/connectors/wechat-oa/connect").json()["state"] == "connected"
    assert client.post("/api/v1/connectors/wechat-oa/read").json()["state"] == "read_succeeded"
    failed = client.post("/api/v1/connectors/wechat-oa/submit", json={"simulate_failure": True})
    assert failed.status_code == 200
    assert failed.json()["state"] == "failed"
    assert failed.json()["last_error_code"] == "mock_submit_failed"
    retried = client.post("/api/v1/connectors/wechat-oa/submit", json={"simulate_failure": False})
    assert retried.json()["state"] == "submit_succeeded"
    assert retried.json()["last_error"] is None


def test_mock_connector_requires_read_and_deduplicates_success(client):
    assert client.post("/api/v1/connectors/wechat-oa/configure").status_code == 200
    assert client.post("/api/v1/connectors/wechat-oa/connect").status_code == 200
    blocked = client.post("/api/v1/connectors/wechat-oa/submit", json={})
    assert blocked.status_code == 409
    assert client.post("/api/v1/connectors/wechat-oa/read").status_code == 200
    first = client.post("/api/v1/connectors/wechat-oa/submit", json={})
    second = client.post("/api/v1/connectors/wechat-oa/submit", json={})
    assert first.status_code == second.status_code == 200
    assert first.json()["state"] == second.json()["state"] == "submit_succeeded"
    assert second.json()["last_operation"] == "submit"


def test_browser_adapter_never_claims_connection_without_external_session(app_settings):
    from fastapi.testclient import TestClient
    from creatoros.api.app import create_app

    from dataclasses import replace
    browser_settings = replace(app_settings, wechat_adapter="browser")
    with TestClient(create_app(browser_settings)) as browser_client:
        listed = browser_client.get("/api/v1/connectors").json()
        wechat = next(item for item in listed if item["connector_key"] == "wechat-oa")
        assert wechat["adapter_kind"] == "browser"
        assert wechat["state"] == "not_configured"
        configured = browser_client.post("/api/v1/connectors/wechat-oa/configure").json()
        assert configured["state"] in {"configured", "unsupported"}
