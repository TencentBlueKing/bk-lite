"""集成闭环及授权边界。"""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from rest_framework import serializers

from apps.core.openapi.identity import CallerIdentity
from apps.core.openapi.registry import OpenAPIRegistry
from apps.itsm.models.integration import Integration, IntegrationRun
from apps.itsm.services.integrations import execute, resolve_inputs, validate_config
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as sample_fixture
from apps.itsm.views.integrations import integration_detail, integration_test, integrations

sample = sample_fixture

pytestmark = pytest.mark.django_db


def req(method="get", data=None, permissions=None, domain="domain.com"):
    return request(method, data, "owner", permissions or ["data-View", "data-Edit", "data-Add", "data-Delete"], domain)


def body(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def script_item(**kwargs):
    return Integration.objects.create(
        name="脚本",
        kind="python",
        config={"script": "def transform(rows, params):\n    return rows\n"},
        created_by="owner",
        updated_by="owner",
        **kwargs,
    )


def test_crud_scope_and_permissions():
    item = body(integrations(req("post", {"name": "脚本", "kind": "python", "config": {"script": "def transform(rows, params):\n    return rows"}})))
    assert len(body(integrations(req()))["items"]) == 1
    assert body(integrations(req(domain="other")))["items"] == []
    assert integration_detail(req(domain="other"), item["id"]).status_code == 404
    assert integration_detail(req("put", {"name": "new"}, ["data-View"]), item["id"]).status_code == 403
    assert integration_test(req("post", {"inputs": {}}, ["data-View"]), item["id"]).status_code == 403


def test_script_uses_isolated_runner_and_records_metadata_only():
    item = script_item()
    identity = CallerIdentity("owner", "domain.com", "jwt")
    with patch("apps.itsm.services.integrations.get_transform_executor") as runner:
        runner.return_value.execute.return_value = [{"value": 3}]
        result = execute(item, {"rows": [{"secret": "hidden"}], "params": {}}, identity)
    assert result["status"] == "done"
    assert result["output"] == [{"value": 3}]
    assert "hidden" not in str(IntegrationRun.objects.values().get())
    assert runner.return_value.execute.call_args.kwargs["org_id"] == "domain.com"


def test_unavailable_script_fails_without_local_execution():
    from apps.operation_analysis.services.transform.errors import TransformError

    item = script_item()
    with patch("apps.itsm.services.integrations.get_transform_executor") as runner:
        runner.return_value.execute.side_effect = TransformError("执行服务未配置", code="transform_runner_unavailable", status_code=503)
        result = execute(item, {}, CallerIdentity("owner", "domain.com", "jwt"))
    assert result["status"] == "failed"
    assert result["code"] == "transform_runner_unavailable"


def test_api_reuses_gateway_schema_and_permissions():
    class Input(serializers.Serializer):
        value = serializers.IntegerField()

    registry = OpenAPIRegistry()
    handler = Mock(return_value={"value": 2})
    registry.register(
        path="demo/read", method="POST", serializer_class=Input, func=handler, team_free=True, permission="demo-View", permission_app="demo"
    )
    item = Integration.objects.create(name="接口", kind="api", config={"path": "demo/read", "method": "POST"})
    with patch("apps.itsm.services.integrations.default_registry", registry):
        denied = execute(item, {"value": 1}, CallerIdentity("reader", "domain.com", "jwt"))
        assert denied["status"] == "failed"
        assert denied["code"] == "PERM_MISSING"
        assert not handler.called
        allowed = CallerIdentity("reader", "domain.com", "jwt", permission={"demo": {"demo-View"}})
        assert execute(item, {"value": "invalid"}, allowed)["code"] == "SCHEMA_INVALID"
        assert execute(item, {"value": 2}, allowed)["status"] == "done"
        handler.assert_called_once_with(value=2)


def test_disabled_and_cross_domain_never_execute():
    item = script_item(is_enabled=False)
    with patch("apps.itsm.services.integrations.get_transform_executor") as runner:
        with pytest.raises(ValueError):
            execute(item, {}, CallerIdentity("owner", "domain.com", "jwt"))
        item.is_enabled = True
        with pytest.raises(PermissionError):
            execute(item, {}, CallerIdentity("owner", "other", "jwt"))
        assert not runner.called


def test_validate_python_and_todo_config():
    for config in [{"script": "x" * 100001}, {"script": "def broken("}, {"script": ""}]:
        with pytest.raises(ValueError):
            validate_config("python", config)
    with pytest.raises(ValueError):
        validate_config("todo", {"url": "http://127.0.0.1/private"})


def test_parameter_binding_preserves_types_and_rejects_missing(sample):
    ticket, _ = sample
    assert resolve_inputs({"amount": "${form.amount}", "sn": "${ticket.sn}"}, ticket) == {"amount": 100, "sn": ticket.sn}
    with pytest.raises(ValueError):
        resolve_inputs({"v": "${form.missing}"}, ticket)


def test_flow_runs_only_matching_tenant_integration(sample):
    from apps.itsm.services.auto_runner import run_auto_action

    ticket, _ = sample
    item = script_item()
    with (
        patch("apps.itsm.services.integrations.live_identity", return_value=CallerIdentity("owner", ticket.domain, "jwt")),
        patch("apps.itsm.services.integrations.get_transform_executor") as runner,
    ):
        runner.return_value.execute.return_value = [{"ok": True}]
        status, detail = run_auto_action(ticket, "integration", {"integration_id": item.id, "inputs": {"rows": []}}, "system")
        assert status == "done"
        assert detail["run_id"]
        assert "output" not in detail
        item.domain = "other"
        item.save()
        with pytest.raises(Integration.DoesNotExist):
            run_auto_action(ticket, "integration", {"integration_id": item.id}, "system")


def test_edit_disable_and_history_are_domain_scoped():
    item = script_item()
    response = integration_detail(req("put", {"name": "新版", "is_enabled": False}), item.id)
    assert body(response)["name"] == "新版"
    assert body(response)["is_enabled"] is False
    assert integration_test(req("post", {"inputs": {}}), item.id).status_code == 400
    assert body(integration_detail(req(), item.id))["runs"] == []
    assert integration_detail(req("put", {"name": ""}), item.id).status_code == 400
    assert integration_detail(req("delete", domain="other"), item.id).status_code == 404
    assert integration_detail(req("delete"), item.id).status_code == 200
    item.refresh_from_db()
    assert not item.is_enabled


def test_todo_token_is_encrypted_masked_and_preserved():
    with patch("apps.itsm.services.integrations.SSRFValidator.validate"):
        item = body(integrations(req("post", {"name": "待办", "kind": "todo", "config": {"url": "https://example.com/hook", "token": "test-secret"}})))
        assert item["has_token"] is True
        assert item["config"]["token"] == ""
        stored = Integration.objects.get(id=item["id"])
        assert stored.config["token"] != "test-secret"
        body(integration_detail(req("put", {"config": {"url": "https://example.com/next", "token": ""}}), stored.id))
        stored.refresh_from_db()
        response = Mock(status_code=204)
        with patch("apps.itsm.services.todo_sync.safe_request", return_value=response) as call:
            result = body(integration_test(req("post", {"inputs": {"event": "test"}}), stored.id))
        assert result["status"] == "done"
        assert call.call_args.kwargs["headers"]["Authorization"] == "Bearer test-secret"


def test_catalog_summary_and_validation():
    from apps.itsm.views.integrations import integration_catalog

    item = script_item()
    assert integration_catalog(req(permissions=["ticket-View"])).status_code == 403
    assert "services" in body(integration_catalog(req()))
    result = body(integrations(req(data={"summary": "1"}, permissions=["workflow-View"])))
    assert "config" not in result["items"][0]
    assert integrations(req(permissions=["workflow-View"])).status_code == 403
    assert integrations(req("post", {"name": "", "kind": "python", "config": {}})).status_code == 400
    for kind, config in [("api", {"path": "missing/read"}), ("python", {"script": "x=1"}), ("unknown", {}), ("python", [])]:
        with pytest.raises(ValueError):
            validate_config(kind, config)
    assert integration_test(req("post", {"inputs": []}), item.id).status_code == 400
    with patch("apps.itsm.services.integrations.get_transform_executor") as runner:
        result = body(integration_test(req("post", {"inputs": {"rows": "invalid"}}), item.id))
        assert result["status"] == "failed"
        assert not runner.called


def test_live_identity_refuses_disabled_or_revoked_maintainer():
    from apps.itsm.services.integrations import live_identity

    item = script_item()
    with patch("apps.system_mgmt.models.User.objects.filter") as accounts:
        accounts.return_value.first.return_value = None
        with pytest.raises(PermissionError):
            live_identity(item)
    account = SimpleNamespace(group_list=[1])
    user = SimpleNamespace(is_superuser=False, permission={"itsm": set()}, roles=[])
    with (
        patch("apps.system_mgmt.models.User.objects.filter") as accounts,
        patch("apps.base.models.user.User.objects.filter") as users,
        patch("apps.system_mgmt.services.user_access.is_account_expired", return_value=False),
        patch("apps.core.backends.APISecretAuthBackend._populate_user_permissions"),
    ):
        accounts.return_value.first.return_value = account
        users.return_value.first.return_value = user
        with pytest.raises(PermissionError):
            live_identity(item)
        user.permission = {"itsm": {"data-Edit"}}
        assert live_identity(item).user == "owner"


def test_api_deleted_and_executor_exception_are_recorded():
    identity = CallerIdentity("owner", "domain.com", "jwt")
    item = Integration.objects.create(name="已删除接口", kind="api", config={"path": "missing/read", "method": "POST"})
    result = execute(item, {}, identity)
    assert result["status"] == "failed"
    item = script_item()
    with patch("apps.itsm.services.integrations.get_transform_executor", side_effect=RuntimeError("internal secret")):
        result = execute(item, {}, identity)
    assert "internal secret" not in str(result)


def test_flow_output_can_be_bound_to_next_node(sample):
    from apps.itsm.services.integrations import run_for_ticket

    ticket, _ = sample
    item = script_item()
    with (
        patch("apps.itsm.services.integrations.live_identity", return_value=CallerIdentity("owner", ticket.domain, "jwt")),
        patch("apps.itsm.services.integrations.get_transform_executor") as runner,
    ):
        runner.return_value.execute.return_value = [{"amount": 200}]
        run_for_ticket(ticket, {"integration_id": item.id, "inputs": {}, "result_field": "api_result"})
    ticket.refresh_from_db()
    assert ticket.form_data["api_result"] == [{"amount": 200}]


def test_api_token_identity_keeps_scope_and_single_team():
    from apps.itsm.services.integrations import request_identity

    request_obj = req()
    request_obj.user.group_list = [{"id": 1}, {"id": 2}]
    request_obj.user._api_secret_id = 9
    request_obj.user._api_secret_team = 2
    request_obj.user._api_secret_scope = {"internal": []}
    identity = request_identity(request_obj)
    assert identity.credential_type == "api_token"
    assert identity.team_ids == [2]
    assert identity.token_scope == {"internal": []}


def test_workflow_never_borrows_integration_maintainer_identity(sample):
    from apps.itsm.services.integrations import run_for_ticket

    ticket, _ = sample
    ticket.workflow_version.updated_by = "designer"
    ticket.workflow_version.save()
    item = script_item()
    with patch("apps.itsm.services.integrations.live_identity", return_value=CallerIdentity("designer", ticket.domain, "jwt")) as identity, patch(
        "apps.itsm.services.integrations.get_transform_executor"
    ) as runner:
        runner.return_value.execute.return_value = []
        run_for_ticket(ticket, {"integration_id": item.id})
    assert identity.call_args.kwargs["actor"] == "designer"
