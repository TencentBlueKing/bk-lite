import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import DatabaseError

from apps.console_mgmt.models import Notification
from apps.console_mgmt.viewsets.notification import NotificationViewSet
from apps.itsm.models import ServiceCalendar, SLAPolicy, Ticket, TicketTask, Workflow
from apps.itsm.services import sla, sla_notices
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.m2 import sla_settings
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db
LOCAL = ZoneInfo("Asia/Shanghai")
FRIDAY = datetime(2026, 11, 20, 17, 40, tzinfo=LOCAL)
MONDAY = datetime(2026, 11, 23, 9, 0, tzinfo=LOCAL)


@pytest.fixture
def sample():
    workflow = Workflow.objects.create(key="sla", name="SLA 流程")
    calendar = ServiceCalendar.objects.create(name="服务窗口", work_days=[1, 2, 3, 4, 5])
    policy = SLAPolicy.objects.create(
        name="响应计时",
        workflow=workflow,
        calendar=calendar,
        target="response",
        minutes=30,
        warning_minutes=15,
        escalation_users=["lead"],
    )
    ticket = Ticket.objects.create(sn="SLA-1", title="SLA 验收", workflow=workflow, creator="owner")
    User.objects.bulk_create(
        [
            User(username="handler", display_name="处理人"),
            User(username="lead", display_name="升级人"),
            User(username="lead", display_name="其他域同名", domain="other"),
        ]
    )
    TicketTask.objects.create(ticket=ticket, node_id="approve", assignee="handler")
    with patch.object(sla.timezone, "now", return_value=FRIDAY):
        sla.open_records(ticket)
    return ticket, policy


def test_pause_freezes_business_seconds_then_warning_and_escalation_fire_once(sample):
    ticket, _ = sample
    record = ticket.sla_records.get()
    assert record.due_at == MONDAY + timedelta(minutes=10)
    assert record.warning_at == FRIDAY + timedelta(minutes=15)
    pause_at = FRIDAY + timedelta(minutes=10, seconds=30)
    with patch.object(sla.timezone, "now", return_value=pause_at):
        sla.pause(ticket)
    assert sla_notices.scan(now=MONDAY + timedelta(minutes=12))["processed"] == 0
    record.refresh_from_db()
    assert record.due_at == MONDAY + timedelta(minutes=10)
    assert not record.breached
    resumed = MONDAY + timedelta(minutes=12, seconds=45)
    with patch.object(sla.timezone, "now", return_value=resumed):
        sla.resume(ticket)
    record.refresh_from_db()
    assert not record.paused_at
    assert record.paused_seconds == 1335
    assert record.warning_at == resumed + timedelta(minutes=4, seconds=30)
    assert record.due_at == resumed + timedelta(minutes=19, seconds=30)
    assert sla_notices.scan(now=record.warning_at - timedelta(seconds=1))["processed"] == 0
    assert sla_notices.scan(now=record.warning_at)["processed"] == 1
    assert sla_notices.scan(now=record.warning_at)["processed"] == 0
    assert sla_notices.scan(now=record.due_at)["processed"] == 1
    assert sla_notices.scan(now=record.due_at)["processed"] == 0
    assert list(record.notices.order_by("id").values_list("kind", "recipients", "status")) == [
        ("warning", ["handler"], "sent"),
        ("escalation", ["lead"], "sent"),
    ]
    assert Notification.objects.filter(app_module="itsm").count() == 2
    view = NotificationViewSet()
    view.request = SimpleNamespace(user=SimpleNamespace(username="lead", domain="other"))
    assert not view._visible_notifications().filter(app_module="itsm").exists()
    view.request.user.domain = "domain.com"
    assert view._visible_notifications().filter(app_module="itsm").count() == 1
    record.refresh_from_db()
    assert record.breached


def test_finished_during_pause_does_not_breach_or_notify(sample):
    ticket, _ = sample
    with patch.object(sla.timezone, "now", return_value=FRIDAY + timedelta(minutes=10)):
        sla.pause(ticket)
    with patch.object(sla.timezone, "now", return_value=MONDAY + timedelta(hours=1)):
        sla.finish(ticket, "response")
    record = ticket.sla_records.get()
    assert record.finished_at
    assert not record.breached
    assert sla_notices.scan(now=MONDAY + timedelta(hours=2))["processed"] == 0


def test_no_assignee_does_not_create_a_broadcast_notice(sample):
    ticket, _ = sample
    ticket.tasks.all().delete()
    record = ticket.sla_records.get()
    sla_notices.scan(now=record.warning_at)
    notice = record.notices.get()
    assert notice.status == "skipped"
    assert notice.recipients == []
    assert not Notification.objects.filter(app_module="itsm").exists()


def test_notification_write_failure_is_recorded_without_replaying(sample):
    ticket, _ = sample
    record = ticket.sla_records.get()
    with patch.object(sla_notices, "create_targeted_notification", side_effect=DatabaseError("private")) as send:
        assert sla_notices.scan(now=record.warning_at)["processed"] == 1
        assert sla_notices.scan(now=record.warning_at)["processed"] == 0
        send.assert_called_once()
    notice = record.notices.get()
    assert notice.status == "failed"
    assert notice.recipients == ["handler"]
    assert "private" not in notice.message
    assert not Notification.objects.filter(app_module="itsm").exists()


def test_policy_checks_domain_and_preserves_existing_clock(sample):
    ticket, policy = sample
    permission = ["workflow-Edit"]
    user = {"username": "owner", "permissions": permission}
    record = ticket.sla_records.get()
    foreign = ServiceCalendar.objects.create(name="外域", domain="other")
    assert sla_settings(request("post", {"policy_id": policy.id, "calendar_id": foreign.id}, **user)).status_code == 404
    assert sla_settings(request("post", {"policy_id": policy.id, "escalation_users": ["foreign"]}, **user)).status_code == 400
    result = sla_settings(request("post", {"policy_id": policy.id, "warning_minutes": 10, "escalation_users": ["lead"]}, **user))
    assert json.loads(result.content)["result"]
    policy.refresh_from_db()
    assert policy.warning_minutes == 10
    record.refresh_from_db()
    assert record.warning_at == FRIDAY + timedelta(minutes=15)
