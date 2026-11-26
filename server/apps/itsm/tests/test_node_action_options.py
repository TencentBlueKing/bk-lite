import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone

from apps.itsm.flowable.validator import validate_design
from apps.itsm.models import Handover, TicketLog, TicketStatus, TicketTask
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.tests.test_review_regressions import sample as sample_ticket
from apps.itsm.views.extend import handover_candidates, resources
from apps.itsm.views.ticket_operations import batch_operate, batch_options
from apps.itsm.views.tickets import operate_ticket, ticket_detail
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def approval_ticket():
    ticket, active = sample_ticket.__wrapped__()
    return ticket, active


def response_data(response):
    return json.loads(response.content)["data"]


def configure(ticket, **settings):
    version = ticket.workflow_version
    next(node for node in version.design["nodes"] if node["type"] == "approval").update(settings)
    version.save(update_fields=["design"])


def complete(ticket, node_id, action, offset):
    when = timezone.now() - timedelta(minutes=offset)
    task = TicketTask.objects.create(ticket=ticket, node_id=node_id, assignee="handler", status="done")
    TicketTask.objects.filter(pk=task.pk).update(created_at=when)
    log = TicketLog.objects.create(ticket=ticket, task=task, action=action, operator="handler")
    TicketLog.objects.filter(pk=log.pk).update(created_at=when + timedelta(seconds=1))
    return task


def setup_history(ticket, active):
    version = ticket.workflow_version
    version.design = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "submit_step", "type": "submit", "name": "需求提报"},
            {"id": "verified", "type": "handle", "name": "运营确认"},
            {"id": "skipped", "type": "handle", "name": "其他分支"},
            {"id": active.node_id, "type": "approval", "actions": ["approve", "return"], "required_opinion_actions": ["return"]},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"from": "start", "to": "submit_step"},
            {"from": "submit_step", "to": "verified"},
            {"from": "submit_step", "to": "skipped"},
            {"from": "verified", "to": active.node_id},
            {"from": "skipped", "to": active.node_id},
            {"from": active.node_id, "to": "end"},
        ],
    }
    version.save(update_fields=["design"])
    complete(ticket, "submit_step", "submit", 8)
    complete(ticket, "verified", "submit", 6)
    complete(ticket, "verified", "submit", 4)
    complete(ticket, "skipped", "return", 3)


def test_opinion_metadata_and_write_guard_use_same_authorization(approval_ticket):
    ticket, task = approval_ticket
    configure(ticket, actions=["approve", "reject", "suspend"], required_opinion_actions=["approve", "suspend"])
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert detail["tasks"][0]["required_opinion_actions"] == ["approve"]
    assert detail["required_opinion_actions"] == ["suspend"]
    viewer = response_data(ticket_detail(request(username="owner", permissions=["ticket-View"]), ticket.id))
    assert viewer["tasks"][0].get("required_opinion_actions", []) == []
    assert viewer.get("required_opinion_actions", []) == []

    client = Mock()
    service = TicketService(client)
    with patch("apps.itsm.views.tickets._service", return_value=service):
        assert operate_ticket(request("post", {"action": "approve", "task_id": task.id, "opinion": " "}, "handler"), ticket.id).status_code == 400
        assert operate_ticket(request("post", {"action": "suspend"}, "handler"), ticket.id).status_code == 400
        assert operate_ticket(request("post", {"action": "approve", "task_id": task.id}, "owner"), ticket.id).status_code == 403
        assert operate_ticket(request("post", {"action": "approve", "task_id": task.id}, "handler", domain="other.com"), ticket.id).status_code == 404
        task.refresh_from_db()
        assert task.status == "pending"
        assert not ticket.logs.exclude(action="create").exists()
        assert client.mock_calls == []
        assert (
            operate_ticket(request("post", {"action": "approve", "task_id": task.id, "opinion": "  已核对  "}, "handler"), ticket.id).status_code == 200
        )
    assert ticket.logs.get(action="approve").message == "已核对"
    history = response_data(ticket_detail(request(username="handler"), ticket.id))["history"]
    assert next(row for row in history if row["action"] == "approve")["opinion"] == "已核对"


def test_batch_opinion_metadata_blocks_empty_value_without_mutation(approval_ticket):
    ticket, task = approval_ticket
    configure(ticket, actions=["approve"], required_opinion_actions=["approve"])
    selection = {"ids": [ticket.id]}
    options = response_data(batch_options(request("post", selection, "handler")))
    assert options["required_opinion_actions"] == ["approve"]
    with patch("apps.itsm.views.ticket_operations._service", return_value=TicketService()):
        result = response_data(batch_operate(request("post", {**selection, "action": "approve", "opinion": " "}, "handler")))
    assert result["items"][0]["ok"] is False
    assert "处理意见" in result["items"][0]["error"]
    task.refresh_from_db()
    assert task.status == "pending"


def test_only_completed_current_round_targets_appear_and_allow_return(approval_ticket):
    ticket, task = approval_ticket
    setup_history(ticket, task)
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert [row["node_id"] for row in detail["tasks"][0]["return_targets"]] == ["verified", "submit_step"]
    assert all(row["completed_at"] for row in detail["tasks"][0]["return_targets"])
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        result = operate_ticket(request("post", {"action": "return", "task_id": task.id, "opinion": "核对"}, "handler"), ticket.id)
        assert result.status_code == 400
        assert "请选择可回退的历史节点" in json.loads(result.content)["message"]
        for invalid in ["skipped", "end", task.node_id]:
            res = operate_ticket(
                request("post", {"action": "return", "task_id": task.id, "return_node_id": invalid, "opinion": "核对"}, "handler"), ticket.id
            )
            assert res.status_code == 400
        assert not ticket.logs.filter(action="return", task=task).exists()
        res = operate_ticket(
            request("post", {"action": "return", "task_id": task.id, "return_node_id": "verified", "opinion": "请重新确认"}, "handler"), ticket.id
        )
        assert res.status_code == 200
    log = ticket.logs.get(action="return", task=task)
    assert log.detail["return_node_id"] == "verified"
    assert log.detail["return_node_name"] == "运营确认"
    TicketLog.objects.create(ticket=ticket, action="return", operator="system", detail={"opinion": "自动退回"})
    rows = [row for row in response_data(ticket_detail(request(username="handler"), ticket.id))["history"] if row["action"] == "return"]
    assert next(row for row in rows if row["id"] == f"log-{log.pk}")["opinion"] == "请重新确认"
    assert all("opinion" not in row for row in rows if row["operator"] == "system")


def test_reopened_round_excludes_old_history_and_disallows_legacy_target(approval_ticket):
    ticket, task = approval_ticket
    setup_history(ticket, task)
    boundary = timezone.now() - timedelta(minutes=2)
    TicketLog.objects.create(ticket=ticket, action="reopen", operator="owner", detail={"round_started_at": boundary.isoformat()})
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert detail["tasks"][0].get("return_targets", []) == []
    assert "return" not in detail["tasks"][0]["allowed_actions"]
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        assert (
            operate_ticket(
                request("post", {"action": "return", "task_id": task.id, "return_mode": "submit", "opinion": "核对"}, "handler"), ticket.id
            ).status_code
            == 400
        )
    assert not ticket.logs.filter(task=task).exists()


def test_multiple_active_tasks_hide_return_and_reject_direct_submission(approval_ticket):
    ticket, task = approval_ticket
    setup_history(ticket, task)
    TicketTask.objects.create(ticket=ticket, node_id="verified", assignee="someone")
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert "return" not in detail["tasks"][0]["allowed_actions"]
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        assert (
            operate_ticket(
                request("post", {"action": "return", "task_id": task.id, "return_node_id": "verified", "opinion": "核对"}, "handler"), ticket.id
            ).status_code
            == 400
        )


def test_handover_uses_same_transfer_opinion_policy(approval_ticket):
    ticket, task = approval_ticket
    configure(ticket, actions=["transfer"], required_opinion_actions=["transfer"])
    User.objects.create(domain=ticket.domain, username="recipient", display_name="接收人")
    payload = {"from_user": "handler", "to_user": "recipient", "ticket_ids": [ticket.id]}
    candidates = handover_candidates(request(payload={"from_user": "handler"}, username="handler", permissions=["handover-Add", "ticket-View"]))
    assert response_data(candidates)["items"] == [{"id": ticket.id, "sn": ticket.sn, "title": ticket.title, "requires_opinion": True}]
    with patch("apps.itsm.views.extend._service", return_value=TicketService()):
        assert resources(request("post", payload, "owner", ["handover-Add"]), "handovers").status_code == 400
        assert not Handover.objects.exists()
        assert resources(request("post", {**payload, "opinion": " 交接说明 "}, "owner", ["handover-Add"]), "handovers").status_code == 200
    assert Handover.objects.get().opinion == "交接说明"
    assert ticket.logs.get(task=task, action="transfer").message == "交接说明"


def test_publish_validation_rejects_required_opinion_for_disabled_button():
    design = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "approval", "type": "approval", "fallback": "admin", "actions": ["approve"], "required_opinion_actions": ["reject"]},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "approval"}, {"from": "approval", "to": "end"}],
    }
    assert any("处理意见" in error for error in validate_design(design))


def test_same_main_multi_instance_activity_can_return_as_a_group(approval_ticket):
    ticket, task = approval_ticket
    setup_history(ticket, task)
    configure(ticket, multi={"mode": "any"})
    TicketTask.objects.create(ticket=ticket, node_id=task.node_id, assignee="another")
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert [row["node_id"] for row in detail["tasks"][0]["return_targets"]] == ["verified", "submit_step"]
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        assert (
            operate_ticket(
                request("post", {"action": "return", "task_id": task.id, "return_mode": "submit", "opinion": "重新提报"}, "handler"),
                ticket.id,
            ).status_code
            == 200
        )
    assert ticket.logs.get(task=task, action="return").detail["return_node_id"] == "submit_step"


def test_cannot_select_target_across_parallel_join(approval_ticket):
    ticket, task = approval_ticket
    setup_history(ticket, task)
    version = ticket.workflow_version
    version.design["nodes"].append({"id": "join", "type": "converge"})
    for edge in version.design["edges"]:
        if edge["to"] == task.node_id:
            edge["to"] = "join"
    version.design["edges"].append({"from": "join", "to": task.node_id})
    version.save(update_fields=["design"])
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert "return" not in detail["tasks"][0]["allowed_actions"]
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        assert (
            operate_ticket(
                request("post", {"action": "return", "task_id": task.id, "return_node_id": "verified", "opinion": "重新处理"}, "handler"),
                ticket.id,
            ).status_code
            == 400
        )
    assert not ticket.logs.filter(task=task).exists()


def test_root_process_origin_and_runtime_origin_are_both_checked(approval_ticket):
    ticket, task = approval_ticket
    setup_history(ticket, task)
    ticket.process_instance_id = "root"
    ticket.save(update_fields=["process_instance_id"])
    task.flowable_task_id = "active"
    task.process_instance_id = "child"
    task.save(update_fields=["flowable_task_id", "process_instance_id"])
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert "return" not in detail["tasks"][0]["allowed_actions"]

    task.process_instance_id = "root"
    task.save(update_fields=["process_instance_id"])
    client = Mock()
    client.list_tasks.return_value = {"data": [{"id": "fresh-other-task", "taskDefinitionKey": "another-node"}]}
    with patch("apps.itsm.views.tickets._service", return_value=TicketService(client)):
        response = operate_ticket(
            request("post", {"action": "return", "task_id": task.id, "return_node_id": "verified", "opinion": "重新处理"}, "handler"),
            ticket.id,
        )
    assert response.status_code == 400
    client.change_state.assert_not_called()
    assert not ticket.logs.filter(task=task).exists()


def test_side_operation_checks_all_applicable_nodes_even_when_task_id_is_supplied(approval_ticket):
    ticket, task = approval_ticket
    configure(ticket, actions=["suspend"])
    version = ticket.workflow_version
    version.design["nodes"].append(
        {
            "id": "another",
            "type": "handle",
            "actions": ["suspend"],
            "required_opinion_actions": ["suspend"],
        }
    )
    version.save(update_fields=["design"])
    TicketTask.objects.create(ticket=ticket, node_id="another", assignee="another")
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert detail["required_opinion_actions"] == ["suspend"]
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        response = operate_ticket(request("post", {"action": "suspend", "task_id": task.id}, "handler"), ticket.id)
    assert response.status_code == 400
    assert not ticket.logs.exclude(action="create").exists()


def test_cannot_urge_as_a_task_assignee(approval_ticket):
    ticket, task = approval_ticket
    configure(ticket, actions=["urge"], required_opinion_actions=["urge"])
    payload = {"action": "urge", "task_id": task.id, "opinion": "请尽快处理"}
    with (
        patch("apps.itsm.views.tickets._service", return_value=TicketService()),
        patch("apps.itsm.services.ticket.service.dispatch_notification") as dispatch,
    ):
        assert operate_ticket(request("post", payload, "handler"), ticket.id).status_code == 403
        dispatch.assert_not_called()
        assert operate_ticket(request("post", {"action": "urge", "opinion": "请尽快处理"}, "owner"), ticket.id).status_code == 200
        dispatch.assert_called_once()


def test_test_ticket_urge_is_only_delivered_to_site(approval_ticket):
    ticket, _ = approval_ticket
    ticket.is_test = True
    ticket.save(update_fields=["is_test"])
    configure(ticket, actions=["urge"])
    with (
        patch("apps.itsm.views.tickets._service", return_value=TicketService()),
        patch("apps.itsm.services.ticket.service.dispatch_notification") as dispatch,
    ):
        response = operate_ticket(request("post", {"action": "urge"}, "owner"), ticket.id)
    assert response.status_code == 200
    assert dispatch.call_args.kwargs["site_only"] is True


@pytest.mark.parametrize(
    ("node_type", "display"),
    [
        ("approval", None),
        ("approval", {"action": "approve"}),
        ("approval", ["approve"]),
        ("approval", [{"action": 1}]),
        ("approval", [{"action": "approve"}, {"action": "approve"}]),
        ("approval", [{"action": "unsupported"}]),
        ("approval", [{"action": "submit"}]),
        ("approval", [{"action": "reject"}]),
        ("start", [{"action": "approve"}]),
        ("approval", [{"action": "approve", "label": 1}]),
        ("approval", [{"action": "approve", "label": "复核\n通过"}]),
        ("approval", [{"action": "approve", "label": "审" * 25}]),
    ],
)
def test_publish_rejects_invalid_operation_presentation(node_type, display):
    design = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "node", "type": node_type, "name": "复核节点", "fallback": "admin", "actions": ["approve"], "action_display": display},
            {"id": "end", "type": "end"},
        ],
        "edges": [{"from": "start", "to": "node"}, {"from": "node", "to": "end"}],
    }
    assert any("复核节点" in error and "按钮" in error for error in validate_design(design))


def test_detail_projects_ordered_button_names_after_permission_and_return_checks(approval_ticket):
    ticket, task = approval_ticket
    configure(
        ticket,
        actions=["approve", "reject", "return", "urge", "suspend"],
        required_opinion_actions=["approve"],
        action_display=[
            {"action": "return", "label": "返回经办"},
            {"action": "reject", "label": "  "},
            {"action": "approve", "label": "  审核通过  "},
            {"action": "urge", "label": "提醒审批"},
            {"action": "suspend", "label": "暂停审批"},
        ],
    )
    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert detail["tasks"][0].get("action_display") == [
        {"action": "reject"},
        {"action": "approve", "label": "审核通过"},
        {"action": "suspend", "label": "暂停审批"},
    ]
    assert detail["tasks"][0]["required_opinion_actions"] == ["approve"]
    assert detail.get("action_display") == [{"action": "suspend", "label": "暂停审批"}]

    requester = response_data(ticket_detail(request(username="owner"), ticket.id))
    assert requester.get("action_display") == [{"action": "urge", "label": "提醒审批"}]
    assert not requester["tasks"][0]["allowed_actions"]
    readonly = response_data(ticket_detail(request(username="handler", permissions=["ticket-View"]), ticket.id))
    assert not readonly.get("action_display")
    assert not readonly["tasks"][0].get("action_display")

    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        without_opinion = operate_ticket(request("post", {"action": "approve", "task_id": task.id}, "handler"), ticket.id)
        assert without_opinion.status_code == 400
        assert not ticket.logs.filter(action="approve").exists()
        approved = operate_ticket(request("post", {"action": "approve", "task_id": task.id, "opinion": "核查完成"}, "handler"), ticket.id)
        assert approved.status_code == 200
    assert ticket.logs.get(action="approve").message == "核查完成"


def test_parallel_tasks_use_own_presentation_and_resume_keeps_default_name(approval_ticket):
    ticket, _ = approval_ticket
    configure(
        ticket,
        actions=["approve", "suspend", "terminate"],
        action_display=[{"action": "approve", "label": "批准立项"}, {"action": "suspend", "label": "暂停立项"}, {"action": "terminate"}],
    )
    version = ticket.workflow_version
    version.design["nodes"].append(
        {
            "id": "secondary",
            "type": "handle",
            "actions": ["submit", "suspend"],
            "action_display": [{"action": "submit", "label": "完成评估"}, {"action": "suspend", "label": "暂停评估"}],
        }
    )
    version.save(update_fields=["design"])
    TicketTask.objects.create(ticket=ticket, node_id="secondary", assignee="handler")

    detail = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert {task["node_id"]: task.get("action_display") for task in detail["tasks"]} == {
        "approval_1": [{"action": "approve", "label": "批准立项"}, {"action": "suspend", "label": "暂停立项"}, {"action": "terminate"}],
        "secondary": [{"action": "submit", "label": "完成评估"}, {"action": "suspend", "label": "暂停评估"}],
    }
    TicketStatus.objects.get_or_create(key="suspended", defaults={"name": "已挂起"})
    with patch("apps.itsm.views.tickets._service", return_value=TicketService()):
        assert operate_ticket(request("post", {"action": "suspend"}, "handler"), ticket.id).status_code == 200
    suspended = response_data(ticket_detail(request(username="handler"), ticket.id))
    assert suspended.get("action_display") == [{"action": "resume"}, {"action": "terminate"}]
    assert all(not task["can_operate"] for task in suspended["tasks"])
