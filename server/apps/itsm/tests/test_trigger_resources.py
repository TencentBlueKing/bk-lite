import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve

from apps.itsm.models import FormModel, FormVersion, Service, Ticket, TicketStatus, Trigger, TriggerLog, Workflow, WorkflowVersion
from apps.itsm.services.trigger_config import scope_matches
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.extend import resource_item, resources

pytestmark = pytest.mark.django_db

RULE_WRITE = ["rule-Add", "rule-Edit", "rule-View", "rule-Delete"]


def response_data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def get(path, *, permissions, username="owner", domain="domain.com", query=None):
    match = resolve(path)
    return match.func(request("get", query, permissions=permissions, username=username, domain=domain), **match.kwargs)


def make_rule(config):
    return {"name": "触发规则", "event": "ticket_create", "config": config}


@pytest.mark.parametrize(
    "config",
    [
        {"actions": [{"type": "status", "value": "missing"}]},
        {"actions": [{"type": "status", "value": "finished"}]},
        {"actions": [{"type": "status", "value": "suspended"}]},
        {"actions": [{"type": "tag", "value": "  "}]},
        {"actions": [{"type": "notice", "value": " "}]},
        {"actions": []},
        {"actions": {"type": "tag", "value": "测试"}},
        {"when": {"logic": "bad", "items": [{"field": "title", "op": "=", "value": "测试"}]}, "actions": [{"type": "tag", "value": "测试"}]},
        {"when": {"logic": "and", "items": []}, "actions": [{"type": "tag", "value": "测试"}]},
        {"when": {"logic": "or", "items": [None]}, "actions": [{"type": "tag", "value": "测试"}]},
        {"when": {"field": "title", "op": "bad", "value": "测试"}, "actions": [{"type": "tag", "value": "测试"}]},
        {"when": {"field": "title", "op": "in", "value": "测试"}, "actions": [{"type": "tag", "value": "测试"}]},
        {"scope": {"mode": "include"}, "actions": [{"type": "tag", "value": "测试"}]},
        {"scope": {"mode": "exclude", "service_ids": [True]}, "actions": [{"type": "tag", "value": "测试"}]},
    ],
)
def test_invalid_trigger_configuration_cannot_be_stored(config):
    TicketStatus.objects.create(key="finished", name="完结", is_terminal=True)
    TicketStatus.objects.create(key="suspended", name="挂起")
    response = resources(request("post", make_rule(config), permissions=RULE_WRITE), "triggers")
    assert response.status_code == 400
    assert not Trigger.objects.exists()


def test_trigger_configuration_validates_domain_and_preserves_action_order():
    form = FormModel.objects.create(name="申请单", key="apply")
    workflow = Workflow.objects.create(name="申请流程", key="apply", form=form)
    service = Service.objects.create(name="申请入口", workflow=workflow)
    unrelated = Service.objects.create(name="其他组织入口", workflow=workflow, domain="another.example")
    actions = [{"type": "tag", "value": "待核实"}, {"type": "notice", "value": "请核实"}, {"type": "tag", "value": "已提醒"}]
    config = {
        "scope": {"mode": "include", "form_ids": [form.id], "workflow_ids": [workflow.id], "service_ids": [service.id, service.id]},
        "when": {
            "logic": "and",
            "items": [
                {"field": "title", "op": "eq", "value": "申请"},
                {"logic": "or", "items": [{"field": "comment", "op": "is_empty"}]},
            ],
        },
        "actions": actions,
    }
    data = response_data(resources(request("post", make_rule(config), permissions=RULE_WRITE), "triggers"))
    assert data["config"]["actions"] == actions
    assert data["config"]["scope"]["service_ids"] == [service.id]
    assert data["config"]["when"]["items"][0]["op"] == "="
    config["scope"]["service_ids"] = [unrelated.id]
    response = resource_item(request("patch", {"config": config}, permissions=RULE_WRITE), "triggers", data["id"])
    assert response.status_code == 400
    assert Trigger.objects.get(id=data["id"]).config["scope"]["service_ids"] == [service.id]


def test_legacy_rule_can_be_disabled_then_requires_repair_before_enable():
    legacy = Trigger.objects.create(name="旧规则", event="ticket_create", action="status", config={"response": "missing"})
    disabled = resource_item(request("put", {"is_enabled": False}, permissions=RULE_WRITE), "triggers", legacy.id)
    assert response_data(disabled)["is_enabled"] is False
    enabled = resource_item(request("put", {"is_enabled": True}, permissions=RULE_WRITE), "triggers", legacy.id)
    assert enabled.status_code == 400
    assert not Trigger.objects.get(pk=legacy.pk).is_enabled
    repaired = resource_item(
        request("put", {"action": "tag", "config": {"response": "旧标签", "when": {"field": "", "op": "eq", "value": ""}}}, permissions=RULE_WRITE),
        "triggers",
        legacy.id,
    )
    assert response_data(repaired)["config"]["actions"] == [{"type": "tag", "value": "旧标签"}]
    enabled = resource_item(request("put", {"is_enabled": True}, permissions=RULE_WRITE), "triggers", legacy.id)
    assert response_data(enabled)["is_enabled"] is True


def test_trigger_permissions_and_same_domain_options():
    form = FormModel.objects.create(name="申请单", key="apply")
    workflow = Workflow.objects.create(name="申请流程", key="apply", form=form)
    service = Service.objects.create(name="申请入口", workflow=workflow)
    remote = Workflow.objects.create(name="其他组织流程", key="apply", domain="another.example")
    TicketStatus.objects.create(key="processing", name="本域处理中")
    TicketStatus.objects.create(key="suspended", name="挂起")
    TicketStatus.objects.create(key="external", name="其他域状态", domain=remote.domain)
    payload = response_data(resources(request("get", permissions=["rule-View"]), "triggers"))
    assert all(payload[flag] is False for flag in ("can_add", "can_edit", "can_delete"))
    denied = resources(request("post", make_rule({"actions": [{"type": "tag", "value": "保留"}]}), permissions=["rule-View"]), "triggers")
    assert denied.status_code == 403
    assert get("/api/v1/itsm/api/triggers/options/", permissions=["ticket-View"]).status_code == 403
    data = response_data(get("/api/v1/itsm/api/triggers/options/", permissions=["rule-View"]))
    assert data["workflows"] == [{"id": workflow.id, "name": workflow.name}]
    assert data["forms"] == [{"id": form.id, "name": form.name}]
    assert data["services"] == [{"id": service.id, "name": service.name}]
    assert data["statuses"] == [{"key": "processing", "name": "本域处理中"}]


def test_condition_field_options_use_published_snapshots_and_domain_metadata():
    form = FormModel.objects.create(name="申请表单", key="apply")
    version = FormVersion.objects.create(
        form=form,
        version_no=1,
        is_published=True,
        schema={"fields": [{"key": "template_field", "label": "模板备注", "type": "textarea"}]},
    )
    form.current_version = version
    form.save(update_fields=["current_version"])
    replacement = FormModel.objects.create(name="替换后的表单", key="replacement")
    workflow = Workflow.objects.create(name="申请流程", key="apply", form=replacement)
    current = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        is_published=True,
        design={
            "form_model_id": form.id,
            "form_schema": {
                "fields": [
                    {"key": "status", "label": "申请状态", "type": "radio", "source": {"options": [{"label": "通过", "value": "pass"}]}},
                    {"key": "amount", "label": "金额", "type": "number", "default": 42},
                    {
                        "key": "asset",
                        "label": "关联资产",
                        "type": "select",
                        "fetch": {"mode": "options", "snapshot": {"url": "internal"}},
                        "source": {"options": [{"label": "默认示例", "value": "demo"}]},
                    },
                    {"key": "section", "type": "section", "children": [{"key": "flags", "label": "特征", "type": "multiselect"}]},
                    {"key": "hidden", "type": "input", "state": "hidden"},
                    {"key": "approval_notes", "label": "审批说明", "type": "input"},
                    {"key": "table", "type": "table", "children": [{"key": "column", "type": "input"}]},
                    {"key": "manual_notes", "type": "description"},
                ]
            },
            "nodes": [
                {"type": "submit", "field_perm": {"approval_notes": "hidden"}},
                {"type": "approval", "field_perm": {"approval_notes": "edit"}},
            ],
        },
    )
    workflow.current_version = current
    workflow.save(update_fields=["current_version"])
    WorkflowVersion.objects.create(workflow=workflow, version_no=2, design={"form_schema": {"fields": [{"key": "draft", "type": "input"}]}})
    legacy = Workflow.objects.create(name="旧流程", key="legacy", form=form)
    legacy.current_version = WorkflowVersion.objects.create(workflow=legacy, version_no=1, is_published=True)
    legacy.save(update_fields=["current_version"])
    service = Service.objects.create(name="申请服务", workflow=workflow)
    Service.objects.create(name="其他组织服务", workflow=workflow, domain="other.example")
    foreign_form = FormModel.objects.create(name="其他组织表单", key="other", domain="other.example")
    foreign_version = FormVersion.objects.create(
        form=foreign_form,
        version_no=1,
        is_published=True,
        domain=foreign_form.domain,
        schema={"fields": [{"key": "foreign", "type": "input"}]},
    )
    FormModel.objects.filter(id=foreign_form.id).update(current_version=foreign_version)
    forged = Workflow.objects.create(name="异常流程", key="forged", form=foreign_form)
    foreign_workflow = Workflow.objects.create(name="其他组织流程", key="other", domain=foreign_form.domain)
    foreign_flow_version = WorkflowVersion.objects.create(
        workflow=foreign_workflow, version_no=1, domain=foreign_form.domain, is_published=True, design={"form_schema": foreign_version.schema}
    )
    Workflow.objects.filter(id=forged.id).update(current_version=foreign_flow_version)
    Workflow.objects.filter(id=foreign_workflow.id).update(current_version=foreign_flow_version)
    TicketStatus.objects.create(key="finished", name="已完结", is_terminal=True)
    TicketStatus.objects.create(key="external", name="其他域状态", domain=foreign_form.domain)

    path = "/api/v1/itsm/api/triggers/options/"
    with CaptureQueriesContext(connection) as queries:
        data = response_data(get(path, permissions=["rule-View"]))
    system_fields = {field["key"]: field for field in data["system_fields"]}
    assert set(system_fields) == {
        "$ticket.sn",
        "$ticket.title",
        "$ticket.status",
        "$ticket.creator",
        "$ticket.workflow_id",
        "$ticket.service_id",
        "$ticket.is_test",
    }
    assert system_fields["$ticket.status"]["options"] == [{"label": "已完结", "value": "finished"}]
    assert system_fields["$ticket.service_id"]["options"] == [{"label": service.name, "value": service.id}]
    assert data["statuses"] == []
    groups = {(group.get("workflow_id"), group.get("form_id")): group for group in data["form_field_groups"]}
    template_fields = [{"key": "$form.template_field", "label": "模板备注", "type": "text"}]
    assert set(groups) == {(workflow.id, form.id), (legacy.id, form.id), (None, form.id)}
    assert groups[(workflow.id, form.id)] == {
        "name": workflow.name,
        "workflow_id": workflow.id,
        "form_id": form.id,
        "service_ids": [service.id],
        "fields": [
            {"key": "$form.status", "label": "申请状态", "type": "text", "options": [{"label": "通过", "value": "pass"}]},
            {"key": "$form.amount", "label": "金额", "type": "number"},
            {"key": "$form.asset", "label": "关联资产", "type": "text"},
            {"key": "$form.flags", "label": "特征", "type": "list"},
            {"key": "$form.approval_notes", "label": "审批说明", "type": "text"},
        ],
    }
    assert groups[(legacy.id, form.id)]["fields"] == groups[(None, form.id)]["fields"] == template_fields

    extra = Workflow.objects.create(name="新增流程", key="extra", form=form)
    extra.current_version = WorkflowVersion.objects.create(workflow=extra, version_no=1, is_published=True)
    extra.save(update_fields=["current_version"])
    with CaptureQueriesContext(connection) as expanded:
        response_data(get(path, permissions=["rule-View"]))
    assert len(queries) == len(expanded)


def test_trigger_history_survives_rule_deletion_and_checks_ticket_visibility():
    workflow = Workflow.objects.create(name="流程", key="wf")
    ticket = Ticket.objects.create(sn="T-1", title="申请", workflow=workflow, creator="owner")
    trigger = Trigger.objects.create(name="规则", event="ticket_create")
    succeeded = TriggerLog.objects.create(
        trigger=trigger,
        ticket_id=ticket.id,
        trigger_name=trigger.name,
        event=trigger.event,
        action="tag",
        position=1,
        status="success",
        message="已打标签",
    )
    failed = TriggerLog.objects.create(
        trigger=trigger,
        ticket_id=ticket.id,
        trigger_name=trigger.name,
        event=trigger.event,
        action="status",
        run_id=succeeded.id,
        position=2,
        status="failed",
        message="状态不允许",
    )
    TriggerLog.objects.filter(pk=succeeded.id).update(run_id=succeeded.id)
    latest = TriggerLog.objects.create(ticket_id=ticket.id, trigger_name="另一次触发")
    TriggerLog.objects.create(ticket_id=ticket.id, domain="another.example", trigger_name="外域脏记录")
    trigger.delete()

    path = f"/api/v1/itsm/api/tickets/{ticket.id}/trigger-logs/"
    assert get(path, permissions=["rule-View"]).status_code == 403
    assert get(path, permissions=["ticket-View"], username="outsider").status_code == 404
    assert get(path, permissions=["ticket-View"], domain="another.example").status_code == 404
    data = response_data(get(path, permissions=["ticket-View"], query={"page_size": 2}))
    assert data["count"] == 3
    assert [row["id"] for row in data["items"]] == [latest.id, succeeded.id]
    older = response_data(get(path, permissions=["ticket-View"], query={"page_size": 2, "page": 2}))
    assert older["items"] == [
        {
            "id": failed.id,
            "run_id": succeeded.id,
            "trigger_name": "规则",
            "event": "ticket_create",
            "action": "status",
            "position": 2,
            "status": "failed",
            "message": "状态不允许",
            "created_at": failed.created_at.isoformat(),
        }
    ]


def test_form_scope_uses_the_ticket_version_form_snapshot():
    original_form = FormModel.objects.create(name="原表单", key="original")
    updated_form = FormModel.objects.create(name="更换后表单", key="updated")
    workflow = Workflow.objects.create(name="流程", key="wf", form=original_form)
    published = WorkflowVersion.objects.create(workflow=workflow, version_no=1, design={"form_model_id": original_form.id})
    legacy = WorkflowVersion.objects.create(workflow=workflow, version_no=2, design={})
    custom = WorkflowVersion.objects.create(workflow=workflow, version_no=3, design={"form_model_id": None})
    ticket = Ticket.objects.create(sn="T-1", title="申请", workflow=workflow, workflow_version=published, creator="owner")
    workflow.form = updated_form
    workflow.save(update_fields=["form"])
    ticket.refresh_from_db()

    original_scope = {"mode": "include", "form_ids": [original_form.id]}
    updated_scope = {"mode": "include", "form_ids": [updated_form.id]}
    assert scope_matches(original_scope, ticket)
    assert not scope_matches(updated_scope, ticket)
    ticket.workflow_version = legacy
    assert scope_matches(updated_scope, ticket)
    ticket.workflow_version = custom
    assert not scope_matches(updated_scope, ticket)


def test_trigger_catalog_fetches_bounded_pages_and_preserves_saved_choices():
    workflows = [Workflow.objects.create(name=f"流程 {i}", key=f"flow-{i}") for i in range(4)]
    forms = [FormModel.objects.create(name=f"表单 {i}", key=f"form-{i}") for i in range(4)]
    for i, workflow in enumerate(workflows):
        version = WorkflowVersion.objects.create(
            workflow=workflow, version_no=1, is_published=True,
            design={"form_schema": {"fields": [{"key": f"memo{i}", "type": "input"}]}},
        )
        Workflow.objects.filter(pk=workflow.pk).update(current_version=version, form=forms[i])
    services = [Service.objects.create(name=f"服务 {i}", workflow=workflow) for i, workflow in enumerate(reversed(workflows))]
    outsider = Workflow.objects.create(name="外组织", key="foreign", domain="foreign.example")
    path = "/api/v1/itsm/api/triggers/options/"
    selected = {"workflows": [workflows[3].pk, outsider.pk], "services": [services[3].pk]}
    first = response_data(get(path, permissions=["rule-View"], query={"page_size": 1, "selected": json.dumps(selected)}))
    assert first["has_more"]
    assert [row["id"] for row in first["workflows"]] == [workflows[0].pk, workflows[3].pk]
    assert [row["id"] for row in first["forms"]] == [forms[0].pk]
    assert [row["id"] for row in first["services"]] == [services[0].pk, services[3].pk]
    fields = {group["workflow_id"]: group for group in first["form_field_groups"]}
    assert fields[workflows[3].pk]["service_ids"] == [services[0].pk]
    assert fields[workflows[3].pk]["form_id"] == forms[3].pk
    assert fields[workflows[3].pk]["fields"][0]["key"] == "$form.memo3"

    second = response_data(get(path, permissions=["rule-View"], query={"page_size": 1, "page": 2}))
    assert [row["id"] for row in second["workflows"]] == [workflows[1].pk]
    last = response_data(get(path, permissions=["rule-View"], query={"page_size": 1, "page": 4}))
    assert not last["has_more"]
    assert [row["id"] for row in last["workflows"]] == [workflows[3].pk]
    assert get(path, permissions=["rule-View"], query={"page_size": "-1"}).status_code == 400


@pytest.mark.django_db
def test_person_field_lookup_reads_selected_published_workflow():
    from apps.itsm.models import Workflow, WorkflowVersion
    from apps.itsm.services.trigger_fields import scoped_person_field_keys

    flows = []
    for key in ("selected", "other"):
        flow = Workflow.objects.create(key=key, name=key)
        version = WorkflowVersion.objects.create(workflow=flow, version_no=1, is_published=True, design={"form_schema": {"fields": [{"type": "user", "key": key}]}})
        flow.current_version = version
        flow.save()
        flows.append(flow)
    assert scoped_person_field_keys(flows[0].domain, {"mode": "include", "workflow_ids": [flows[0].id]}, {"selected", "other"}) == {"selected"}
