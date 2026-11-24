from unittest.mock import Mock, patch

import pytest

from apps.console_mgmt.models import Notification
from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import FormModel, Service, StatusTransition, TicketStatus, TicketTask, Trigger, TriggerLog, Workflow, WorkflowVersion
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.services.triggers import fire_triggers

pytestmark = pytest.mark.django_db
DOMAIN = "trigger.example"


@pytest.fixture
def workflow():
    for key in ["new", "processing", "finished", "terminated", "cancelled", "suspended"]:
        TicketStatus.objects.create(key=key, name=key, domain=DOMAIN)
    form = FormModel.objects.create(name="验收表单", key="trigger_form", domain=DOMAIN)
    flow = Workflow.objects.create(name="验收流程", key="trigger_flow", form=form, domain=DOMAIN)
    return WorkflowVersion.objects.create(workflow=flow, version_no=1, design={"nodes": [{"id": "submit", "type": "submit"}]}, domain=DOMAIN)


def make_rule(event, *, config, action="tag", name="验收规则", domain=DOMAIN):
    return Trigger.objects.create(name=name, event=event, action=action, config=config, domain=domain)


def test_legacy_equals_and_empty_condition_are_evaluated(workflow):
    make_rule("ticket_create", config={"when": {"field": "title", "op": "eq", "value": "服务申请"}, "response": "标题命中"})
    make_rule("ticket_create", config={"when": {"field": "", "op": "eq", "value": ""}, "response": "不限条件"})
    make_rule("ticket_create", config={"when": {"field": "title", "op": "eq", "value": "其他标题"}, "response": "不可命中"})

    ticket = TicketService().create(workflow, {"title": "服务申请"}, "owner", is_test=True)

    assert set(ticket.tags.values_list("name", flat=True)) == {"标题命中", "不限条件"}


def test_system_and_form_condition_namespaces_match_without_changing_legacy_rules(workflow):
    service = Service.objects.create(name="申请服务", workflow=workflow.workflow, domain=DOMAIN)
    ticket = TicketService().create(workflow, {"title": "工单标题"}, "owner", is_test=True, service=service)
    task = TicketTask.objects.create(ticket=ticket, node_id="submit", assignee="owner")
    form_values = {"title": "不同的表单标题", "status": "表单状态", "amount": 20, "flags": ["A", "B"]}
    expected_fields = {
        "$ticket.sn": ticket.sn,
        "$ticket.title": "工单标题",
        "$ticket.status": "new",
        "$ticket.creator": "owner",
        "$ticket.workflow_id": workflow.workflow_id,
        "$ticket.service_id": service.id,
        "$ticket.is_test": True,
        "$form.status": "表单状态",
        "$form.title": "不同的表单标题",
        "$form.amount": 20,
        "status": "new",
        "title": "不同的表单标题",
    }
    for field, value in expected_fields.items():
        make_rule("ticket_update", config={"when": {"field": field, "op": "=", "value": value}, "response": field})
    make_rule("ticket_update", config={"when": {"field": "$form.flags", "op": "contains", "value": "A"}, "response": "列表子项"})
    make_rule("ticket_update", config={"when": {"field": "$form.amount", "op": "=", "value": "20"}, "response": "类型不同"})
    make_rule("ticket_update", config={"when": {"field": "status", "op": "=", "value": "表单状态"}, "response": "错误的状态"})

    updated = TicketService().operate(ticket, task, "save", {"form_data": form_values}, "owner")

    assert set(updated.tags.values_list("name", flat=True)) == {*expected_fields, "列表子项"}


def test_ordered_actions_and_legacy_invalid_config_do_not_block_saving(workflow):
    make_rule("ticket_update", config={"when": {"field": "amount", "op": "contains", "value": "x"}, "response": "不可命中"})
    ordered = make_rule(
        "ticket_update",
        config={
            "actions": [
                {"type": "status", "value": "missing_status"},
                {"type": "status", "value": "processing"},
                {"type": "tag", "value": "本规则继续执行"},
            ]
        },
    )
    make_rule("ticket_update", config={"when": {"field": "status", "op": "=", "value": "processing"}, "response": "后续规则已执行"})
    ticket = TicketService().create(workflow, {"title": "申请", "amount": 3}, "owner", is_test=True)
    task = TicketTask.objects.create(ticket=ticket, node_id="submit", assignee="owner")

    updated = TicketService().operate(ticket, task, "save", {"form_data": {"amount": 6}}, "owner")
    assert updated.status.key == "processing" and updated.form_data["amount"] == 6
    assert set(updated.tags.values_list("name", flat=True)) == {"本规则继续执行", "后续规则已执行"}
    entries = TriggerLog.objects.filter(ticket_id=ticket.pk, trigger=ordered).order_by("position")
    assert list(entries.values_list("position", "action", "status")) == [(1, "status", "failed"), (2, "status", "success"), (3, "tag", "success")]
    assert len(set(entries.values_list("run_id", flat=True))) == 1 and entries.first().run_id == entries.first().pk
    assert TriggerLog.objects.filter(ticket_id=ticket.pk, status="failed", position__isnull=True).exists()


def test_scope_and_nested_conditions_use_service_at_create_and_first_node(workflow):
    entry_service = Service.objects.create(name="验收服务", workflow=workflow.workflow, domain=DOMAIN)
    other = Service.objects.create(name="其他服务", workflow=workflow.workflow, domain=DOMAIN)
    scope = {
        "mode": "include",
        "service_ids": [entry_service.id],
        "form_ids": [workflow.workflow.form_id],
        "workflow_ids": [workflow.workflow_id],
    }
    when = {
        "logic": "and",
        "items": [
            {"field": "title", "op": "=", "value": "申请"},
            {"logic": "or", "items": [{"field": "amount", "op": ">=", "value": 10}, {"field": "urgent", "op": "=", "value": True}]},
        ],
    }
    make_rule("ticket_create", config={"scope": scope, "when": when, "response": "包含"})
    make_rule("activity_into", config={"scope": scope, "when": when, "response": "首节点"})
    make_rule("ticket_create", config={"scope": {**scope, "mode": "exclude"}, "response": "排除"})
    make_rule("ticket_create", domain="another.example", config={"response": "跨组织"})
    client = Mock()
    client.start_process.return_value = {"id": "flowable-process"}
    client.list_tasks_including_children.return_value = [{"id": "runtime-task", "taskDefinitionKey": "submit", "assignee": "owner"}]
    workflow.process_definition_id = "test:1:stable"
    workflow.process_definition_key = workflow.workflow.key
    engine = TicketService(client)

    matching = engine.create(workflow, {"title": "申请", "amount": 0, "urgent": True}, "owner", is_test=True, service=entry_service)
    excluding = engine.create(workflow, {"title": "申请", "amount": 12}, "owner", is_test=True, service=other)
    failing = engine.create(workflow, {"title": "其他", "amount": 0}, "owner", is_test=True, service=entry_service)

    assert set(matching.tags.values_list("name", flat=True)) == {"包含", "首节点"}
    assert list(excluding.tags.values_list("name", flat=True)) == ["排除"]
    assert not failing.tags.exists()


@pytest.mark.parametrize("operation", ["submit", "reconcile", "close", "terminate", "withdraw"])
def test_flowable_end_is_distinct_from_manual_stop_and_runs_once(workflow, operation):
    make_rule("ticket_end", config={"response": "流程自然结束"})
    make_rule("ticket_finish", config={"response": "已经完结"})
    ticket = TicketService().create(workflow, {"title": "申请"}, "owner", is_test=True)
    ticket.process_instance_id = "runtime-process"
    ticket.save(update_fields=["process_instance_id"])
    task = TicketTask.objects.create(ticket=ticket, node_id="submit", assignee="owner", flowable_task_id="active-task")
    client = Mock()
    client.get_process_instance.side_effect = FlowableError(404, "")
    client.list_tasks_including_children.return_value = []
    service = TicketService(client)

    if operation == "reconcile":
        service.finish_if_ended(ticket)
    else:
        service.operate(ticket, task if operation == "submit" else None, operation, {}, "owner")
    service.finish_if_ended(ticket)
    service.finish_if_ended(ticket)

    expected = {
        "submit": ["ticket_end", "ticket_finish"],
        "reconcile": ["ticket_end", "ticket_finish"],
        "close": ["ticket_finish"],
        "terminate": [],
        "withdraw": [],
    }
    assert list(TriggerLog.objects.filter(ticket_id=ticket.pk).order_by("id").values_list("event", flat=True)) == expected[operation]


def test_status_action_uses_tenant_status_and_rejects_a_forbidden_transition(workflow):
    other = TicketStatus.objects.create(key="custom_status", name="跨租户状态", domain="foreign.example")
    local = TicketStatus.objects.create(key=other.key, name="本租户状态", domain=DOMAIN)
    ticket = TicketService().create(workflow, {"title": "申请"}, "owner", is_test=True)
    rule = make_rule("ticket_update", action="status", config={"response": local.key})
    suspended = TicketStatus.objects.get(domain=DOMAIN, key="suspended")
    transition = StatusTransition.objects.create(from_status=ticket.status, to_status=suspended, name="挂起", domain=DOMAIN)

    fire_triggers(ticket, "save", "owner")
    assert rule.logs.get().status == "failed"
    assert ticket.status.key == "new"
    transition.delete()
    fire_triggers(ticket, "save", "owner")
    ticket.refresh_from_db()
    assert ticket.status_id == local.id


@pytest.mark.parametrize("is_test", [False, True])
def test_notification_contains_detail_link_and_does_not_run_before_commit(workflow, settings, django_capture_on_commit_callbacks, is_test):
    settings.WEB_BASE_URL = "https://itsm.example"
    rule = make_rule("ticket_create", action="notice", config={"response": "已提交"})
    with patch("apps.itsm.services.notify.service._send_im_if_configured", return_value={"result": True}) as send:
        with django_capture_on_commit_callbacks(execute=True):
            ticket = TicketService().create(workflow, {"title": "申请"}, "owner", is_test=is_test)
            assert not Notification.objects.exists()
            assert rule.logs.get().status == "pending"
        assert Notification.objects.get().target_url == f"/itsm/tickets/{ticket.pk}"
        if is_test:
            send.assert_not_called()
        else:
            assert f"https://itsm.example/itsm/tickets/{ticket.pk}" in send.call_args.args[1]
    assert rule.logs.get().status == "success"


def test_trigger_notice_recovers_when_commit_callback_was_lost(workflow, django_capture_on_commit_callbacks):
    from apps.itsm.tasks import trigger_notice_tick

    rule = make_rule("ticket_create", action="notice", config={"response": "待恢复通知"})
    with django_capture_on_commit_callbacks(execute=False):
        ticket = TicketService().create(workflow, {"title": "申请"}, "owner", is_test=True)
    assert rule.logs.get().status == "pending"
    assert not Notification.objects.filter(target_url=f"/itsm/tickets/{ticket.pk}").exists()

    trigger_notice_tick()
    trigger_notice_tick()

    assert rule.logs.get().status == "success"
    assert Notification.objects.filter(target_url=f"/itsm/tickets/{ticket.pk}").count() == 1


def test_parallel_task_creation_triggers_once_per_active_node(workflow, django_capture_on_commit_callbacks):
    rule = make_rule("activity_into", config={"response": "进入审批"})
    ticket = TicketService().create(workflow, {"title": "申请"}, "owner", is_test=True)
    ticket.process_instance_id = "parent"
    ticket.save(update_fields=["process_instance_id"])
    client = Mock()
    task = {"processInstanceId": "child", "taskDefinitionKey": "review", "name": "审批"}
    records = [
        {**task, "id": "review-1", "assignee": "alice"},
        {**task, "id": "review-2", "assignee": "bob"},
    ]
    client.list_tasks_including_children.return_value = records
    service = TicketService(client)
    with django_capture_on_commit_callbacks(execute=False):
        service.sync_ticket(ticket)
        client.list_tasks_including_children.return_value = [*records, {**task, "id": "review-3", "assignee": "carol"}]
        service.sync_ticket(ticket)
    assert rule.logs.count() == 1
    assert ticket.tasks.count() == 3

    child_review = {**task, "processInstanceId": "other-child", "id": "child-review"}
    client.list_tasks_including_children.return_value = [*records, child_review]
    with django_capture_on_commit_callbacks(execute=False):
        service.sync_ticket(ticket)
    assert rule.logs.count() == 2

    client.list_tasks_including_children.return_value = [child_review, {**task, "id": "review-return", "assignee": "alice"}]
    with django_capture_on_commit_callbacks(execute=False):
        service.sync_ticket(ticket)
    assert rule.logs.count() == 3
