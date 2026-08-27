"""_docs 聚合端点测试（integration，需 DB）。"""

import pytest

from apps.core.openapi import renderer
from apps.core.openapi.testing import bearer, create_api_tenant

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

DOCS_URL = "/openapi/v1/_docs"


def test_docs_requires_credential(client):
    resp = client.get(DOCS_URL)
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID"


def test_docs_lists_internal_endpoints_with_schema(client):
    _, token = create_api_tenant(1)
    resp = client.get(DOCS_URL, **bearer(token))
    assert resp.status_code == 200
    services = {s["name"]: s for s in resp.json()["data"]["services"]}

    patch_service = services["patch-mgmt"]
    assert patch_service["kind"] == "internal"
    endpoint = next(
        e for e in patch_service["endpoints"] if e["path"] == "patch-mgmt/module-data"
    )
    assert endpoint["method"] == "GET"
    assert endpoint["inject"] == "team_list"
    schema = endpoint["request_schema"]
    assert schema["module"]["required"] is True
    assert schema["module"]["choices"] == ["patch_target"]
    assert schema["group_id"]["type"] == "integer"
    assert schema["page"]["required"] is False
    # 身份字段绝不出现在对外 schema 中
    assert "team" not in schema


def test_docs_includes_external_services(client, monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_ITSM_SECRET", "s3cret")
    monkeypatch.setattr(
        "apps.core.openapi.renderer.fetch_entries",
        lambda: {
            "itsm": {
                "schema_version": 1,
                "type": "http",
                "base_url": "http://itsm-svc:8000",
                "auth_mode": "trusted-header",
                "shared_secret_ref": "env:TEST_ITSM_SECRET",
                "doc_url": "http://itsm-svc:8000/swagger.json",
                "enabled": True,
            }
        },
    )
    renderer.refresh_snapshot()

    _, token = create_api_tenant(1)
    resp = client.get(DOCS_URL, **bearer(token))
    services = {s["name"]: s for s in resp.json()["data"]["services"]}
    assert services["itsm"]["kind"] == "external"
    assert services["itsm"]["doc_url"] == "http://itsm-svc:8000/swagger.json"
