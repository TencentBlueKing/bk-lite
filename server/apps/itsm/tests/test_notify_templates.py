from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from apps.console_mgmt.models import Notification
from apps.console_mgmt.viewsets.notification import NotificationViewSet
from apps.itsm.models import NotifyTemplate, Ticket, Workflow
from apps.itsm.serializers.org import NotifyTemplateSerializer
from apps.itsm.services.notify.service import dispatch_notification
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.signals import send_itsm_notification
from apps.system_mgmt.models import User
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannel, IMNotificationUserMapping
from apps.system_mgmt.models.integration_instance import IntegrationInstance

pytestmark = pytest.mark.django_db


def create_template(domain, channel_type, title, event="test.notice"):
    return NotifyTemplate.objects.create(
        domain=domain, channel_type=channel_type, event=event, title_tpl=title, content_tpl="{{ title }} · {{ content }}"
    )


def test_delivery_selects_template_for_the_event_domain_and_channel():
    create_template("elsewhere.example", "site", "其他组织")
    create_template("test.example", "site", "站内通知")
    create_template("test.example", "im", "即时通知")
    with patch("apps.itsm.services.notify.service._send_im_if_configured") as im:
        result = dispatch_notification("test.notice", {"title": "服务申请", "content": "等待办理"}, ["tester"], domain="test.example")
    assert result["title"] == "站内通知"
    assert Notification.objects.get().content == "站内通知\n服务申请 · 等待办理"
    im.assert_called_once_with("即时通知", "服务申请 · 等待办理", ["tester"], domain="test.example")


def test_template_defaults_do_not_read_a_different_domain():
    create_template("elsewhere.example", "site", "其他组织")
    with patch("apps.itsm.services.notify.service._send_im_if_configured") as im:
        dispatch_notification("test.notice", {"title": "原始标题"}, ["tester"], site_only=True, domain="test.example")
    assert Notification.objects.get().content == "原始标题\n原始标题"
    im.assert_not_called()


def test_site_delivery_is_visible_only_to_the_matching_domain_and_is_idempotent():
    for _ in range(2):
        dispatch_notification("test.notice", {"title": "原始标题"}, ["tester"], "test.notice:1", site_only=True, domain="test.example")
    notification = Notification.objects.get()
    assert notification.recipient_domain == "test.example"
    view = NotificationViewSet()
    view.request = SimpleNamespace(user=SimpleNamespace(username="tester", domain="elsewhere.example"))
    assert not view._visible_notifications().exists()
    view.request.user.domain = "test.example"
    assert list(view._visible_notifications()) == [notification]
    dispatch_notification("test.notice", {}, [], site_only=True, domain="test.example")
    dispatch_notification("test.notice", {}, ["tester"], site_only=True)
    assert Notification.objects.count() == 1


def test_delivery_keeps_every_recipient_when_site_batch_exceeds_twenty():
    receivers = [f"tester{i}" for i in range(22)]
    for _ in range(2):
        dispatch_notification("test.notice", {}, receivers, "test.notice:batch", site_only=True, domain="test.example")
    batches = list(Notification.objects.order_by("id").values_list("recipient_usernames", flat=True))
    assert batches == [receivers[:20], receivers[20:]]


def test_im_routes_each_user_to_one_ready_channel_with_their_mapping():
    local = User.objects.create(domain="test.example", username="tester")
    local_second = User.objects.create(domain="test.example", username="second")
    remote = User.objects.create(domain="other.example", username="tester")
    unmapped = User.objects.create(domain="test.example", username="unmapped")
    unavailable = IntegrationInstance.objects.create(
        name="Unavailable", provider_key="feishu", status="ready", capability_enabled={"im_notification": False}
    )
    integrations = [
        IntegrationInstance.objects.create(name=provider, provider_key=provider, status="ready", capability_status={"im_notification": "ready"})
        for provider in ("feishu", "wecom")
    ]
    ignored = IMNotificationChannel.objects.create(name="Unavailable", integration_instance=unavailable, status="ready")
    first, second = [
        IMNotificationChannel.objects.create(name=instance.name, integration_instance=instance, status="ready") for instance in integrations
    ]
    for channel, user in [(ignored, local), (first, local), (first, remote), (second, local), (second, local_second)]:
        IMNotificationUserMapping.objects.create(
            channel=channel,
            user=user,
            external_identity_value=str(user.id),
            external_receive_key="external_id",
            external_snapshot={"external_id": str(user.id)},
        )
    IMNotificationUserMapping.objects.create(channel=first, user=unmapped, external_identity_value="missing")
    with patch("apps.itsm.services.notify.service.SystemMgmt") as system:
        send = system.return_value.send_msg_with_channel
        send.side_effect = [RuntimeError("提供方请求结果未知"), {"result": True}]
        result = dispatch_notification("test.notice", {"title": "待办"}, ["tester", "second", "unmapped"], domain="test.example")
    assert send.call_args_list == [
        call(first.id, "待办", "待办", [local.id], channel_type="im_notification"),
        call(second.id, "待办", "待办", [local_second.id], channel_type="im_notification"),
    ]
    assert result["im"]["result"] is True
    assert result["im"]["partial_success"] is True
    assert Notification.objects.get().recipient_usernames == ["tester", "second", "unmapped"]


def test_invalid_saved_template_falls_back_to_event_content():
    create_template("test.example", "site", "{% if broken %}")
    result = dispatch_notification("test.notice", {"title": "原始标题"}, ["tester"], site_only=True, domain="test.example")
    assert result["title"] == "原始标题"


def test_template_form_validates_channel_and_template_syntax():
    payload = {"event": "test.notice", "title_tpl": "新待办", "content_tpl": "{{ title }}", "channel_type": "im"}
    serializer = NotifyTemplateSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["channel_type"] == "im"
    assert not NotifyTemplateSerializer(data={**payload, "channel_type": "unavailable"}).is_valid()
    invalid = NotifyTemplateSerializer(data={**payload, "content_tpl": "{% if incomplete %}"})
    assert not invalid.is_valid() and "content_tpl" in invalid.errors


def test_new_task_renders_ticket_fields_in_im_without_changing_the_site_link(django_capture_on_commit_callbacks):
    workflow = Workflow.objects.create(domain="test.example", name="服务申请流程", key="notice-test")
    ticket = Ticket.objects.create(
        domain=workflow.domain, workflow=workflow, sn="REQ-NOTICE-1", title="更换设备", creator="owner", process_instance_id="process-1"
    )
    NotifyTemplate.objects.create(
        domain=ticket.domain,
        event="task.created",
        channel_type="im",
        title_tpl="工单待办 {{ sn }}",
        content_tpl="{{ ticket_title }} · {{ workflow }} · {{ node }} · {{ ticket_path }}",
    )
    client = SimpleNamespace(
        list_tasks_including_children=lambda _: [{"id": "task-1", "assignee": "handler", "taskDefinitionKey": "handle", "name": "部门审批"}]
    )
    with patch("apps.itsm.services.notify.service._send_im_if_configured") as send_im, django_capture_on_commit_callbacks(execute=True):
        TicketService(client).sync_ticket(ticket)
    send_im.assert_called_once_with("工单待办 REQ-NOTICE-1", f"更换设备 · 服务申请流程 · 部门审批 · /itsm/tickets/{ticket.id}", ["handler"], domain=ticket.domain)
    assert Notification.objects.get().target_url == f"/itsm/tickets/{ticket.id}"


def test_ticket_event_uses_sender_domain():
    with patch("apps.itsm.signals.deliver_with_retry") as deliver:
        send_itsm_notification(SimpleNamespace(domain="test.example", is_test=True), "task.created", ["tester"], {"title": "服务申请"})
    assert deliver.call_args.kwargs["domain"] == "test.example"
    assert deliver.call_args.kwargs["site_only"] is True
