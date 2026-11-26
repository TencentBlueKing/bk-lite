"""详情协作、节点操作及流转信息的行为回归。"""
import json

import pytest

from apps.itsm.models import TicketAttachment, TicketComment
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests import test_review_regressions as review
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.m2 import attachments, comments
from apps.itsm.views.tickets import ticket_detail

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample():
    return review.sample.__wrapped__()


def test_reply_preserves_parent_and_attachment(sample):
    ticket, _ = sample
    parent = TicketComment.objects.create(ticket=ticket, content="原评论", created_by="owner")
    attachment = TicketAttachment.objects.create(ticket=ticket, name="图片.png", object_name="test", created_by="handler")
    response = comments(request("post", {"content": "回复", "parent_id": parent.id, "attachment_ids": [attachment.id]}, "handler"), ticket.id)
    assert response.status_code == 200
    reply = ticket.comments.latest("id")
    assert reply.parent_id == parent.id
    assert list(reply.attachments.values_list("id", flat=True)) == [attachment.id]


def test_reject_reply_to_other_ticket(sample):
    ticket, _ = sample
    parent = TicketComment.objects.create(ticket=ticket, content="原评论")
    other = TicketService().create(ticket.workflow_version, {"title": "另一单", "amount": 1}, "owner")
    response = comments(request("post", {"content": "跨单", "parent_id": parent.id}, "owner"), other.id)
    assert response.status_code == 404
    assert not other.comments.exists()


def test_attachment_list_includes_uploader_and_delete_permission(sample):
    ticket, _ = sample
    TicketAttachment.objects.create(ticket=ticket, name="文件", object_name="test", created_by="owner")
    data = json.loads(attachments(request(username="handler", permissions=["ticket-View"]), ticket.id).content)
    assert data["data"]["items"][0]["operator"] == "owner"
    assert data["data"]["items"][0]["can_delete"] is False


def test_node_config_restricts_operations(sample):
    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["actions"] = ["approve"]
    version.save()
    with pytest.raises(PermissionError):
        TicketService().operate(ticket, task, "reject", {}, "handler")
    task.refresh_from_db()
    assert task.status == "pending"


def test_view_only_cannot_see_processing_buttons(sample):
    ticket, _ = sample
    data = json.loads(ticket_detail(request(username="handler", permissions=["ticket-View"]), ticket.id).content)["data"]
    assert data["allowed_actions"] == []
    assert not any(task["can_operate"] for task in data["tasks"])


def test_flow_history_has_real_step_and_time(sample):
    ticket, task = sample
    task.node_name = "主管审批"
    task.save()
    TicketService().operate(ticket, task, "approve", {}, "handler")
    data = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    step = next(item for item in data["history"] if item["node_id"] == task.node_id)
    assert step["name"] == "主管审批"
    assert step["operator"] == "handler"
    assert step["finished_at"]


def test_other_uploader_cannot_delete_attachment(sample):
    from apps.itsm.views.m2 import attachment_item

    ticket, _ = sample
    file = TicketAttachment.objects.create(ticket=ticket, name="文件", object_name="test", created_by="owner")
    response = attachment_item(request("delete", username="handler"), ticket.id, file.id)
    assert response.status_code == 403
    assert ticket.attachments.filter(id=file.id).exists()


def test_uploader_delete_removes_file_and_comment_reference(sample):
    from unittest.mock import patch

    from apps.itsm.views.m2 import attachment_item

    ticket, _ = sample
    comment = TicketComment.objects.create(ticket=ticket, content="附件评论")
    file = TicketAttachment.objects.create(ticket=ticket, comment=comment, name="文件", object_name="test", created_by="owner")
    with patch("apps.itsm.services.attachment.storage_client") as storage:
        response = attachment_item(request("delete", username="owner"), ticket.id, file.id)
        storage.return_value.remove_object.assert_called_once_with("itsm-private", "test")
    assert response.status_code == 200
    assert not comment.attachments.exists()
    assert ticket.comments.filter(id=comment.id).exists()


def test_comment_cannot_attach_another_uploaders_file(sample):
    ticket, _ = sample
    file = TicketAttachment.objects.create(ticket=ticket, name="文件", object_name="test", created_by="owner")
    response = comments(request("post", {"content": "引用", "attachment_ids": [file.id]}, "handler"), ticket.id)
    assert response.status_code == 403
    assert not ticket.comments.exists()


def test_register_requires_valid_ticket_and_uploader_receipt(sample):
    from apps.itsm.services.attachment import register_upload, upload_receipt

    ticket, _ = sample
    receipt = upload_receipt({"object_name": "test"}, ticket, "owner", "测试.txt")
    with pytest.raises(PermissionError):
        register_upload(ticket, "handler", {"receipt": receipt})
    with pytest.raises(PermissionError):
        register_upload(ticket, "owner", {"receipt": "forged"})


def test_register_uses_storage_size_and_preserves_chinese_filename(sample):
    from types import SimpleNamespace
    from unittest.mock import patch

    from apps.itsm.services.attachment import download_url, register_upload, upload_receipt

    ticket, _ = sample
    receipt = upload_receipt({"object_name": "test"}, ticket, "owner", "测试.txt")
    with patch("apps.itsm.services.attachment.storage_client") as storage:
        storage.return_value.stat_object.return_value = SimpleNamespace(size=42)
        file = register_upload(ticket, "owner", {"receipt": receipt, "size": 0})
        again = register_upload(ticket, "owner", {"receipt": receipt})
        download_url(file)
        assert "UTF-8''%E6%B5%8B" in storage.return_value.presigned_get_object.call_args.kwargs["response_headers"]["response-content-disposition"]
    assert file.id == again.id
    assert file.name == "测试.txt" and file.size == 42


def test_empty_node_actions_hide_and_deny_all_task_actions(sample):
    ticket, task = sample
    version = ticket.workflow_version
    version.design["nodes"][1]["actions"] = []
    version.save()
    data = json.loads(ticket_detail(request(username="handler"), ticket.id).content)["data"]
    assert data["tasks"][0]["allowed_actions"] == []
    for action in ["approve", "reject", "transfer", "return", "save", "claim"]:
        with pytest.raises(PermissionError):
            TicketService().operate(ticket, task, action, {}, "handler")


@pytest.mark.parametrize("action,outcome", [("approve", "accepted"), ("reject", "rejected")])
def test_flow_node_exposes_actual_approval_outcome(sample, action, outcome):
    ticket, task = sample
    TicketService().operate(ticket, task, action, {}, "handler")
    data = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    node = next(item for item in data["nodes"] if item["id"] == task.node_id)
    assert node["outcome"] == outcome


def test_revisited_node_does_not_keep_previous_rejection_color(sample):
    from apps.itsm.models import TicketTask

    ticket, task = sample
    TicketService().operate(ticket, task, "reject", {}, "handler")
    TicketTask.objects.create(ticket=ticket, node_id=task.node_id, assignee="handler")
    data = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    node = next(item for item in data["nodes"] if item["id"] == task.node_id)
    assert node["outcome"] == "current"


def test_itsm_init_creates_default_menu_idempotently():
    from django.core.management import call_command

    from apps.system_mgmt.models import CustomMenuGroup

    CustomMenuGroup.objects.filter(app="itsm").delete()
    call_command("init_itsm", verbosity=0)
    call_command("init_itsm", verbosity=0)
    group = CustomMenuGroup.objects.get(app="itsm")
    assert group.is_enabled and group.is_build_in
    assert group.menus == []


def test_itsm_init_preserves_custom_menu():
    from django.core.management import call_command

    from apps.system_mgmt.models import CustomMenuGroup

    CustomMenuGroup.objects.filter(app="itsm").delete()
    group = CustomMenuGroup.objects.create(app="itsm", display_name="我的菜单", is_enabled=True, menus=[{"name": "ticket"}])
    call_command("init_itsm", verbosity=0)
    group.refresh_from_db()
    assert CustomMenuGroup.objects.filter(app="itsm").count() == 1
    assert group.is_enabled and not group.is_build_in
    assert group.menus == [{"name": "ticket"}]


def test_reopen_resets_progress_but_preserves_history(sample):
    from apps.itsm.models import TicketLog, TicketTask

    ticket, task = sample
    service = TicketService()
    service.operate(ticket, task, "approve", {}, "handler")
    service.operate(ticket, None, "close", {}, "owner", privileged=True)
    service.operate(ticket, None, "reopen", {}, "owner", privileged=True)
    detail = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    assert detail["tasks"][0]["node_id"] == "submit"
    assert detail["tasks"][0]["assignee"] == ticket.creator
    nodes = {node["id"]: node for node in detail["nodes"]}
    assert nodes["submit"]["state"] == "current"
    assert nodes["approval_1"]["state"] == "waiting"
    assert not nodes["approval_1"]["assignees"]
    assert not nodes["approval_1"]["finished_at"]
    assert any(row.get("action") == "approve" for row in detail["history"])
    submit = TicketTask.objects.get(ticket=ticket, status="pending")
    submit.status = "done"
    submit.save()
    TicketLog.objects.create(ticket=ticket, task=submit, action="submit", operator="owner")
    detail = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    assert next(node for node in detail["nodes"] if node["id"] == "submit")["state"] == "done"


def test_ticket_history_exposes_only_row_and_job_record_reference(sample):
    from apps.itsm.models import AutoExecution

    ticket, _ = sample
    execution = AutoExecution.objects.create(
        ticket=ticket,
        kind="external",
        status="done",
        detail={
            "node_id": "inventory",
            "job_template": {
                "rows": [
                    {"row": 1, "job_id": 94, "params": "private"},
                    {"row": 2, "job_id": 95},
                ]
            },
        },
    )
    data = json.loads(ticket_detail(request(username="owner"), ticket.id).content)["data"]
    step = next(item for item in data["history"] if item.get("execution_id") == execution.id)
    assert step["job_records"] == [{"row": 1, "job_id": 94}, {"row": 2, "job_id": 95}]
