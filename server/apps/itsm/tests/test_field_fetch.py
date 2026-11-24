import copy
from unittest.mock import patch

import pytest

from apps.core.openapi.identity import CallerIdentity
from apps.itsm.models.integration import Integration
from apps.itsm.services.form.fetch import fetch_field, freeze_schema, public_schema, verify_fields

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    item = Integration.objects.create(name="选项", kind="python", config={"script": "def transform(rows, params):\n    return rows"})
    schema = {
        "version": 1,
        "fields": [
            {"key": "department", "type": "input"},
            {
                "key": "asset",
                "type": "select",
                "label": "资产",
                "fetch": {
                    "source": "integration",
                    "integration_id": item.id,
                    "mode": "options",
                    "inputs": {"rows": [], "params": {"department": "${form.department}"}},
                    "list_path": "",
                    "label_path": "name",
                    "value_path": "id",
                    "trigger": "change",
                },
            },
        ],
    }
    identity = CallerIdentity("reader", "domain.com", "jwt", team_ids=[1])
    return item, freeze_schema(schema, "domain.com"), identity


def test_freeze_hides_script_and_pins_version(setup):
    item, schema, _ = setup
    original = copy.deepcopy(schema)
    item.config["script"] = "def transform(rows, params):\n    return []"
    item.save()
    assert schema == original
    assert "script" not in str(public_schema(schema))
    assert "snapshot" not in str(public_schema(schema))


def test_options_receipt_binds_actor_dependencies_and_value(setup):
    _, schema, identity = setup
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": "a1", "name": "资产一"}]}):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context="service:1")
    assert result["options"] == [{"value": "a1", "label": "资产一"}]
    values = {"department": "研发", "asset": "a1", "_field_receipts": {"asset": [result["receipt"]]}}
    checked = verify_fields(schema, values, identity, context="service:1")
    assert checked["_field_labels"]["asset"] == [{"value": "a1", "label": "资产一"}]
    for bad in [
        {**values, "asset": "forged"},
        {**values, "department": "其他"},
        {**values, "_field_receipts": {}},
        {**values, "_field_receipts": ["invalid"]},
    ]:
        with pytest.raises(ValueError):
            verify_fields(schema, bad, identity, context="service:1")
    with pytest.raises(ValueError):
        verify_fields(schema, values, CallerIdentity("other", "domain.com", "jwt"), context="service:1")


def test_disabled_and_cross_tenant_rejected(setup):
    item, schema, identity = setup
    item.is_enabled = False
    item.save()
    with pytest.raises(ValueError):
        fetch_field(schema, "asset", {"department": "研发"}, identity, context="service:1")
    with pytest.raises(Integration.DoesNotExist):
        freeze_schema(
            {"fields": [{"key": "x", "type": "select", "fetch": {"source": "integration", "integration_id": item.id, "mode": "options"}}]},
            "other",
        )


def test_write_api_cannot_be_used_for_fields():
    item = Integration.objects.create(name="写入", kind="api", config={"path": "itsm/tickets", "method": "POST"})
    with pytest.raises(ValueError):
        freeze_schema(
            {"fields": [{"key": "x", "type": "select", "fetch": {"source": "integration", "integration_id": item.id, "mode": "options"}}]},
            "domain.com",
        )


def test_failure_never_returns_unrestricted_options(setup):
    _, schema, identity = setup
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "failed", "code": "timeout"}):
        with pytest.raises(ValueError):
            fetch_field(schema, "asset", {"department": "研发"}, identity, context="failure:1")


def test_dependency_cycles_rejected(setup):
    _, schema, _ = setup
    schema["fields"][0]["fetch"] = {**schema["fields"][1]["fetch"], "inputs": {"params": {"asset": "${form.asset}"}}}
    with pytest.raises(ValueError):
        freeze_schema(schema, "domain.com")


def test_ticket_submission_requires_receipt_and_preserves_labels(setup):
    from apps.itsm.models import Workflow, WorkflowVersion
    from apps.itsm.services.ticket.service import TicketService

    _, schema, identity = setup
    workflow = Workflow.objects.create(name="动态表单", key="fetch-test")
    version = WorkflowVersion.objects.create(
        workflow=workflow, version_no=1, design={"form_schema": schema, "nodes": [{"id": "submit", "type": "submit"}]}
    )
    service = TicketService(identity=identity)
    with pytest.raises(ValueError):
        service.create(version, {"department": "研发", "asset": "a1"}, "reader")
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": "a1", "name": "资产一"}]}):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context=f"version:{version.id}")
    ticket = service.create(version, {"department": "研发", "asset": "a1", "_field_receipts": {"asset": [result["receipt"]]}}, "reader")
    assert ticket.form_data["_field_labels"]["asset"][0]["label"] == "资产一"
    assert "_field_receipts" not in ticket.form_data
    service._save_form(ticket, {}, {"form_data": {"asset": "a1"}})
    assert ticket.form_data["asset"] == "a1"
    with pytest.raises(ValueError):
        service._save_form(ticket, {}, {"form_data": {"department": "其他"}})


def test_numeric_options_and_table_mapping(setup):
    _, schema, identity = setup
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": 7, "name": "资产七"}]}):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context="numeric")
    from apps.itsm.services.form.fetch import validate_submission

    values = validate_submission(schema, {"department": "研发", "asset": 7, "_field_receipts": {"asset": [result["receipt"]]}}, identity, "numeric")
    assert values["asset"] == 7
    schema["fields"][1].update(
        type="table",
        columns=[{"key": "asset_id", "type": "number"}],
        fetch={**schema["fields"][1]["fetch"], "mode": "table", "columns": {"asset_id": "id"}, "enforce": True},
    )
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": 7, "name": "资产七"}]}):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context="table")
    values = validate_submission(
        schema, {"department": "研发", "asset": [{"asset_id": 999}], "_field_receipts": {"asset": [result["receipt"]]}}, identity, "table"
    )
    assert values["asset"] == [{"asset_id": 7}]


def test_data_table_permissions_rechecked_on_cache_hit(setup):
    from apps.itsm.models import DataTable, DataTableField, DataTableRow

    table = DataTable.objects.create(key="assets", name="资产", team=[1])
    DataTableField.objects.create(table=table, key="value")
    DataTableField.objects.create(table=table, key="label")
    DataTableRow.objects.create(table=table, data={"value": "a1", "label": "资产一"})
    schema = freeze_schema(
        {"fields": [{"key": "asset", "type": "select", "fetch": {"source": "table", "resource_key": "assets", "mode": "options"}}]},
        "domain.com",
    )
    identity = setup[2]
    assert fetch_field(schema, "asset", {}, identity, context="table-cache")["options"][0]["value"] == "a1"
    table.team = [99]
    table.save()
    with pytest.raises(PermissionError):
        fetch_field(schema, "asset", {}, identity, context="table-cache")


def test_preview_requires_edit_permission_and_cannot_submit(setup):
    import json

    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.field_fetch import field_fetch

    _, schema, identity = setup
    body = {"preview": True, "schema": schema, "field": "asset", "values": {"department": "研发"}}
    denied = field_fetch(request("post", body, permissions=["form-View"]))
    assert denied.status_code == 403
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": "a1", "name": "资产一"}]}):
        response = field_fetch(request("post", body, permissions=["form-Edit"], username="reader"))
    assert response.status_code == 200
    receipt = json.loads(response.content)["data"]["receipt"]
    with pytest.raises(ValueError):
        verify_fields(schema, {"department": "研发", "asset": "a1", "_field_receipts": {"asset": [receipt]}}, identity, context="version:1")


def test_service_and_ticket_field_endpoints_enforce_scope(setup):
    import json

    from apps.itsm.models import Service, TicketTask, Workflow, WorkflowVersion
    from apps.itsm.services.ticket.service import TicketService
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.field_fetch import field_catalog, field_fetch

    _, schema, _ = setup
    workflow = Workflow.objects.create(name="取数服务", key="fetch-scope")
    version = WorkflowVersion.objects.create(
        workflow=workflow, version_no=1, is_published=True, design={"form_schema": schema, "nodes": [{"id": "submit", "type": "submit"}]}
    )
    workflow.current_version = version
    workflow.save()
    service = Service.objects.create(name="取数服务", workflow=workflow, visibility="restricted", visible_users=["reader"])
    body = {"service_id": service.id, "field": "asset", "values": {"department": "研发"}}
    assert field_fetch(request("post", body, username="other", permissions=["ticket-Add"])).status_code == 404
    assert field_catalog(request(permissions=["form-Edit"])).status_code == 200
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": "a1", "name": "资产一"}]}):
        response = field_fetch(request("post", body, username="reader", permissions=["ticket-Add"]))
    assert response.status_code == 200
    assert json.loads(response.content)["data"]["options"][0]["value"] == "a1"
    # 空的非必填选项可以先创建草稿，再由当前节点处理人取数。
    ticket = TicketService().create(version, {"department": "研发"}, "reader")
    first = TicketTask.objects.create(ticket=ticket, node_id="submit", assignee="reader")
    second = TicketTask.objects.create(ticket=ticket, node_id="parallel", assignee="reader")
    body.pop("service_id")
    body["ticket_id"] = ticket.id
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": "a1", "name": "资产一"}]}):
        selected = field_fetch(request("post", {**body, "task_id": second.id}, username="reader"))
        assert selected.status_code == 200
    proof = json.loads(selected.content)["data"]["receipt"]
    update = {"action": "save", "form_data": {"asset": "a1", "_field_receipts": {"asset": [proof]}}}
    from apps.itsm.views.tickets import operate_ticket

    assert operate_ticket(request("post", {**update, "task_id": first.id}, username="reader"), ticket.id).status_code == 400
    assert operate_ticket(request("post", {**update, "task_id": second.id}, username="reader"), ticket.id).status_code == 200
    body["field"] = "unknown"
    assert field_fetch(request("post", body, username="reader")).status_code == 403
    body["field"] = "asset"
    version.design["nodes"][0]["field_perm"] = {"asset": "read"}
    version.save()
    assert field_fetch(request("post", body, username="reader")).status_code == 403


def test_catalog_reuses_gateway_schema_and_table_columns_without_script_source():
    import json

    from apps.itsm.models import DataTable, DataTableField
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.field_fetch import field_catalog

    Integration.objects.create(name="API参数", kind="api", config={"path": "itsm/tickets", "method": "GET"})
    Integration.objects.create(name="脚本", kind="python", config={"script": "def transform(rows, params):\n    return rows"})
    table = DataTable.objects.create(name="资产表", key="assets")
    DataTableField.objects.create(table=table, key="name", field_type="string")
    payload = json.loads(field_catalog(request(permissions=["form-Edit"])).content)["data"]
    api = next(item for item in payload["integrations"] if item["kind"] == "api")
    assert api["request_schema"]["properties"]["page"]["type"] == "integer"
    assert payload["tables"][0]["columns"] == [{"key": "name", "type": "string"}]
    assert "def transform" not in str(payload)


def test_dictionary_tree_fetch_and_child_submission():
    from apps.itsm.models import DataDictionary, DataDictionaryItem
    from apps.itsm.services.form.fetch import validate_submission

    dictionary = DataDictionary.objects.create(key="tree", name="树字典")
    parent = DataDictionaryItem.objects.create(dictionary=dictionary, key="p", label="父项")
    DataDictionaryItem.objects.create(dictionary=dictionary, key="c", label="子项", parent=parent)
    schema = freeze_schema(
        {"fields": [{"key": "x", "type": "cascade", "fetch": {"source": "dictionary", "mode": "options", "resource_key": "tree"}}]},
        "domain.com",
    )
    identity = CallerIdentity("reader", "domain.com", "jwt")
    result = fetch_field(schema, "x", {}, identity, context="tree")
    assert result["options"] == [{"value": "p", "label": "父项", "children": [{"value": "c", "label": "子项"}]}]
    assert validate_submission(schema, {"x": "c", "_field_receipts": {"x": [result["receipt"]]}}, identity, "tree")["x"] == "c"


def test_api_unknown_parameter_rejected_at_publish():
    item = Integration.objects.create(name="查询", kind="api", config={"path": "itsm/tickets", "method": "GET"})
    with pytest.raises(ValueError, match="API 声明"):
        freeze_schema(
            {
                "fields": [
                    {
                        "key": "x",
                        "type": "select",
                        "fetch": {"source": "integration", "mode": "options", "integration_id": item.id, "inputs": {"invented": 1}},
                    }
                ]
            },
            "domain.com",
        )


def test_table_unknown_filter_rejected_at_publish():
    from apps.itsm.models import DataTable, DataTableField

    table = DataTable.objects.create(key="strict", name="列校验")
    DataTableField.objects.create(table=table, key="name")
    with pytest.raises(ValueError, match="筛选条件"):
        freeze_schema(
            {
                "fields": [
                    {
                        "key": "x",
                        "type": "input",
                        "fetch": {
                            "source": "table",
                            "mode": "value",
                            "resource_key": "strict",
                            "inputs": {"unknown": 1},
                            "value_path": "0.name",
                        },
                    }
                ]
            },
            "domain.com",
        )


def test_python_rows_cannot_reference_scalar(setup):
    item, _, _ = setup
    with pytest.raises(ValueError, match="只能引用表格"):
        freeze_schema(
            {
                "fields": [
                    {"key": "text", "type": "input"},
                    {
                        "key": "x",
                        "type": "input",
                        "fetch": {"source": "integration", "mode": "value", "integration_id": item.id, "inputs": {"rows": "${form.text}"}},
                    },
                ]
            },
            "domain.com",
        )


def test_new_radio_api_maps_platform_list_without_manual_paths(setup):
    _, schema, identity = setup
    field = schema["fields"][1]
    field["type"] = "radio"
    field["fetch"].pop("list_path", None)
    field["fetch"].pop("label_path", None)
    field["fetch"].pop("value_path", None)
    with patch(
        "apps.itsm.services.form.fetch.execute",
        return_value={"status": "done", "output": {"result": True, "data": {"items": [{"id": 1, "title": "测试工单"}]}}},
    ):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context="radio-auto")
    assert result["options"] == [{"value": 1, "label": "测试工单"}]


def test_option_cache_does_not_flatten_cascade_after_radio(setup):
    _, schema, identity = setup
    cfg = schema["fields"][1]["fetch"]
    cfg.pop("label_path", None)
    cfg.pop("value_path", None)
    schema["fields"][1]["type"] = "radio"
    tree = copy.deepcopy(schema["fields"][1])
    tree.update(key="tree", type="cascade")
    schema["fields"].append(tree)
    output = [{"value": "p", "label": "父项", "children": [{"value": "c", "label": "子项"}]}]
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": output}):
        assert "children" not in fetch_field(schema, "asset", {"department": "研发"}, identity, context="cache-types")["options"][0]
        assert fetch_field(schema, "tree", {"department": "研发"}, identity, context="cache-types")["options"][0]["children"][0]["value"] == "c"


def test_field_debug_returns_actionable_mapping_error():
    import json

    from django.test import RequestFactory

    from apps.itsm.views.field_fetch import field_validation_errors

    @field_validation_errors
    def fail(request):
        raise ValueError("结果缺少字段路径：wrong.items")

    response = fail(RequestFactory().post("/"))
    assert response.status_code == 400
    assert json.loads(response.content)["message"] == "结果缺少字段路径：wrong.items"


def test_inspect_sample_before_mapping_does_not_issue_submission_receipt(setup):
    _, schema, identity = setup
    schema["fields"][1].update(type="table", props={"columns": "名称:name"})
    schema["fields"][1]["fetch"].update(mode="table", columns={})
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": {"data": {"items": [{"title": "样本"}]}}}):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context="preview", inspect=True)
    assert result["sample"]["data"]["items"][0]["title"] == "样本"
    assert "receipt" not in result
    with pytest.raises(ValueError):
        fetch_field(schema, "asset", {"department": "研发"}, identity, context="ticket:1", inspect=True)


def test_sample_inspection_requires_edit_permission_and_never_relaxes_publish(setup):
    import json

    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.field_fetch import field_fetch

    _, schema, _ = setup
    schema["fields"][1].update(type="table", props={"columns": "名称:name"})
    schema["fields"][1]["fetch"].update(mode="table", columns={})
    body = {"preview": True, "inspect": True, "schema": schema, "field": "asset", "values": {"department": "研发"}}
    assert field_fetch(request("post", body, permissions=["form-View"])).status_code == 403
    assert field_fetch(request("post", {**body, "preview": False}, permissions=["form-Edit"])).status_code == 403
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"title": "样本"}] * 10}):
        response = field_fetch(request("post", body, permissions=["form-Edit"]))
    assert response.status_code == 200
    data = json.loads(response.content)["data"]
    assert len(data["sample"]) == 3 and "receipt" not in data
    with pytest.raises(ValueError):
        freeze_schema(schema, "domain.com")


def test_manual_child_validates_receipt_as_requester_and_inherits_test_flag(setup):
    import json
    from apps.itsm.models import Ticket, Workflow, WorkflowVersion
    from apps.itsm.services.integrations import request_identity
    from apps.itsm.tests.test_review_regressions import request
    from apps.itsm.views.ticket_operations import create_child

    _, schema, _ = setup
    workflow = Workflow.objects.create(name="子单", key="dynamic-child")
    version = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={"form_schema": schema})
    parent = Ticket.objects.create(workflow=workflow, workflow_version=version, sn="PARENT", title="测试父单", creator="reader", is_test=True)
    actor = {"username": "reader", "permissions": ["ticket-Add"]}
    identity = request_identity(request(**actor))
    with patch("apps.itsm.services.form.fetch.execute", return_value={"status": "done", "output": [{"id": "a1", "name": "资产一"}]}):
        result = fetch_field(schema, "asset", {"department": "研发"}, identity, context=f"version:{version.pk}")
    data = {"department": "研发", "asset": "a1", "_field_receipts": {"asset": [result["receipt"]]}}
    response = json.loads(create_child(request("post", {"form_data": data}, **actor), parent.id).content)
    assert response["result"], response
    child = Ticket.objects.get(pk=response["data"]["id"])
    assert child.is_test and child.creator == "reader" and child.form_data["asset"] == "a1"
