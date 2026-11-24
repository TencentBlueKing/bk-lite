"""审查回归：对象授权、表单权限、任务终态与规则执行。"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.itsm.models import FormModel, FormVersion, Ticket, TicketStatus, TicketTask, Workflow, WorkflowVersion
from apps.itsm.models.extend import TicketProxy, Trigger
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.services.triggers import fire_triggers
from apps.itsm.views.extend import resources
from apps.itsm.views.tickets import operate_ticket, ticket_detail, tickets

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample():
    form = FormModel.objects.create(name="回归", key="review")
    fv = FormVersion.objects.create(
        form=form,
        version_no=1,
        schema={
            "fields": [
                {"key": "title", "type": "input", "required": True},
                {"key": "amount", "type": "number", "required": True},
                {"key": "secret", "type": "input"},
            ]
        },
    )
    form.current_version = fv
    form.save()
    workflow = Workflow.objects.create(name="回归", key="review", form=form)
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        is_published=True,
        design={
            "nodes": [
                {"id": "submit", "type": "submit"},
                {"id": "approval_1", "type": "approval", "field_perm": {"secret": "read"}},
            ]
        },
    )
    for key in ["new", "processing", "finished", "terminated", "cancelled"]:
        TicketStatus.objects.get_or_create(key=key, defaults={"name": key})
    ticket = TicketService().create(version, {"title": "申请", "amount": 100, "secret": "original"}, "owner")
    task = TicketTask.objects.create(ticket=ticket, node_id="approval_1", assignee="handler")
    return ticket, task


def request(method="get", payload=None, username="outsider", permissions=None, domain="domain.com"):
    req = (
        getattr(RequestFactory(), method)("/", data=json.dumps(payload or {}), content_type="application/json")
        if method != "get"
        else RequestFactory().get("/", payload or {})
    )
    req.user = SimpleNamespace(
        username=username,
        domain=domain,
        is_superuser=False,
        locale="zh-Hans",
        permission={"itsm": set(permissions or ["ticket-View", "ticket-Operate"])},
    )
    return req


def test_unrelated_user_cannot_read_or_save(sample):
    ticket, _ = sample
    assert ticket_detail(request(), ticket.id).status_code == 404
    assert operate_ticket(request("post", {"action": "save", "form_data": {"secret": "attack"}}), ticket.id).status_code == 404
    ticket.refresh_from_db()
    assert ticket.form_data["secret"] == "original"


def test_creator_cannot_act_as_another_handler(sample):
    ticket, task = sample
    with pytest.raises(PermissionError):
        TicketService().operate(ticket, task, "approve", {}, "owner")
    task.refresh_from_db()
    assert task.status == "pending"


@pytest.mark.parametrize("action", ["claim", "save", "approve"])
def test_readonly_fields_survive_partial_update(sample, action):
    ticket, task = sample
    TicketService().operate(ticket, task, action, {"form_data": {"secret": "attack", "amount": 200}}, "handler")
    ticket.refresh_from_db()
    assert ticket.form_data == {"title": "申请", "amount": 200, "secret": "original"}


def test_view_permission_cannot_create_proxy(sample):
    response = resources(request("post", {"principal": "owner", "agent": "outsider"}, permissions=["ticket-View"]), "proxies")
    assert response.status_code == 403
    assert not TicketProxy.objects.exists()


def test_missing_required_field_returns_validation_error(sample):
    ticket, _ = sample
    response = tickets(
        request(
            "post", {"workflow_version_id": ticket.workflow_version_id, "form_data": {"title": "缺少金额"}}, permissions=["ticket-View", "ticket-Add"]
        )
    )
    assert response.status_code == 400
    assert "amount" in response.content.decode()


def test_closing_clears_claimed_task(sample):
    ticket, task = sample
    task.status = "claimed"
    task.save()
    TicketService().operate(ticket, task, "close", {}, "handler")
    task.refresh_from_db()
    assert task.status == "done"


def test_trigger_maps_event_and_checks_conditions(sample):
    ticket, _ = sample
    Trigger.objects.create(
        name="匹配", event="ticket_suspend", action="tag", config={"response": "hit", "when": {"field": "amount", "op": ">", "value": 50}}
    )
    Trigger.objects.create(
        name="不匹配", event="ticket_suspend", action="tag", config={"response": "miss", "when": {"field": "amount", "op": ">", "value": 500}}
    )
    fire_triggers(ticket, "suspend", "owner")
    assert list(ticket.tags.values_list("name", flat=True)) == ["hit"]


def test_domain_scope_even_for_same_username(sample):
    ticket, _ = sample
    assert ticket_detail(request(username="owner", domain="other.example"), ticket.id).status_code == 404


def test_pagination_and_pending_filter(sample):
    ticket, task = sample
    response = tickets(request(payload={"tab": "mine"}, username="owner"))
    assert json.loads(response.content)["data"]["count"] == 0
    response = tickets(request(payload={"tab": "mine"}, username="handler"))
    assert json.loads(response.content)["data"]["count"] == 1


def test_sync_clears_claimed_tasks_removed_by_engine(sample):
    ticket, task = sample
    task.status = "claimed"
    task.save()
    ticket.process_instance_id = "process"
    ticket.save()
    client = SimpleNamespace(list_tasks_including_children=lambda _: [])
    TicketService(client).sync_ticket(ticket)
    task.refresh_from_db()
    assert task.status == "done"


def test_auto_job_executes_once_and_syncs_next_task(sample):
    from unittest.mock import Mock

    from apps.itsm.models import DataTable, DataTableRow
    from apps.itsm.services.external_jobs import process_job

    ticket, _ = sample
    table = DataTable.objects.create(name="自动记录", key="auto_test")
    version = ticket.workflow_version
    version.design["nodes"].append({"id": "auto_1", "type": "auto", "auto": {"kind": "table", "table_key": table.key, "data": {"verified": True}}})
    version.save()
    ticket.process_instance_id = "process-auto"
    ticket.save()
    client = Mock()
    client.list_tasks_including_children.return_value = [{"id": "next", "taskDefinitionKey": "approval_1", "assignee": "handler"}]
    client.get_process_instance.return_value = {"id": "process-auto"}
    client._request.return_value = {}
    job = {"id": "job-one", "processInstanceId": "process-auto", "elementId": "auto_1"}
    with patch("apps.itsm.services.ticket.service.itsm_event.send"), patch("apps.itsm.services.todo_sync.push_todo"):
        assert process_job(client, job) is True
        assert process_job(client, job) is True
    assert DataTableRow.objects.filter(table=table).count() == 1
    assert ticket.tasks.filter(flowable_task_id="next", status="pending").exists()


def test_unconfigured_auto_job_is_not_acknowledged(sample):
    from unittest.mock import Mock

    from apps.itsm.services.external_jobs import process_job

    ticket, _ = sample
    ticket.process_instance_id = "process-bad"
    ticket.save()
    client = Mock()
    assert process_job(client, {"id": "bad-job", "processInstanceId": "process-bad", "elementId": "unknown"}) is False
    client.complete_external_job.assert_not_called()


def test_approval_rejects_submit_action(sample):
    ticket, task = sample
    with pytest.raises(ValueError):
        TicketService().operate(ticket, task, "submit", {}, "handler")
    task.refresh_from_db()
    assert task.status == "pending"


def test_stop_does_not_claim_success_when_engine_fails(sample):
    from unittest.mock import Mock

    from apps.itsm.flowable.client import FlowableError

    ticket, task = sample
    ticket.process_instance_id = "active"
    ticket.save()
    client = Mock()
    client.delete_process_instance.side_effect = FlowableError(503, "")
    with pytest.raises(FlowableError):
        TicketService(client).operate(ticket, task, "close", {}, "handler")
    ticket.refresh_from_db()
    assert ticket.status.key == "new"


def test_late_engine_task_is_reconciled_after_ack(sample):
    from unittest.mock import Mock

    from apps.itsm.services.external_jobs import reconcile_tickets

    ticket, _ = sample
    ticket.process_instance_id = "late-process"
    ticket.save()
    client = Mock()
    client.list_tasks_including_children.return_value = [{"id": "late-task", "taskDefinitionKey": "approval_1", "assignee": "handler"}]
    client.get_process_instance.return_value = {"id": "late-process"}
    client._request.return_value = {}
    with patch("apps.itsm.services.ticket.service.itsm_event.send"), patch("apps.itsm.services.todo_sync.push_todo"):
        reconcile_tickets(client)
    assert ticket.tasks.filter(flowable_task_id="late-task", status="pending").exists()


def test_subprocess_form_creates_linked_child_once(sample):
    ticket, task = sample
    child_flow = Workflow.objects.create(name="子流程", key="child")
    child_version = WorkflowVersion.objects.create(workflow=child_flow, version_no=1, design={"nodes": []}, is_published=True)
    form_version = ticket.workflow.form.current_version
    form_version.schema["fields"].append({"key": "children", "type": "subProcessForm", "props": {"workflow_version_id": child_version.id}})
    form_version.save()
    service = TicketService()
    service.operate(ticket, task, "save", {"form_data": {"children": [{"form_data": {"title": "子申请"}}]}}, "handler")
    ticket.refresh_from_db()
    assert ticket.relations.filter(relation_type="child").count() == 1
    rows = ticket.form_data["children"]
    assert rows[0]["ticket_id"] == ticket.relations.get().related_id
    service.operate(ticket, task, "save", {"form_data": {"children": rows}}, "handler")
    assert ticket.relations.count() == 1


@pytest.mark.parametrize("view_name", ["comments", "attachments", "followers", "ticket_tags", "relations"])
def test_collaboration_endpoints_share_object_scope(sample, view_name):
    from apps.itsm.views import m2

    ticket, _ = sample
    view = getattr(m2, view_name)
    assert view(request(), ticket.id).status_code == 404
    assert view(request(username="owner"), ticket.id).status_code == 200


def test_detail_log_survey_and_form_contract(sample):
    from apps.itsm.views.tickets import ticket_form, ticket_logs, ticket_survey

    ticket, task = sample
    response = json.loads(ticket_detail(request(username="handler"), ticket.id).content)["data"]
    assert response["tasks"][0]["node_type"] == "approval"
    assert response["tasks"][0]["can_operate"] is True
    assert response["tasks"][0]["field_perm"]["secret"] == "read"
    assert ticket_logs(request(), ticket.id).status_code == 404
    assert ticket_logs(request(username="owner"), ticket.id).status_code == 200
    assert ticket_survey(request("post", {"score": 5}, username="outsider"), ticket.id).status_code == 404
    assert ticket_survey(request("post", {"score": 5}, username="handler"), ticket.id).status_code == 403
    assert ticket_survey(request("post", {"score": 5}, username="owner"), ticket.id).status_code == 400
    response = ticket_form(request(permissions=["ticket-Add"]), ticket.workflow_version_id)
    assert response.status_code == 200
    assert json.loads(response.content)["data"]["schema"]["fields"][1]["key"] == "amount"


def test_proxy_delegate_and_superuser_are_explicit(sample):
    ticket, task = sample
    TicketProxy.objects.create(principal="handler", agent="delegate")
    service = TicketService()
    service.operate(ticket, task, "claim", {}, "delegate")
    task.refresh_from_db()
    assert task.assignee == "delegate"
    req = request(username="admin")
    assert ticket_detail(req, ticket.id).status_code == 404
    req.user.is_superuser = True
    assert ticket_detail(req, ticket.id).status_code == 200
    assert not Ticket.objects.visible_to("").exists()


def test_resource_permissions_ownership_and_domain(sample):
    from apps.itsm.views.extend import resource_item

    permissions = ["setting-Edit", "setting-View", "ticket_center_setting-Edit", "ticket_center_setting-View"]
    created = resources(request("post", {"principal": "owner", "agent": "handler"}, username="owner", permissions=permissions), "proxies")
    item_id = json.loads(created.content)["data"]["id"]
    assert resources(request(permissions=permissions), "proxies").status_code == 200
    assert resource_item(request("patch", {"is_enabled": False}, permissions=permissions), "proxies", item_id).status_code == 200
    assert resource_item(request("delete", permissions=permissions), "proxies", item_id).status_code == 200
    saved = resources(request("post", {"name": "我的视图"}, username="owner", permissions=permissions), "views")
    view_id = json.loads(saved.content)["data"]["id"]
    assert json.loads(resources(request(permissions=permissions), "views").content)["data"]["items"] == []
    assert resource_item(request("patch", {"name": "篡改"}, permissions=permissions), "views", view_id).status_code == 400


def test_authorized_partial_form_api_and_validation(sample):
    ticket, task = sample
    response = operate_ticket(request("post", {"task_id": task.id, "action": "save", "form_data": {"amount": 333}}, username="handler"), ticket.id)
    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.form_data["amount"] == 333
    assert operate_ticket(request("post", {"task_id": task.id, "action": "approve"}, username="owner"), ticket.id).status_code == 403
    assert tickets(request(payload={"page_size": "bad"})).status_code == 400


def test_trigger_status_changes_state(sample):
    ticket, _ = sample
    Trigger.objects.create(name="状态流转", event="ticket_update", action="status", config={"response": "processing"})
    fire_triggers(ticket, "ticket_update", "owner")
    ticket.refresh_from_db()
    assert ticket.status.key == "processing"


@pytest.mark.parametrize("kind", ["notice", "decision", "knowledge", "auto_dispatch"])
def test_external_node_business_effects(sample, kind):
    from apps.itsm.models import DecisionTable, KnowledgeArticle
    from apps.itsm.services.external_jobs import execute_node

    ticket, _ = sample
    if kind == "notice":
        with patch("apps.itsm.services.notify.service.dispatch_notification", return_value={"site": {"result": True}}) as notify:
            assert execute_node(ticket, {"id": "notice", "type": kind, "auto": {"receivers": ["owner"]}})["notified"]
            notify.assert_called_once()
    elif kind == "decision":
        table = DecisionTable.objects.create(name="金额路由", rules=[{"when": {"field": "amount", "op": ">", "value": 50}, "then": {"route": "high"}}])
        execute_node(ticket, {"type": kind, "auto": {"decision_id": table.id}})
        ticket.refresh_from_db()
        assert ticket.form_data["route"] == "high"
    elif kind == "knowledge":
        result = execute_node(ticket, {"type": kind, "auto": {"content": "知识正文"}})
        assert KnowledgeArticle.objects.get(id=result["article_id"]).content == "知识正文"
    else:
        with patch.object(TicketService, "_assignee_variables", return_value={"itsm_assignee_next": "handler"}):
            assert execute_node(ticket, {"type": kind})["variables"]["itsm_assignee_next"] == "handler"


def test_failed_ack_does_not_repeat_business_effect(sample):
    from unittest.mock import Mock

    from apps.itsm.flowable.client import FlowableError
    from apps.itsm.models import AutoExecution
    from apps.itsm.services.external_jobs import process_job

    ticket, _ = sample
    ticket.process_instance_id = "retry-ack"
    ticket.save()
    client = Mock()
    client.complete_external_job.side_effect = [FlowableError(503, ""), None]
    client.list_tasks_including_children.return_value = []
    client.get_process_instance.return_value = {"id": "retry-ack"}
    client._request.return_value = {}
    job = {"id": "retry-job", "processInstanceId": "retry-ack", "elementId": "approval_1"}
    with patch("apps.itsm.services.external_jobs.execute_node", return_value={"ok": True}) as action:
        assert not process_job(client, job)
        assert process_job(client, job)
        action.assert_called_once()
    assert AutoExecution.objects.get(ticket=ticket).status == "done"


def test_readonly_input_cannot_influence_computed_field(sample):
    ticket, task = sample
    fv = ticket.workflow.form.current_version
    fv.schema["fields"].append({"key": "copy", "type": "input"})
    fv.schema["rules"] = [{"type": "compute", "field": "copy", "expr": "secret"}]
    fv.save()
    TicketService().operate(ticket, task, "save", {"form_data": {"secret": "attack"}}, "handler")
    ticket.refresh_from_db()
    assert ticket.form_data["copy"] == "original"


def test_ticket_add_role_can_load_runtime_workflows_without_design_access(sample):
    from apps.itsm.views.tickets import ticket_workflows

    ticket, _ = sample
    workflow = ticket.workflow
    workflow.current_version = ticket.workflow_version
    workflow.save()
    response = ticket_workflows(request(permissions=["ticket-Add"]))
    assert response.status_code == 200
    assert json.loads(response.content)["data"]["items"][0]["current_version_id"] == ticket.workflow_version_id


def test_automatic_node_is_shown_completed_in_ticket_graph(sample):
    from apps.itsm.models import AutoExecution

    ticket, _ = sample
    version = ticket.workflow_version
    version.design["nodes"].append({"id": "auto_1", "type": "auto"})
    version.save()
    AutoExecution.objects.create(ticket=ticket, status="done", detail={"node_id": "auto_1"})
    data = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    assert next(node for node in data["nodes"] if node["id"] == "auto_1")["state"] == "done"


def test_hidden_field_is_not_serialized_to_handler(sample):
    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["field_perm"]["secret"] = "hidden"
    version.save()
    data = json.loads(ticket_detail(request(username="handler"), ticket.id).content)["data"]
    assert "secret" not in data["form_data"]
    assert "secret" not in [field["key"] for field in data["fields"]]


def test_hidden_table_cells_are_filtered_and_preserved_on_visible_edits(sample):
    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["field_perm"]["cost"] = "hidden"
    version.design["form_schema"] = {
        "fields": [
            {"key": "title", "type": "input"},
            {
                "key": "items",
                "type": "table",
                "children": [
                    {"key": "name", "label": "名称", "type": "input"},
                    {"key": "cost", "label": "成本", "type": "number"},
                    {"key": "memo", "label": "备注", "type": "input", "state": "hidden"},
                ],
            },
        ],
    }
    version.save(update_fields=["design"])
    ticket.form_data["items"] = [
        {"name": "第一行", "cost": 100, "memo": "隐藏备注一"},
        {"name": "第二行", "cost": 200, "memo": "隐藏备注二"},
    ]
    ticket.save(update_fields=["form_data"])

    result = json.loads(ticket_detail(request(username="handler"), ticket.id).content)["data"]
    assert [field["key"] for field in result["fields"][1]["children"]] == ["name"]
    first, second = result["form_data"]["items"]
    assert not ({"cost", "memo"} & (first.keys() | second.keys()))
    owner = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    assert owner["form_data"]["items"][1]["cost"] == 200

    payload = {"action": "save", "task_id": task.pk, "form_data": {"items": [{**second, "name": "已修改", "cost": 1}, {"name": "新行"}]}}
    assert operate_ticket(request("post", payload, username="handler"), ticket.id).status_code == 200
    ticket.refresh_from_db()
    assert ticket.form_data["items"] == [{"name": "已修改", "cost": 200, "memo": "隐藏备注二"}, {"name": "新行"}]

    assert operate_ticket(request("post", payload, username="handler"), ticket.id).status_code == 400
    ticket.refresh_from_db()
    assert ticket.form_data["items"][0]["name"] == "已修改"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_flowable_mutations_are_not_replayed_after_timeout(method):
    import requests

    from apps.itsm.flowable.client import FlowableClient, FlowableError

    client = FlowableClient("http://engine", "test", "test")
    with patch.object(client.session, "request", side_effect=requests.Timeout("timeout")) as send:
        with pytest.raises(FlowableError):
            client._request(method, "/test")
    assert send.call_count == 1


def test_suspend_blocks_progress_and_changes_engine_state(sample):
    from unittest.mock import Mock

    ticket, task = sample
    TicketStatus.objects.get_or_create(key="suspended", defaults={"name": "挂起"})
    ticket.process_instance_id = "process"
    ticket.save()
    client = Mock()
    service = TicketService(client)
    service.operate(ticket, task, "suspend", {}, "handler")
    client.set_process_suspended.assert_called_once_with("process", True)
    with pytest.raises(ValueError, match="挂起"):
        service.operate(ticket, task, "approve", {}, "handler")
    client.complete_task.assert_not_called()
    service.operate(ticket, task, "resume", {}, "handler")
    client.set_process_suspended.assert_called_with("process", False)
    ticket.refresh_from_db()
    assert ticket.status.key == "processing"


def test_invalid_service_binding_is_rejected_before_process_start(sample):
    from apps.itsm.models import Service

    ticket, _ = sample
    service = Service.objects.create(name="跨域服务", workflow=ticket.workflow, domain="other.example")
    with patch("apps.itsm.views.tickets._service") as factory:
        response = tickets(
            request(
                "post",
                {"workflow_version_id": ticket.workflow_version_id, "service_id": service.id, "form_data": {"title": "测试", "amount": 1}},
                username="owner",
                permissions=["ticket-View", "ticket-Add"],
            )
        )
    assert response.status_code == 404
    factory.assert_not_called()


@pytest.mark.parametrize(
    "action,event", [("save", "ticket_update"), ("return", "ticket_back"), ("urge", "ticket_urging"), ("finish", "ticket_finish")]
)
def test_remaining_trigger_event_aliases(sample, action, event):
    ticket, _ = sample
    Trigger.objects.create(name="事件", event=event, action="tag", config={"response": event})
    fire_triggers(ticket, action, "owner")
    assert ticket.tags.filter(name=event).exists()


@pytest.mark.parametrize(
    "view_name,permission",
    [
        ("forms", "form-View"),
        ("form_detail", "form-View"),
        ("workflows", "workflow-View"),
        ("dictionaries", "data-View"),
        ("basic_settings", "setting-View"),
    ],
)
def test_configuration_read_permission_cannot_write(sample, view_name, permission):
    from apps.itsm.views import api

    args = [sample[0].workflow.form_id] if view_name == "form_detail" else []
    req = request("put" if args else "post", {"name": "unauthorized", "key": "unauthorized", "schema": {"fields": []}}, permissions=[permission])
    assert getattr(api, view_name)(req, *args).status_code == 403


@pytest.mark.parametrize(
    "view_name,id_source,permission", [("form_detail", "form_id", "form-View"), ("workflow_design", "workflow_id", "workflow-Edit")]
)
def test_design_cross_domain_is_hidden(sample, view_name, id_source, permission):
    from apps.itsm.views import api

    ticket, _ = sample
    identity = ticket.workflow.form_id if id_source == "form_id" else ticket.workflow_id
    response = getattr(api, view_name)(request(domain="other.example", permissions=[permission]), identity)
    assert response.status_code == 404


def test_portal_and_data_tables_are_domain_scoped(sample):
    from apps.itsm.models import DataTable, Service
    from apps.itsm.views.m2 import data_tables
    from apps.itsm.views.services import service_portal, service_use

    ticket, _ = sample
    service = Service.objects.create(name="外域", workflow=ticket.workflow, domain="other.example")
    DataTable.objects.create(name="外域", key="foreign", domain="other.example")
    assert json.loads(service_portal(request(permissions=["portal-View"])).content)["data"]["services"] == []
    assert service_use(request("post", permissions=["portal-View"]), service.id).status_code == 404
    assert json.loads(data_tables(request(permissions=["data-View"])).content)["data"]["items"] == []


def test_detail_actions_match_actor_and_state(sample):
    ticket, task = sample

    def detail(user):
        return json.loads(ticket_detail(request(username=user), ticket.id).content)["data"]

    assert "withdraw" in detail("owner")["allowed_actions"]
    assert "suspend" not in detail("owner")["allowed_actions"]
    assert "suspend" in detail("handler")["allowed_actions"]
    assert "withdraw" not in detail("handler")["allowed_actions"]
    ticket.status = TicketStatus.objects.create(key="suspended", name="挂起")
    ticket.save()
    assert detail("handler")["tasks"][0]["can_operate"] is False
    assert "resume" in detail("handler")["allowed_actions"]


def test_full_form_draft_roundtrip_and_user_isolation(sample):
    from apps.itsm.views.m2 import portal_draft

    values = {"title": "草稿", "amount": 25, "items": [{"name": "资源"}]}
    response = portal_draft(request("post", {"service_id": 1, "form_data": values}, username="owner", permissions=["portal-View"]))
    assert response.status_code == 200
    data = json.loads(portal_draft(request(username="owner", permissions=["portal-View"])).content)["data"]
    assert data["items"]["1"] == values
    data = json.loads(portal_draft(request(username="handler", permissions=["portal-View"])).content)["data"]
    assert data["items"] == {}


def test_configuration_authorized_domain_roundtrip():
    from apps.itsm.views import api, m2

    domain = "tenant.example"
    perms = [
        "form-View",
        "form-Add",
        "form-Edit",
        "form-Publish",
        "workflow-View",
        "workflow-Add",
        "workflow-Edit",
        "data-View",
        "data-Edit",
        "data-Add",
        "setting-View",
        "setting-Edit",
    ]

    def call(view, method="get", payload=None, *args):
        response = view(request(method, payload, "designer", perms, domain), *args)
        assert response.status_code == 200, response.content
        return json.loads(response.content)["data"]

    form_id = call(api.forms, "post", {"name": "申请表", "key": "form"})["id"]
    schema = {"fields": [{"key": "title", "type": "input", "required": True}]}
    call(api.form_detail, "put", {"schema": schema}, form_id)
    call(api.publish_form, "post", {"schema": schema, "sample": {"title": "样例"}}, form_id)
    assert call(api.form_versions, "get", {}, form_id)["count"] == 2
    assert call(api.forms)["count"] == 1
    assert call(api.preview_form, "post", {"data": {}}, form_id)["errors"]["title"]
    workflow_id = call(api.workflows, "post", {"name": "流程", "key": "flow", "form_id": form_id})["id"]
    design = {"nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}], "edges": [{"from": "start", "to": "end"}]}
    call(api.workflow_design, "post", design, workflow_id)
    call(api.workflow_design, "post", design, workflow_id)
    assert call(api.workflows)["items"][0]["form_id"] == form_id
    assert call(m2.workflow_export, "get", {}, workflow_id)["design"] == design
    dictionary_id = call(api.dictionaries, "post", {"name": "字典", "key": "dict"})["id"]
    call(api.dictionaries, "post", {"id": dictionary_id, "name": "更新字典"})
    call(api.dictionary_items, "post", {"key": "one", "label": "一"}, dictionary_id)
    assert call(api.dictionary_items, "get", {}, dictionary_id)["items"][0]["label"] == "一"
    table_id = call(m2.data_tables, "post", {"name": "数据", "key": "data", "fields": [{"key": "title"}]})["id"]
    call(m2.data_table_rows, "post", {"data": {"title": "内容"}}, table_id)
    assert call(m2.data_table_rows, "get", {}, table_id)["items"][0]["data"] == {"title": "内容"}
    call(api.basic_settings, "post", {"product_name": "租户服务"})
    assert call(api.basic_settings)["product_name"] == "租户服务"
    assert FormModel.objects.get(id=form_id).domain == domain
    assert Workflow.objects.get(id=workflow_id).domain == domain


def test_service_catalog_and_configuration_crud_is_scoped(sample):
    from apps.itsm.views.services import CatalogView, ServiceView, service_favorite, service_hot, service_use

    ticket, _ = sample
    ticket.workflow.current_version = ticket.workflow_version
    ticket.workflow.save()
    perms = ["workflow-Edit", "portal-View"]

    def call(cls, method, payload):
        req = request(method, payload, "designer", perms)
        req.data = payload
        response = getattr(cls(), method)(req)
        assert response.status_code == 200, getattr(response, "content", None)
        return response.data

    catalog = call(CatalogView, "post", {"name": "服务目录"})["id"]
    service = call(ServiceView, "post", {"name": "申请", "workflow_id": ticket.workflow_id, "catalog_id": catalog, "is_hot": True})["id"]
    assert call(ServiceView, "get", {})["items"][0]["id"] == service
    call(ServiceView, "post", {"id": service, "name": "更新"})
    call(CatalogView, "post", {"id": catalog, "name": "更新目录"})
    assert call(CatalogView, "get", {})["items"][0]["name"] == "更新目录"
    for view in [service_favorite, service_use]:
        assert view(request("post", permissions=perms), service).status_code == 200
    assert json.loads(service_hot(request(permissions=perms)).content)["data"]["items"][0]["id"] == service
    foreign = request("delete", permissions=perms, domain="foreign.example")
    foreign.GET = {"id": service}
    assert ServiceView().delete(foreign).status_code == 404
    req = request("delete", permissions=perms)
    req.GET = {"id": service}
    assert ServiceView().delete(req).status_code == 200
    req.GET = {"id": catalog}
    assert CatalogView().delete(req).status_code == 200


@pytest.mark.parametrize("status,expected", [(200, "done"), (302, "failed"), (500, "failed")])
def test_http_automatic_action_does_not_follow_redirects(status, expected):
    from unittest.mock import Mock

    from apps.itsm.services.auto_runner import _run_http

    with (
        patch("apps.itsm.services.auto_runner.SSRFValidator"),
        patch("apps.itsm.services.auto_runner.requests.request", return_value=Mock(status_code=status)) as send,
    ):
        assert _run_http({"url": "https://public.example"})[0] == expected
        assert send.call_args.kwargs["allow_redirects"] is False


def test_published_workflow_uses_its_form_snapshot(sample):
    ticket, _ = sample
    snapshot = {"fields": [{"key": "title", "type": "input", "required": True}]}
    version = ticket.workflow_version
    version.design = {**version.design, "form_schema": snapshot}
    version.save()
    created = TicketService().create(version, {"title": "旧版申请"}, "owner")
    assert created.form_data == {"title": "旧版申请"}
    data = json.loads(ticket_detail(request(username="owner"), created.id).content)["data"]
    assert [field["key"] for field in data["fields"]] == ["title"]


def test_foreign_data_table_cannot_be_deleted_by_row_endpoint(sample):
    from apps.itsm.models import DataTable, DataTableRow
    from apps.itsm.views.m2 import data_table_row_delete

    table = DataTable.objects.create(name="外域", key="foreign", domain="foreign.example")
    row = DataTableRow.objects.create(table=table, data={"secret": "private"})
    response = data_table_row_delete(request("post", {"ids": [row.id]}, permissions=["data-Edit"]), table.id)
    assert response.status_code == 404
    assert DataTableRow.objects.filter(id=row.id).exists()


def test_invalid_status_transition_never_stops_engine(sample):
    from unittest.mock import Mock

    from apps.itsm.models import StatusTransition

    ticket, task = sample
    StatusTransition.objects.create(from_status=ticket.status, to_status=TicketStatus.objects.get(key="processing"), name="仅响应")
    ticket.process_instance_id = "live"
    ticket.save()
    client = Mock()
    with pytest.raises(ValueError):
        TicketService(client).operate(ticket, task, "close", {}, "handler")
    client.delete_process_instance.assert_not_called()


def test_sla_read_permission_cannot_modify_calendar():
    from apps.itsm.views.m2 import sla_settings

    assert sla_settings(request("post", {"kind": "calendar", "name": "unauthorized"}, permissions=["workflow-View"])).status_code == 403


def test_handover_updates_engine_and_claimed_local_task(sample):
    from unittest.mock import Mock

    from apps.itsm.models.extend import Handover
    from apps.itsm.views.extend import _apply_handover
    from apps.system_mgmt.models import User

    ticket, task = sample
    User.objects.create(domain=ticket.domain, username="replacement", display_name="接替处理人")
    task.flowable_task_id = "engine-task"
    task.status = "claimed"
    task.save()
    handover = Handover.objects.create(from_user="handler", to_user="replacement", ticket_ids=[ticket.id])
    client = Mock()
    with patch("apps.itsm.views.extend._service", return_value=TicketService(client)):
        _apply_handover(handover)
    client.update_task_assignee.assert_called_once_with("engine-task", "replacement")
    task.refresh_from_db()
    assert task.assignee == "replacement"


def test_print_escapes_ticket_values_and_ignores_stored_template(sample):
    from apps.itsm.models.extend import PrintTemplate
    from apps.itsm.views.ticket_operations import render_print

    ticket, _ = sample
    ticket.title = "<img src=x onerror=alert(1)>"
    ticket.save()
    template = PrintTemplate.objects.create(name="打印", body="{{ title.__class__.__mro__ }}")
    response = render_print(request(payload={"template_id": template.id}, username="owner"), ticket.id)
    assert response.status_code == 200
    html = json.loads(response.content)["data"]["html"]
    assert "<h1>&lt;img src=x onerror=alert(1)&gt;</h1>" in html
    assert "<img" not in html
