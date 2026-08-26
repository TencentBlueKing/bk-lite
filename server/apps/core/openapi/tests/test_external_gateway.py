"""外部服务链路测试（integration，需 DB，无需真实 NATS）。

覆盖 spec.md「验证」节：provider 端点保护、ForwardAuth 与 invoke 的
401 逐字段同构、required_roles 空数组语义、身份头注入。
"""

import pytest

from apps.core.openapi import renderer
from apps.core.openapi.testing import bearer, create_api_tenant

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

AUTH_URL = "/openapi/v1/_auth"
PROVIDER_URL = "/openapi/v1/_provider/traefik"

SAMPLE_ENTRY = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "auth_mode": "trusted-header",
    "shared_secret_ref": "env:TEST_ITSM_SECRET",
    "required_roles": [],
    "enabled": True,
}


@pytest.fixture
def external_env(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_ITSM_SECRET", "s3cret")
    monkeypatch.setenv("OPENAPI_PROVIDER_TOKEN", "provider-token")


@pytest.fixture
def registered_itsm(external_env, monkeypatch):
    monkeypatch.setattr(
        "apps.core.openapi.renderer.fetch_entries", lambda: {"itsm": dict(SAMPLE_ENTRY)}
    )
    renderer.refresh_snapshot()


# ---------- provider 端点 ----------


def test_provider_requires_configured_token(client, monkeypatch):
    monkeypatch.delenv("OPENAPI_PROVIDER_TOKEN", raising=False)
    resp = client.get(PROVIDER_URL)
    assert resp.status_code == 503


def test_provider_rejects_wrong_token(client, external_env):
    resp = client.get(PROVIDER_URL, HTTP_X_PROVIDER_TOKEN="wrong")
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID"


def test_provider_returns_native_traefik_config(client, registered_itsm):
    resp = client.get(PROVIDER_URL, HTTP_X_PROVIDER_TOKEN="provider-token")
    assert resp.status_code == 200
    config = resp.json()
    assert "openapi-v1-itsm" in config["http"]["routers"]
    assert (
        config["http"]["middlewares"]["openapi-itsm-inject"]["headers"][
            "customRequestHeaders"
        ]["X-BK-Gateway-Auth"]
        == "s3cret"
    )


def test_provider_falls_back_to_snapshot_when_kv_down(client, registered_itsm, monkeypatch):
    monkeypatch.setattr("apps.core.openapi.renderer.fetch_entries", lambda: None)
    resp = client.get(PROVIDER_URL, HTTP_X_PROVIDER_TOKEN="provider-token")
    assert resp.status_code == 200
    assert "openapi-v1-itsm" in resp.json()["http"]["routers"]


# ---------- ForwardAuth ----------


def test_forward_auth_401_identical_to_invoke_401(client):
    resp_auth = client.get(AUTH_URL)
    resp_invoke = client.get("/openapi/v1/patch-mgmt/module-data")
    assert resp_auth.status_code == resp_invoke.status_code == 401
    assert resp_auth.json() == resp_invoke.json()


def test_forward_auth_unknown_service_404(client, registered_itsm):
    _, token = create_api_tenant(1)
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/nonexistent/x",
        **bearer(token),
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_forward_auth_missing_forwarded_uri_404(client, registered_itsm):
    _, token = create_api_tenant(1)
    resp = client.get(AUTH_URL, **bearer(token))
    assert resp.status_code == 404


def test_forward_auth_empty_required_roles_allows_any_authenticated(
    client, registered_itsm
):
    """required_roles: [] 语义冻结：放行任意已认证身份。"""
    _, token = create_api_tenant(9)
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create",
        **bearer(token),
    )
    assert resp.status_code == 200
    assert resp["X-BK-Team"] == "9"
    assert resp["X-BK-User"].endswith("@domain.com")


def test_forward_auth_required_roles_rejects_without_role(
    client, external_env, monkeypatch
):
    entry = dict(SAMPLE_ENTRY, required_roles=["itsm--operator"])
    monkeypatch.setattr(
        "apps.core.openapi.renderer.fetch_entries", lambda: {"itsm": entry}
    )
    renderer.refresh_snapshot()

    _, token = create_api_tenant(9)
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create",
        **bearer(token),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "ROLE_REQUIRED"


def test_forward_auth_on_behalf_of_echoed_for_api_token(client, registered_itsm):
    _, token = create_api_tenant(9)
    resp = client.get(
        AUTH_URL,
        HTTP_X_FORWARDED_URI="/openapi/v1/itsm/tickets/create",
        HTTP_X_ON_BEHALF_OF="lisi@domain.com",
        **bearer(token),
    )
    assert resp.status_code == 200
    assert resp["X-On-Behalf-Of"] == "lisi@domain.com"


# ---------- _me 合并外部 service ----------


def test_me_includes_external_services(client, registered_itsm):
    _, token = create_api_tenant(3)
    resp = client.get("/openapi/v1/_me", **bearer(token))
    assert resp.status_code == 200
    services = {s["name"]: s["kind"] for s in resp.json()["data"]["services"]}
    assert services.get("itsm") == "external"
    assert services.get("patch-mgmt") == "internal"
