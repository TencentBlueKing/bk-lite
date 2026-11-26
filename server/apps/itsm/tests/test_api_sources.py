"""网关目录与外部 API 的字段取数边界。"""

import json
from unittest.mock import Mock, patch

import pytest

from apps.core.openapi.identity import CallerIdentity
from apps.itsm.models.integration import Integration
from apps.itsm.services.form.fetch import field_safe, freeze_schema
from apps.itsm.services.integrations import execute, validate_config
from apps.itsm.tests.test_integrations import body, req
from apps.itsm.views.field_fetch import field_catalog
from apps.itsm.views.integrations import integrations

pytestmark = pytest.mark.django_db


def test_gateway_catalog_contains_unconfigured_query_endpoints():
    data = body(field_catalog(req(permissions=["form-Edit"])))
    assert len(data["gateways"]) > 5
    assert all(row["method"] in ["GET", "POST"] for row in data["gateways"])
    assert any(row["path"].startswith("itsm/") for row in data["gateways"])


def test_external_config_validation_and_secret_redaction():
    with patch("apps.itsm.services.external_api.SSRFValidator.validate"):
        result = body(
            integrations(
                req(
                    "post",
                    {
                        "name": "外部查询",
                        "kind": "api",
                        "config": {
                            "transport": "external",
                            "url": "https://api.example.com/items",
                            "method": "GET",
                            "token": "private-secret",
                            "request_schema": {"properties": {"keyword": {"type": "string"}}, "required": ["keyword"]},
                        },
                    },
                )
            )
        )
    assert result["config"]["token"] == "" and result["has_token"]
    item = Integration.objects.get(pk=result["id"])
    assert item.config["token"] != "private-secret"
    assert field_safe(item)
    with pytest.raises(ValueError, match="必填"):
        freeze_schema(
            {"fields": [{"key": "x", "type": "select", "fetch": {"source": "integration", "integration_id": item.id, "mode": "options"}}]},
            "domain.com",
        )


def test_external_execution_bounded_and_does_not_follow_redirects():
    item = Integration.objects.create(
        name="外部",
        kind="api",
        config={
            "transport": "external",
            "url": "https://api.example.com/items",
            "method": "GET",
            "request_schema": {"properties": {"q": {"type": "string"}}},
        },
    )
    response = Mock(status_code=200)
    response.iter_content.return_value = [b'[{"id":1,"name":"demo"}]']
    with patch("apps.itsm.services.external_api.safe_request", return_value=response) as http:
        result = execute(item, {"q": "demo"}, CallerIdentity("owner", "domain.com", "jwt"))
    assert result["status"] == "done" and result["output"][0]["id"] == 1
    assert http.call_args.kwargs["allow_redirects"] is False
    assert http.call_args.kwargs["params"] == {"q": "demo"}
    response.close.assert_called_once()
    response.iter_content.return_value = [b"x" * (1024 * 1024 + 1)]
    with patch("apps.itsm.services.external_api.safe_request", return_value=response):
        assert execute(item, {}, CallerIdentity("owner", "domain.com", "jwt"))["status"] == "failed"


def test_external_rejects_private_url_and_writes_not_for_fields():
    with pytest.raises(ValueError):
        validate_config("api", {"transport": "external", "url": "http://169.254.169.254/latest", "method": "GET"})
    assert not field_safe(Integration(kind="api", config={"transport": "external", "method": "DELETE"}))
    assert not field_safe(Integration(kind="api", config={"transport": "external", "method": "POST"}))


def test_gateway_binding_requires_edit_and_reuses_reference():
    from apps.itsm.views.field_fetch import field_gateway

    data = body(field_catalog(req(permissions=["form-Edit"])))
    gateway = next(g for g in data["gateways"] if g["path"].startswith("itsm/"))
    config = {k: gateway[k] for k in ["path", "method"]}
    assert field_gateway(req("post", config, ["form-View"])).status_code == 403
    first = body(field_gateway(req("post", config, ["form-Edit"])))
    second = body(field_gateway(req("post", config, ["form-Edit"])))
    assert first["id"] == second["id"]
    assert body(field_gateway(req("post", config, ["form-Edit"], domain="other")))["id"] != first["id"]


def test_seed_is_idempotent_and_domain_scoped():
    from django.core.management import call_command

    from apps.itsm.models import DataDictionary, DataTable, DataTableRow

    call_command("seed_itsm_form_demo", domain="demo.test")
    before = DataTableRow.objects.filter(domain="demo.test").count()
    call_command("seed_itsm_form_demo", domain="demo.test")
    assert DataTableRow.objects.filter(domain="demo.test").count() == before == 20
    assert DataDictionary.objects.filter(domain="demo.test", key__startswith="demo_form_").count() == 4
    assert DataTable.objects.filter(domain="demo.test", key__startswith="demo_form_").count() == 2
    assert not DataTable.objects.filter(domain="domain.com", key__startswith="demo_form_").exists()


def test_demo_api_filter_pagination_and_tree():
    from apps.itsm.devtools.form_demo_api import query

    assert query("/assets", {"department": "rd"})["data"]["total"] == 4
    assert len(query("/assets", {"page_size": "2"})["data"]["items"]) == 2
    assert query("/assets", {"keyword": "host-001"})["data"]["total"] == 1
    assert query("/regions", {})["data"]["items"][0]["children"][0]["id"] == "sh"
    with pytest.raises(ValueError):
        query("/assets", {"page": "bad"})


@pytest.mark.parametrize(
    "schema",
    [
        [],
        {"properties": []},
        {"properties": {"x": {"type": "bad"}}},
        {"properties": {}, "required": ["missing"]},
        {"properties": {"is_valid": {"type": "string"}}},
    ],
)
def test_external_rejects_invalid_parameter_schema(schema):
    with patch("apps.itsm.services.external_api.SSRFValidator.validate"):
        with pytest.raises(ValueError):
            validate_config("api", {"transport": "external", "url": "https://api.example.com/data", "request_schema": schema})


def test_external_secret_not_reused_for_changed_url():
    from apps.itsm.views.integrations import integration_detail

    with patch("apps.itsm.services.external_api.SSRFValidator.validate"):
        item = body(
            integrations(
                req(
                    "post",
                    {
                        "kind": "api",
                        "name": "外部",
                        "config": {"transport": "external", "url": "https://api.example.com/one", "token": "secret"},
                    },
                )
            )
        )
        body(integration_detail(req("put", {"config": {"transport": "external", "url": "https://api.example.com/two"}}), item["id"]))
    assert Integration.objects.get(pk=item["id"]).config["token"] == ""


@pytest.mark.parametrize("status,chunks", [(302, [b"{}"]), (200, [b"not json"])])
def test_external_rejects_redirect_and_non_json(status, chunks):
    item = Integration.objects.create(kind="api", name="外部", config={"transport": "external", "url": "https://api.example.com/data", "method": "GET"})
    response = Mock(status_code=status)
    response.iter_content.return_value = chunks
    with patch("apps.itsm.services.external_api.safe_request", return_value=response):
        assert execute(item, {}, CallerIdentity("owner", "domain.com", "jwt"))["status"] == "failed"
    response.close.assert_called_once()


def test_demo_http_service_returns_json_and_input_errors():
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import ProxyHandler, build_opener

    from apps.itsm.devtools.form_demo_api import Handler

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = build_opener(ProxyHandler({}))
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with client.open(base + "/assets?department=ops&page_size=2", timeout=3) as response:
            data = json.load(response)
            assert data["data"]["total"] == 4
            assert len(data["data"]["items"]) == 2
        with client.open(base + "/health", timeout=3) as response:
            assert json.load(response)["status"] == "ok"
        for path, status in [("/missing", 404), ("/assets?page=invalid", 400)]:
            with pytest.raises(HTTPError) as error:
                client.open(base + path, timeout=3)
            assert error.value.code == status
            error.value.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
