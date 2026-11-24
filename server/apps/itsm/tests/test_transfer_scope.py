import json
from unittest.mock import Mock, patch

import pytest
from django.urls import resolve

from apps.itsm.models import HandlerGroup, TicketStatus, TicketTask, Workflow, WorkflowVersion
from apps.itsm.models.extend import Handover, TicketProxy
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as ticket_sample
from apps.itsm.views.api import publish_workflow
from apps.itsm.views.extend import resources
from apps.itsm.views.tickets import operate_ticket
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample():
    return ticket_sample.__wrapped__()


def user(name, domain="domain.com", disabled=False):
    return User.objects.create(username=name, display_name="接收 " + name, domain=domain, disabled=disabled)


def set_node(ticket, scope=None, actions=None):
    version = ticket.workflow_version
    node = version.design["nodes"][1]
    if scope is not None:
        node["transfer_scope"] = scope
    if actions is not None:
        node["actions"] = actions
    version.save(update_fields=["design"])


def candidates(ticket, task, **kwargs):
    match = resolve(f"/api/tickets/{ticket.pk}/tasks/{task.pk}/transfer-candidates/", urlconf="apps.itsm.urls")
    return match.func(request(**{"username": "handler", **kwargs}), **match.kwargs)


def payload(response):
    assert response.status_code == 200
    return json.loads(response.content)["data"]


def test_candidates_and_transfer_use_ticket_version_and_active_domain_users(sample):
    ticket, task = sample
    set_node(ticket, {"type": "users", "users": ["enabled", "disabled", "abroad"]}, ["transfer"])
    current = WorkflowVersion.objects.create(workflow=ticket.workflow, version_no=2, design=ticket.workflow_version.design, is_published=True)
    current.design = {"nodes": [{"id": task.node_id, "type": "approval"}]}
    current.save(update_fields=["design"])
    ticket.workflow.current_version = current
    ticket.workflow.save(update_fields=["current_version"])
    user("enabled")
    user("disabled", disabled=True)
    user("disabled", "other.com")
    user("abroad", "other.com")
    user("unlisted")
    assert payload(candidates(ticket, task, payload={"q": "接收"}))["items"] == [{"username": "enabled", "display_name": "接收 enabled"}]
    task.flowable_task_id = "engine-task"
    task.save(update_fields=["flowable_task_id"])
    engine = Mock()
    with patch("apps.itsm.views.tickets._service", return_value=TicketService(engine)):
        for target in ("abroad", "disabled", "unlisted"):
            response = operate_ticket(request("post", {"action": "transfer", "task_id": task.id, "target": target}, "handler"), ticket.id)
            assert response.status_code == 403
            task.refresh_from_db()
            assert task.assignee == "handler"
        engine.update_task_assignee.assert_not_called()
        response = operate_ticket(request("post", {"action": "transfer", "task_id": task.id, "target": "enabled"}, "handler"), ticket.id)
        assert response.status_code == 200
    engine.update_task_assignee.assert_called_once_with("engine-task", "enabled")
    task.refresh_from_db()
    assert task.assignee == "enabled"
    assert ticket.logs.filter(action="transfer").count() == 1


def test_unrestricted_candidates_search_and_paginate_within_domain(sample):
    ticket, task = sample
    for index in range(12):
        user(f"receiver-{index:02}")
    user("receiver-overseas", "other.com")
    user("receiver-disabled", disabled=True)
    result = payload(candidates(ticket, task, payload={"q": "receiver", "page": "2"}))
    assert (result["count"], result["page"], result["page_size"]) == (12, 2, 10)
    assert [row["username"] for row in result["items"]] == ["receiver-10", "receiver-11"]


def test_group_candidates_follow_membership_without_falling_back(sample):
    ticket, task = sample
    group = HandlerGroup.objects.create(name="一线", members=["old", "foreign"])
    outside = HandlerGroup.objects.create(name="其他租户", domain="other.com", members=["wrong"])
    set_node(ticket, {"type": "handler_groups", "group_ids": [group.id, outside.id]})
    for name in ("old", "new", "wrong"):
        user(name)
    user("foreign", "other.com")
    assert [row["username"] for row in payload(candidates(ticket, task))["items"]] == ["old"]
    group.members = ["new"]
    group.save(update_fields=["members"])
    with pytest.raises(PermissionError):
        TicketService().operate(ticket, task, "transfer", {"target": "old"}, "handler")
    assert [row["username"] for row in payload(candidates(ticket, task))["items"]] == ["new"]
    group.delete()
    assert payload(candidates(ticket, task))["items"] == []
    with pytest.raises(PermissionError):
        TicketService().operate(ticket, task, "transfer", {"target": "new"}, "handler")


def test_existing_invalid_scope_fails_closed(sample):
    ticket, task = sample
    user("unlisted")
    set_node(ticket, {"type": "users", "users": []})
    assert payload(candidates(ticket, task))["items"] == []
    with pytest.raises(PermissionError):
        TicketService().operate(ticket, task, "transfer", {"target": "unlisted"}, "handler")


def test_candidates_require_visible_active_transferable_task(sample):
    ticket, task = sample
    assert candidates(ticket, task, username="outsider").status_code == 404
    assert candidates(ticket, task, domain="other.com").status_code == 404
    assert candidates(ticket, task, username="owner").status_code == 403
    for permission in ("ticket-View", "ticket-Operate"):
        assert candidates(ticket, task, permissions=[permission]).status_code == 403
    other = TicketService().create(ticket.workflow_version, {"title": "另一单", "amount": 1}, "owner")
    other_task = TicketTask.objects.create(ticket=other, node_id=task.node_id, assignee="handler")
    assert candidates(ticket, other_task).status_code == 404
    TicketProxy.objects.create(principal="handler", agent="delegate")
    assert candidates(ticket, task, username="delegate").status_code == 200
    set_node(ticket, actions=["approve"])
    assert candidates(ticket, task).status_code == 403
    set_node(ticket, actions=["transfer"])
    task.status = "done"
    task.save(update_fields=["status"])
    assert candidates(ticket, task).status_code == 400
    task.status = "pending"
    task.save(update_fields=["status"])
    ticket.status = TicketStatus.objects.create(key="suspended", name="挂起")
    ticket.save(update_fields=["status"])
    assert candidates(ticket, task).status_code == 400


def test_group_options_only_lists_names_in_editor_domain():
    local = HandlerGroup.objects.create(name="本地组", members=["owner"])
    HandlerGroup.objects.create(name="其他租户", domain="other.com")
    view = resolve("/api/workflows/handler-group-options/", urlconf="apps.itsm.urls").func
    assert view(request(permissions=["org-View"])).status_code == 403
    assert payload(view(request(permissions=["workflow-Edit"]))) == {"items": [{"id": local.id, "name": "本地组"}], "count": 1}


def test_handover_checks_all_included_tickets_before_transferring(sample):
    ticket, allowed = sample
    user("replacement")
    user("other")
    version = ticket.workflow_version
    version.design["nodes"].append({"id": "restricted", "type": "approval", "transfer_scope": {"type": "users", "users": ["other"]}})
    version.save(update_fields=["design"])
    allowed.flowable_task_id = "allowed"
    allowed.save(update_fields=["flowable_task_id"])
    other_ticket = TicketService().create(version, {"title": "指定范围工单", "amount": 1}, "owner")
    blocked = TicketTask.objects.create(ticket=other_ticket, node_id="restricted", assignee="handler", flowable_task_id="blocked")
    engine = Mock()
    with patch("apps.itsm.views.extend._service", return_value=TicketService(engine)):
        response = resources(
            request(
                "post", {"from_user": "handler", "to_user": "replacement", "ticket_ids": [ticket.id, other_ticket.id]}, "admin", ["handover-Add"]
            ),
            "handovers",
        )
    assert response.status_code == 403
    engine.update_task_assignee.assert_not_called()
    assert not Handover.objects.exists()
    allowed.refresh_from_db()
    blocked.refresh_from_db()
    assert allowed.assignee == blocked.assignee == "handler"


@pytest.mark.parametrize(
    "mode", ["valid_user", "disabled_user", "foreign_user", "mixed_keys", "empty_users", "foreign_group", "valid_group", "unknown", "off"]
)
def test_publish_checks_transfer_configuration_before_deploy(mode):
    user("active")
    user("disabled", disabled=True)
    user("foreign", "other.com")
    foreign_group = HandlerGroup.objects.create(name="其他租户", domain="other.com")
    local_group = HandlerGroup.objects.create(name="本地组", members=["active"])
    scopes = {
        "valid_user": {"type": "users", "users": ["active"]},
        "disabled_user": {"type": "users", "users": ["disabled"]},
        "foreign_user": {"type": "users", "users": ["active", "foreign"]},
        "mixed_keys": {"type": "users", "users": ["active"], "group_ids": [local_group.pk]},
        "empty_users": {"type": "users", "users": []},
        "foreign_group": {"type": "handler_groups", "group_ids": [foreign_group.pk]},
        "valid_group": {"type": "handler_groups", "group_ids": [local_group.pk]},
        "unknown": {"type": "all"},
        "off": {"type": "users", "users": []},
    }
    workflow = Workflow.objects.create(name="转交范围", key="transfer-scope")
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        design={
            "nodes": [
                {"id": "start", "type": "start"},
                {
                    "id": "approval",
                    "type": "approval",
                    "assignee": {"source": "users", "value": ["active"]},
                    "transfer_scope": scopes[mode],
                    **({"actions": ["approve"]} if mode == "off" else {}),
                },
                {"id": "end", "type": "end"},
            ],
            "edges": [{"from": "start", "to": "approval"}, {"from": "approval", "to": "end"}],
        },
    )
    expected = mode in {"valid_user", "valid_group", "off"}
    with patch("apps.itsm.views.api.FlowableClient") as client:
        client.return_value.definition_for_deployment.return_value = "tested:1:stable"
        client.return_value.deploy_bpmn.return_value = {"id": "deployment"}
        response = publish_workflow(request("post", permissions=["workflow-Publish"]), workflow.id)
        assert json.loads(response.content)["result"] is expected
        assert client.return_value.deploy_bpmn.called is expected
    version.refresh_from_db()
    assert version.is_published is expected
