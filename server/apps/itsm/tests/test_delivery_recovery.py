from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.itsm.models import EmailRule, KnowledgeArticle, Service, TicketComment, TicketFollower
from apps.itsm.models.integration import Integration, TodoDelivery
from apps.itsm.services import external_jobs, todo_sync
from apps.itsm.tasks import email_poll
from apps.itsm.tests.test_review_regressions import sample as sample_fixture

sample = sample_fixture
pytestmark = pytest.mark.django_db


def test_stale_todo_requires_reconciliation_before_resend(sample):
    ticket, _ = sample
    Integration.objects.create(name="待办", kind="todo")
    todo_sync.sync_todos(ticket.pk)
    row = TodoDelivery.objects.get()
    TodoDelivery.objects.update(status="running", updated_at=timezone.now() - timedelta(hours=1))
    with patch.object(todo_sync, "send_payload") as send:
        todo_sync.drain_deliveries()
        row.refresh_from_db()
        assert row.status == "unknown" and "核对" in row.code
        send.assert_not_called()
        todo_sync.deliver(row.pk)
        send.assert_not_called()
        from apps.itsm.tests.test_integrations import req
        from apps.itsm.views.integrations import reconcile_delivery

        outcome = {"received": False, "attempts": row.attempts}
        assert reconcile_delivery(req("post", outcome, ["data-View"]), row.integration_id, row.pk).status_code == 403
        assert reconcile_delivery(req("post", outcome), row.integration_id, row.pk).status_code == 200
        todo_sync.drain_deliveries()
        assert send.call_args.args[1]["event_id"] == row.event_key


def test_follower_notice_recovers_without_commit_callback(sample):
    from apps.itsm.services.trigger_delivery import drain_trigger_notices
    from apps.console_mgmt.models import Notification

    ticket, _ = sample
    TicketFollower.objects.create(ticket=ticket, username="reader")
    comment = TicketComment.objects.create(ticket=ticket, created_by="owner", content="更新")
    drain_trigger_notices()
    drain_trigger_notices()
    assert Notification.objects.filter(event_key=f"itsm-follow-TicketComment-{comment.pk}").count() == 1


def test_email_routes_and_deduplicates_replayed_files(sample, tmp_path, monkeypatch):
    ticket, _ = sample
    ticket.workflow.current_version = ticket.workflow_version
    ticket.workflow.save()
    service = Service.objects.create(name="收件服务", workflow=ticket.workflow)
    EmailRule.objects.create(name="隔离", mailbox="other@example.org", domain="foreign", is_enabled=True, service_id=service.pk)
    EmailRule.objects.create(name="正式", mailbox="itsm@example.org", is_enabled=True, service_id=service.pk)
    monkeypatch.setenv("ITSM_MAIL_DIR", str(tmp_path))
    for index, address in enumerate(["itsm@example.org", "itsm@example.org", "other@example.org", "unknown@example.org"]):
        (tmp_path / f"{index}.eml").write_bytes(f"To: {address}\nSubject: mail\nMessage-ID: <one@example.org>\n\nbody".encode())
    with patch("apps.itsm.views.tickets._service") as factory:
        factory.return_value.create.return_value = ticket
        assert email_poll()["created"] == 1
        assert factory.return_value.create.call_args.kwargs.get("service") == service
        assert not factory.return_value.create.call_args.kwargs.get("is_test")


def test_notice_key_identifies_each_job_arrival(sample):
    ticket, _ = sample
    with patch("apps.itsm.services.notify.service.dispatch_notification", return_value={"site": {"result": True}}) as send:
        for job_id in ["first", "first", "second"]:
            external_jobs.execute_node(ticket, {"id": "n", "type": "notice", "auto": {"receivers": ["owner"]}}, job_id=job_id)
    keys = [call.kwargs["event_key"] for call in send.call_args_list]
    assert keys[0] == keys[1] and keys[1] != keys[2]


def test_knowledge_node_rejects_empty_and_links_source(sample):
    ticket, _ = sample
    with pytest.raises(external_jobs.ActionFailure, match="正文"):
        external_jobs.execute_node(ticket, {"type": "knowledge", "auto": {"content": "   "}})
    result = external_jobs.execute_node(ticket, {"type": "knowledge", "auto": {"content": "说明"}})
    assert KnowledgeArticle.objects.get(pk=result["article_id"]).tickets.get() == ticket


def test_expired_notice_recipient_cannot_receive_during_recovery(sample):
    from apps.itsm.services.trigger_notice import TriggerNotice, deliver_configured_notice, resolve_notice
    from apps.system_mgmt.models import User

    ticket, _ = sample
    recipient = User.objects.create(domain=ticket.domain, username="owner", display_name="owner")
    notice = TriggerNotice.model_validate({"recipients": {"roles": ["creator"]}, "channels": [{"type": "site"}]})
    recipients, variables = resolve_notice(ticket, notice)
    assert recipients == [(recipient.pk, "owner")]
    User.objects.filter(pk=recipient.pk).update(account_expires_at=timezone.now() - timedelta(seconds=1))
    assert resolve_notice(ticket, notice)[0] == []
    with patch("apps.itsm.services.trigger_notice.send_site_notification") as send:
        ok, _ = deliver_configured_notice(notice, variables, recipients, domain=ticket.domain, event_key="expiry", is_test=False, im_sender=None)
    assert not ok
    send.assert_not_called()


def test_commit_enqueues_workers_without_doing_network_io(sample, django_capture_on_commit_callbacks):
    from apps.itsm.services.knowledge_attachments import queue_attachment_cleanup
    from apps.itsm.services.trigger_delivery import schedule_delivery
    from apps.itsm.tasks import knowledge_attachment_cleanup, trigger_notice_tick

    with (
        patch.object(knowledge_attachment_cleanup, "apply_async") as cleanup,
        patch.object(trigger_notice_tick, "apply_async") as notice,
        patch("apps.itsm.services.knowledge_attachments.storage_client") as storage,
        patch("apps.itsm.services.trigger_delivery.deliver_trigger_notice") as deliver,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            schedule_delivery(123)
            queue_attachment_cleanup(["object"])
            cleanup.assert_not_called()
            notice.assert_not_called()
        cleanup.assert_called_once()
        notice.assert_called_once()
        storage.assert_not_called()
        deliver.assert_not_called()


def test_task_notice_persists_with_task_and_notifications_roll_back_together(sample):
    from types import SimpleNamespace

    from django.db import transaction

    from apps.itsm.models.integration import TicketNoticeDelivery
    from apps.itsm.services.ticket.service import TicketService

    ticket, _ = sample
    ticket.process_instance_id = "process"
    ticket.save()
    service = TicketService(
        SimpleNamespace(
            list_tasks_including_children=lambda _: [
                {"id": "new-task", "assignee": "worker", "taskDefinitionKey": "review", "name": "复核"},
            ]
        )
    )
    with pytest.raises(RuntimeError), transaction.atomic():
        service.sync_ticket(ticket)
        assert TicketNoticeDelivery.objects.get().event_key == "itsm-task-new-task"
        raise RuntimeError("回滚")
    assert not TicketNoticeDelivery.objects.exists()
    assert not ticket.tasks.filter(flowable_task_id="new-task").exists()
    service.sync_ticket(ticket)
    service.sync_ticket(ticket)
    assert TicketNoticeDelivery.objects.get().delivery_payload["recipients"] == ["worker"]


def test_email_failure_does_not_block_next_file_and_recovers_with_same_key(sample, tmp_path, monkeypatch):
    from apps.itsm.models.integration import EmailReceipt

    ticket, _ = sample
    ticket.workflow.current_version = ticket.workflow_version
    ticket.workflow.save()
    service = Service.objects.create(name="服务", workflow=ticket.workflow)
    EmailRule.objects.create(mailbox="desk@example.org", service_id=service.pk, is_enabled=True)
    monkeypatch.setenv("ITSM_MAIL_DIR", str(tmp_path))
    for key in ["uncertain", "good"]:
        (tmp_path / f"{key}.eml").write_text(f"Delivered-To: DESK@example.org\nSubject: {key}\nMessage-ID: <{key}>\n\nbody")
    calls = []

    def create(version, data, actor, **options):
        key = options["creation_key"]
        if data["title"] == "uncertain":
            calls.append(key)
            if len(calls) == 1:
                raise ConnectionError()
        return ticket

    with patch("apps.itsm.views.tickets._service") as factory:
        factory.return_value.create.side_effect = create
        assert email_poll() == {"checked": 2, "created": 1}
        assert email_poll() == {"checked": 1, "created": 0}
        EmailReceipt.objects.filter(status="running").update(claimed_at=timezone.now() - timedelta(minutes=6))
        assert email_poll() == {"checked": 1, "created": 1}
    assert len(calls) == 2 and calls[0] == calls[1]
    assert EmailReceipt.objects.filter(ticket=ticket, status="done").count() == 2


def test_email_with_ambiguous_or_disabled_recipient_never_routes(sample, tmp_path, monkeypatch):
    ticket, _ = sample
    ticket.workflow.current_version = ticket.workflow_version
    ticket.workflow.save()
    service = Service.objects.create(name="邮件", workflow=ticket.workflow)
    local = EmailRule.objects.create(mailbox="team@example.org", is_enabled=True, service_id=service.pk)
    foreign = EmailRule.objects.create(domain="other.example", mailbox="team@example.org", is_enabled=True, service_id=service.pk)
    monkeypatch.setenv("ITSM_MAIL_DIR", str(tmp_path))
    (tmp_path / "in.eml").write_text("To: team@example.org\nSubject: ambiguous\n\nbody")
    with patch("apps.itsm.views.tickets._service") as factory:
        assert email_poll()["created"] == 0
        foreign.delete()
        service.is_enabled = False
        service.save()
        assert email_poll()["created"] == 0
        service.is_enabled = True
        service.save()
        local.is_enabled = False
        local.save()
        assert email_poll()["created"] == 0
        factory.assert_not_called()


def test_legacy_notice_skips_reassigned_username_between_commit_and_worker(sample):
    from apps.console_mgmt.models import Notification
    from apps.itsm.models import Trigger
    from apps.itsm.services.trigger_delivery import drain_trigger_notices
    from apps.itsm.services.triggers import fire_triggers
    from apps.system_mgmt.models import User

    ticket, _ = sample
    user = User.objects.create(username=ticket.creator, domain=ticket.domain)
    rule = Trigger.objects.create(name="旧规则", event="ticket_update", action="notice")
    fire_triggers(ticket, "save", ticket.creator)
    user.delete()
    User.objects.create(username=ticket.creator, domain=ticket.domain)
    drain_trigger_notices()
    assert not Notification.objects.filter(event_key=f"itsm-trigger-{rule.logs.get().pk}").exists()
    assert rule.logs.get().status == "failed"


@pytest.mark.parametrize("lost_response", [True, False])
def test_todo_uncertain_transport_requires_manual_reconciliation(sample, lost_response):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from requests.exceptions import ReadTimeout

    from apps.itsm.tests.test_integrations import req
    from apps.itsm.views.integrations import reconcile_delivery, retry_delivery

    ticket, _ = sample
    integration = Integration.objects.create(name="送达核对", kind="todo", config={"url": "https://receiver.example.test/"})
    todo_sync.sync_todos(ticket.pk)
    row = TodoDelivery.objects.get()
    with (
        patch("apps.core.utils.safe_requests.SSRFValidator.validate_target", return_value=SimpleNamespace(url=integration.config["url"])),
        patch("apps.core.utils.safe_requests.get_egress_gateway") as gateway,
    ):
        send = gateway.return_value.send
        if lost_response:
            send.side_effect = ReadTimeout()
        else:
            send.return_value = Mock(status_code=503, is_redirect=False)
        todo_sync.deliver(row.pk)
        row.refresh_from_db()
        assert row.status == "unknown" and "核对" in row.code
        assert retry_delivery(req("post"), integration.pk, row.pk).status_code == 400
        assert reconcile_delivery(req("post", {"attempts": row.attempts, "received": True}), integration.pk, row.pk).status_code == 200
        todo_sync.drain_deliveries()
        row.refresh_from_db()
        assert row.status == "done"
        send.assert_called_once()


def test_real_mail_creation_recovers_engine_reply_loss_and_archival_replay(tmp_path, monkeypatch, settings):
    from apps.itsm.flowable.client import FlowableError
    from apps.itsm.models import Ticket, Workflow, WorkflowVersion
    from apps.itsm.models.integration import EmailReceipt, TicketNoticeDelivery

    workflow = Workflow.objects.create(name="收件流程", key="mail-flow")
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        is_published=True,
        process_definition_key=workflow.key,
        process_definition_id="mail-flow:1:deployed",
        design={},
    )
    workflow.current_version = version
    workflow.save()
    service = Service.objects.create(name="正式收件", workflow=workflow)
    EmailRule.objects.create(name="收件", mailbox="service@example.org", service_id=service.pk, is_enabled=True)
    settings.FLOWABLE_PASSWORD = "test-fixture"
    monkeypatch.setenv("ITSM_MAIL_DIR", str(tmp_path))
    mail = tmp_path / "first.eml"
    raw = b"To: SERVICE@example.org\r\nSubject: Support\r\nMessage-ID: <case@sender.example>\r\n\r\nHelp"
    mail.write_bytes(raw)

    with patch("apps.itsm.views.tickets.FlowableClient") as gateway:
        engine = gateway.return_value
        engine.start_process.side_effect = FlowableError(0, "")
        engine.instance_for_business_key.return_value = "started-instance"
        engine.list_tasks_including_children.return_value = [{"id": "mail-task", "assignee": "agent", "taskDefinitionKey": "review"}]
        assert email_poll() == {"checked": 1, "created": 0}
        receipt = EmailReceipt.objects.get()
        ticket = Ticket.objects.get()
        assert ticket.creation_state == "starting" and ticket.creation_key == f"email-{receipt.pk}"
        assert ticket.service == service and not ticket.is_test
        assert email_poll() == {"checked": 1, "created": 0}

        EmailReceipt.objects.filter(pk=receipt.pk).update(claimed_at=timezone.now() - timedelta(minutes=6))
        assert email_poll() == {"checked": 1, "created": 1}
        assert mail.with_suffix(".eml.done").read_bytes() == raw
        (tmp_path / "replayed.eml").write_bytes(raw)
        assert email_poll() == {"checked": 1, "created": 0}

        receipt.refresh_from_db()
        ticket.refresh_from_db()
        assert receipt.ticket_id == ticket.pk and receipt.status == "done"
        assert ticket.process_instance_id == "started-instance" and ticket.creation_state == "complete"
        assert Ticket.objects.count() == EmailReceipt.objects.count() == 1
        assert TicketNoticeDelivery.objects.get().event_key == "itsm-task-mail-task"
        engine.start_process.assert_called_once()
        engine.instance_for_business_key.assert_called_once_with(ticket.sn, version.process_definition_id)
