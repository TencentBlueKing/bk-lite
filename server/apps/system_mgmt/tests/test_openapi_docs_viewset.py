"""系统管理接口文档页：View 权限门 + 与 `_docs` 同源目录。"""

import json
import types
from pathlib import Path

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.openapi import renderer
from apps.core.openapi.testing import bearer, create_api_tenant
from apps.system_mgmt.viewset.openapi_docs_viewset import OpenAPIDocsViewSet, build_docs_catalog

factory = APIRequestFactory()

pytestmark = [pytest.mark.django_db]


def _user(perms, is_superuser=False):
    return types.SimpleNamespace(
        username="docs-viewer",
        domain="domain.com",
        locale="en",
        is_superuser=is_superuser,
        is_authenticated=True,
        permission={"system-manager": set(perms)},
    )


def _list(user):
    view = OpenAPIDocsViewSet.as_view({"get": "list"})
    request = factory.get("/system_mgmt/openapi_docs/")
    force_authenticate(request, user=user)
    return view(request)


def _json(response):
    return json.loads(response.content)


def test_system_manager_setting_includes_openapi_docs_view_only():
    payload = json.loads(Path("support-files/system_mgmt/menus/system-manager.json").read_text(encoding="utf-8"))
    setting = next(menu for menu in payload["menus"] if menu["name"] == "Setting")
    child = next(item for item in setting["children"] if item["id"] == "openapi_docs")
    assert child["operation"] == ["View"]
    for role in payload["roles"]:
        if role["name"] == "admin":
            continue
        assert not any(name.startswith("openapi_docs-") for name in role["menus"])


def test_list_denied_without_view_permission():
    response = _list(_user(set()))
    assert response.status_code == 403


def test_list_returns_internal_schema_with_view_permission():
    response = _list(_user({"openapi_docs-View"}))
    assert response.status_code == 200
    body = _json(response)
    assert body["result"] is True
    services = {item["name"]: item for item in body["data"]["services"]}
    patch_service = services["patch-mgmt"]
    assert patch_service["kind"] == "internal"
    endpoint = next(item for item in patch_service["endpoints"] if item["path"] == "patch-mgmt/module-data")
    assert endpoint["method"] == "GET"
    assert "team" not in endpoint["request_schema"]


def test_list_matches_live_gateway_docs(client):
    _, token = create_api_tenant(1)
    docs_response = client.get("/openapi/v1/_docs", **bearer(token))
    assert docs_response.status_code == 200
    console = _json(_list(_user({"openapi_docs-View"})))
    assert console["data"] == docs_response.json()["data"]


def test_external_projection_omits_secrets_and_paths(monkeypatch):
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
                "paths": ["/tickets/*"],
                "doc_url": "http://itsm-svc:8000/swagger.json",
                "enabled": True,
            }
        },
    )
    renderer.refresh_snapshot()

    catalog = build_docs_catalog()
    itsm = next(item for item in catalog["services"] if item["name"] == "itsm")
    assert itsm == {"name": "itsm", "kind": "external", "doc_url": "http://itsm-svc:8000/swagger.json"}

    raw = json.dumps(_json(_list(_user({"openapi_docs-View"}))))
    assert "s3cret" not in raw
    assert "shared_secret" not in raw
    assert "/tickets/*" not in raw
