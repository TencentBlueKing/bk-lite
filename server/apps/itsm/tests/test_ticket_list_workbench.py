"""列表配置、筛选性能与批量操作行为。"""
import json
from unittest.mock import patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import TicketTask
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests import test_review_regressions as review
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.extend import batch_operate
from apps.itsm.views.tickets import tickets

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample():
    return review.sample.__wrapped__()


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_personal_columns_groups_and_isolation(sample):
    from apps.itsm.views.ticket_center import center_settings

    defaults = data(center_settings(request(username="owner")))["columns"]
    assert "sn" in defaults
    columns = ["sn", "title", "created_at"]
    data(center_settings(request("put", {"columns": columns, "username": "other"}, "owner")))
    assert data(center_settings(request(username="owner")))["columns"] == columns
    assert data(center_settings(request(username="other")))["columns"] == defaults
    assert data(center_settings(request(username="owner", domain="other")))["columns"] == defaults
    saved = data(center_settings(request("post", {"name": "处理中", "filters": {"status": "processing", "tab": "following"}}, "owner")))
    assert len(data(center_settings(request(username="owner")))["views"]) == 1
    assert center_settings(request("delete", {"id": saved["id"]}, "other")).status_code == 404
    data(center_settings(request("delete", {"id": saved["id"]}, "owner")))
    assert data(center_settings(request(username="owner")))["views"] == []
    data(center_settings(request("put", {"columns": None}, "owner")))
    assert data(center_settings(request(username="owner")))["columns"] == defaults
    assert center_settings(request("put", {"columns": ["form_data"]}, "owner")).status_code == 400
    assert center_settings(request("post", {"name": "bad", "filters": {"domain": "other"}}, "owner")).status_code == 400


def test_filters_sort_history_and_projection(sample):
    ticket, task = sample
    second = TicketService().create(ticket.workflow_version, {"title": "ZZ", "amount": 1}, "owner")
    result = data(tickets(request(payload={"fields": "sn,title,created_at", "ordering": "title", "status": "new,processing"}, username="owner")))
    assert [x["id"] for x in result["items"]] == [second.id, ticket.id]
    assert "tasks" not in result["items"][0] and "sla_due_at" not in result["items"][0]
    task.status = "done"
    task.save()
    assert data(tickets(request(payload={"tab": "history"}, username="handler")))["count"] == 1
    assert data(tickets(request(payload={"tab": "mine"}, username="handler")))["count"] == 0
    for ordering in ["form_data", "--title"]:
        assert tickets(request(payload={"ordering": ordering}, username="owner")).status_code == 400


@pytest.mark.parametrize(
    ("permissions", "can_apply"),
    [
        (["ticket-View"], False),
        (["ticket-View", "portal-View"], False),
        (["ticket-View", "ticket-Add"], False),
        (["ticket-View", "portal-View", "ticket-Add"], True),
    ],
)
def test_ticket_list_reports_quick_apply_availability(permissions, can_apply):
    response = tickets(request(username="owner", permissions=permissions))
    assert data(response)["can_apply"] is can_apply


def test_projection_queries_do_not_load_tasks_or_sla(sample):
    from apps.itsm.models import TicketSLARecord

    req = request(payload={"fields": "sn,title"}, username="owner")
    req.user.is_superuser = True
    with CaptureQueriesContext(connection) as captured:
        assert data(tickets(req))["count"] == 1
    sql = " ".join(q["sql"] for q in captured)
    assert TicketTask._meta.db_table not in sql
    assert TicketSLARecord._meta.db_table not in sql
    assert len(captured) <= 3


def test_batch_returns_all_items_and_selects_actor_task(sample):
    ticket, task = sample
    with patch("apps.itsm.views.extend._service", return_value=TicketService()):
        result = data(batch_operate(request("post", {"ids": [ticket.id, 999999], "action": "approve"}, "handler")))
    assert result["items"][0]["ok"] is True
    assert result["items"][1]["ok"] is False
    task.refresh_from_db()
    assert task.status == "done"


def test_batch_validation_and_partial_failure(sample):
    ticket, _ = sample
    assert batch_operate(request("post", {"ids": [], "action": "approve"}, "owner")).status_code == 400
    assert batch_operate(request("post", {"ids": list(range(51)), "action": "approve"}, "owner")).status_code == 400
    assert batch_operate(request("post", {"ids": [ticket.id], "action": "terminate"}, "owner")).status_code == 400
    assert batch_operate(request("post", {"ids": [ticket.id], "action": "approve"}, "owner", ["ticket-View"])).status_code == 403
    result = data(batch_operate(request("post", {"ids": [ticket.id], "action": "approve"}, "owner")))
    assert not result["items"][0]["ok"]
    with patch("apps.itsm.views.extend._service") as service:
        service.return_value.operate.side_effect = FlowableError(502, "failed")
        result = data(batch_operate(request("post", {"ids": [ticket.id, 999999], "action": "approve"}, "handler")))
    assert len(result["items"]) == 2 and not any(x["ok"] for x in result["items"])


def test_batch_follow_idempotent_read_permission(sample):
    ticket, _ = sample
    for _ in range(2):
        assert data(batch_operate(request("post", {"ids": [ticket.id], "action": "follow"}, "owner", ["ticket-View"])))["items"][0]["ok"]
    assert ticket.followers.count() == 1
    data(batch_operate(request("post", {"ids": [ticket.id], "action": "unfollow"}, "owner", ["ticket-View"])))
    assert ticket.followers.count() == 0


def test_date_bounds_created_group_and_query_count(sample):
    from django.utils import timezone

    ticket, _ = sample
    day = timezone.localdate(ticket.created_at).isoformat()
    result = data(tickets(request(payload={"tab": "created", "created_after": day, "created_before": day}, username="owner")))
    assert result["count"] == 1
    assert tickets(request(payload={"created_after": "not-a-date"}, username="owner")).status_code == 400
    req = request(payload={"fields": "sn,title,node,assignees,sla,workflow,priority"}, username="owner")
    with CaptureQueriesContext(connection) as captured:
        data(tickets(req))
    count = len(captured)
    for i in range(5):
        TicketService().create(ticket.workflow_version, {"title": f"批量样本{i}", "amount": 1}, "owner")
    with CaptureQueriesContext(connection) as captured:
        result = data(tickets(req))
    assert result["count"] == 6
    assert len(captured) == count


def test_invalid_groups_and_duplicate_names(sample):
    from apps.itsm.views.ticket_center import center_settings

    for payload in [{"name": ""}, {"name": "bad", "filters": {"q": 3}}, {"name": "bad", "filters": {"tab": "other"}}]:
        assert center_settings(request("post", payload, "owner")).status_code == 400
    payload = {"name": "唯一分组", "filters": {"created_after": "2026-01-01T00:00:00Z"}}
    data(center_settings(request("post", payload, "owner")))
    assert center_settings(request("post", payload, "owner")).status_code == 400


def test_batch_invisible_domain_node_rule_and_multiple_tasks(sample):
    ticket, task = sample
    payload = {"ids": [ticket.id], "action": "approve"}
    assert not data(batch_operate(request("post", payload, "handler", domain="other")))["items"][0]["ok"]
    version = ticket.workflow_version
    version.design["nodes"][1]["actions"] = []
    version.save()
    assert not data(batch_operate(request("post", payload, "handler")))["items"][0]["ok"]
    TicketTask.objects.create(ticket=ticket, node_id=task.node_id, assignee="handler")
    assert not data(batch_operate(request("post", payload, "handler")))["items"][0]["ok"]


def test_filter_tags_only_visible_ticket_tags(sample):
    from apps.itsm.models import TicketTag
    from apps.itsm.views.ticket_center import filter_tags

    ticket, _ = sample
    visible = TicketTag.objects.create(name="数据库", domain=ticket.domain)
    ticket.tags.add(visible)
    TicketTag.objects.create(name="隐藏标签", domain=ticket.domain)
    assert data(filter_tags(request(username="owner")))["items"] == [{"name": "数据库", "color": "#1677ff"}]
    assert data(filter_tags(request(payload={"q": "库"}, username="owner")))["items"] == [{"name": "数据库", "color": "#1677ff"}]
    assert data(filter_tags(request(username="outsider")))["items"] == []
    assert data(filter_tags(request(username="owner", domain="other")))["items"] == []


def test_user_filter_accepts_ticket_permission_and_scopes_domain():
    from apps.itsm.views.users import UserSearchView
    from apps.system_mgmt.models import User

    User.objects.create(username="filter-user", display_name="筛选用户", domain="tenant-a")
    User.objects.create(username="filter-other", display_name="其他域", domain="domain.com")
    response = UserSearchView().get(request(payload={"q": "filter"}, username="owner", domain="tenant-a", permissions=["ticket-View"]))
    assert response.status_code == 200
    assert response.data["items"] == [{"username": "filter-user", "display_name": "筛选用户"}]


def test_batch_available_actions_respect_node_and_permissions(sample):
    from apps.itsm.services.ticket.batch import selection

    ticket, task = sample
    options, _ = selection(request(username="handler"), [ticket.id])
    assert "approve" in options["actions"] and "submit" not in options["actions"]
    options, _ = selection(request(username="owner", permissions=["ticket-View"]), [ticket.id])
    assert set(options["actions"]) == {"follow", "unfollow"}
    version = ticket.workflow_version
    version.design["nodes"][1]["actions"] = ["reject"]
    version.save()
    options, _ = selection(request(username="handler"), [ticket.id])
    assert set(options["actions"]) == {"follow", "unfollow", "reject"}


def test_mixed_nodes_block_process_before_any_write(sample):
    from apps.itsm.services.ticket.batch import selection

    ticket, _ = sample
    second = TicketService().create(ticket.workflow_version, {"title": "另一个节点", "amount": 1}, "handler")
    TicketTask.objects.create(ticket=second, node_id="submit", assignee="handler")
    options, _ = selection(request(username="handler"), [ticket.id, second.id])
    assert options["mixed_nodes"] and set(options["actions"]) == {"follow", "unfollow"}
    with patch("apps.itsm.views.extend._service") as service:
        result = data(batch_operate(request("post", {"ids": [ticket.id, second.id], "action": "approve"}, "handler")))
    assert not any(item["ok"] for item in result["items"])
    service.assert_not_called()


@pytest.fixture
def dynamic_tickets(sample):
    ticket, _ = sample
    version = ticket.workflow_version
    version.design["form_schema"] = {
        "fields": [
            {"key": "title", "type": "input"},
            {"key": "amount", "label": "申请金额", "type": "number"},
            {"key": "notes", "label": "备注", "type": "input"},
            {"key": "secret", "type": "input"},
            {"key": "conditional", "type": "input", "visibleWhen": {"field": "amount", "op": ">", "value": 50}},
            {"key": "nested", "type": "section", "children": [{"key": "nested_note", "type": "input"}]},
        ]
    }
    version.design["nodes"][1]["field_perm"] = {"secret": "hidden", "nested": "hidden"}
    version.save()
    match = TicketService().create(version, {"title": "=1+1", "amount": 200, "notes": "Blue office"}, "owner")
    TicketService().create(version, {"title": "数字较小", "amount": 9, "notes": "blue desk"}, "owner")
    invisible = TicketService().create(version, {"title": "他人的工单", "amount": 200, "notes": "blue desk"}, "other")
    return match, invisible


def test_dynamic_filters_catalog_groups_and_invalid_conditions(dynamic_tickets):
    from apps.itsm.views.ticket_center import center_settings, filter_fields

    match, _ = dynamic_tickets
    workflow_id = str(match.workflow_id)
    params = {"workflow_id": workflow_id}
    fields = data(filter_fields(request(payload=params, username="owner")))["fields"]
    assert {field["key"] for field in fields} == {"amount", "notes"}
    assert data(filter_fields(request(username="outsider")))["workflows"] == []
    assert filter_fields(request(payload=params, username="outsider")).status_code == 404
    assert filter_fields(request(payload=params, username="owner", domain="elsewhere")).status_code == 404
    filters = {
        **params,
        "tab": "created",
        "form_filters": [{"key": "amount", "operator": "gte", "value": 150}, {"key": "notes", "operator": "contains", "value": "blue"}],
    }
    saved = data(center_settings(request("post", {"name": "大额申请", "filters": filters}, "owner")))
    query = {**saved["filters"], "form_filters": json.dumps(saved["filters"]["form_filters"])}
    assert [row["id"] for row in data(tickets(request(payload=query, username="owner")))["items"]] == [match.id]
    for clause in [
        {"key": "secret", "operator": "eq", "value": "original"},
        {"key": "amount", "operator": "contains", "value": "200"},
        {"key": "notes", "operator": "eq", "value": ["blue"]},
    ]:
        assert tickets(request(payload={**params, "form_filters": json.dumps([clause])}, username="owner")).status_code == 400


def test_export_matches_filters_checks_permissions_and_preserves_literal_cells(dynamic_tickets):
    import base64
    from io import BytesIO

    from openpyxl import load_workbook

    from apps.itsm.models.extend import TicketExportTask
    from apps.itsm.views.ticket_export import export_tickets

    match, invisible = dynamic_tickets
    payload = {
        "filters": {"workflow_id": str(match.workflow_id), "tab": "created", "form_filters": [{"key": "amount", "operator": "gte", "value": 150}]},
        "form_columns": ["amount", "notes"],
        "ids": [match.id, invisible.id],
    }
    assert export_tickets(request("post", payload, "owner")).status_code == 403
    assert export_tickets(request("post", payload, "owner", ["ticket-Export"])).status_code == 403
    permissions = ["ticket-View", "ticket-Export"]
    assert export_tickets(request("post", {**payload, "form_columns": ["secret"]}, "owner", permissions)).status_code == 400
    result = data(export_tickets(request("post", payload, "owner", permissions)))
    assert result["count"] == 1
    sheet = load_workbook(BytesIO(base64.b64decode(result["content_base64"]))).active
    assert list(sheet.values) == [("单号", "标题", "提单人", "状态", "申请金额", "备注"), (match.sn, "=1+1", "owner", "new", 200, "Blue office")]
    assert sheet["B2"].data_type == "s"
    assert TicketExportTask.objects.get(pk=result["id"]).domain == match.domain


def test_historical_hidden_field_is_neither_matched_nor_exported(dynamic_tickets):
    import base64
    from copy import deepcopy
    from io import BytesIO

    from openpyxl import load_workbook

    from apps.itsm.models import WorkflowVersion
    from apps.itsm.views.ticket_export import export_tickets

    match, _ = dynamic_tickets
    design = deepcopy(match.workflow_version.design)
    design["nodes"][1]["field_perm"]["amount"] = "hidden"
    hidden_version = WorkflowVersion.objects.create(workflow=match.workflow, version_no=2, design=design, is_published=True)
    hidden = TicketService().create(hidden_version, {"title": "金额不可见", "amount": 200}, "owner")
    invalid = TicketService().create(match.workflow_version, {"title": "旧表单值", "amount": 200}, "owner")
    invalid.form_data["amount"] = "200"
    invalid.save(update_fields=["form_data"])
    workflow_id = str(match.workflow_id)
    clause = {"key": "amount", "operator": "gte", "value": 150}
    result = data(tickets(request(payload={"workflow_id": workflow_id, "form_filters": json.dumps([clause])}, username="owner")))
    assert [row["id"] for row in result["items"]] == [match.id]
    payload = {"filters": {"workflow_id": workflow_id}, "form_columns": ["amount"], "ids": [hidden.id]}
    result = data(export_tickets(request("post", payload, "owner", ["ticket-View", "ticket-Export"])))
    sheet = load_workbook(BytesIO(base64.b64decode(result["content_base64"]))).active
    assert sheet["A2"].value == hidden.sn and sheet["E2"].value is None


def test_export_limit_does_not_create_partial_file(dynamic_tickets, monkeypatch):
    from apps.itsm.models.extend import TicketExportTask
    from apps.itsm.views.ticket_export import export_tickets

    monkeypatch.setattr("apps.itsm.views.ticket_export.MAX_ROWS", 1)
    permissions = ["ticket-View", "ticket-Export"]
    assert export_tickets(request("post", {}, "owner", permissions)).status_code == 400
    assert export_tickets(request("post", {"ids": []}, "owner", permissions)).status_code == 400
    assert not TicketExportTask.objects.exists()


def test_dynamic_choice_accepts_numeric_value_stored_by_integration(dynamic_tickets):
    match, _ = dynamic_tickets
    version = match.workflow_version
    version.design["form_schema"]["fields"].append({"key": "asset", "type": "select", "label": "关联资产"})
    version.save(update_fields=["design"])
    match.form_data["asset"] = 72
    match.save(update_fields=["form_data"])
    params = {"workflow_id": str(match.workflow_id), "form_filters": json.dumps([{"key": "asset", "operator": "eq", "value": "72"}])}
    result = data(tickets(request(payload=params, username="owner")))
    assert [row["id"] for row in result["items"]] == [match.id]
