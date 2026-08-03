from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.alerts.common.notification_target import normalize_notification_target, read_notification_target, resolve_notification_target
from apps.alerts.models import Alert, AlertAssignment, AlertReminderTask
from apps.alerts.service.escalation_service import EscalationService
from apps.alerts.service.reminder_service import ReminderService
from apps.system_mgmt.models import Group, User


def test_legacy_personnel_is_normalized_as_user_target():
    assert normalize_notification_target(
        target=None,
        legacy_personnel=["alice", "alice", "bob"],
    ) == {
        "type": "user",
        "usernames": ["alice", "bob"],
        "organization_ids": [],
        "include_children": False,
    }


def test_invalid_structured_target_does_not_fall_back_to_legacy_personnel():
    assert normalize_notification_target(
        target={"type": "invalid"},
        legacy_personnel=["legacy-user"],
    ) == {
        "type": "user",
        "usernames": [],
        "organization_ids": [],
        "include_children": False,
    }


def test_explicit_null_target_is_invalid_while_missing_target_is_legacy():
    assert read_notification_target({}) is None
    assert read_notification_target({"notification_target": None}) == {}


@pytest.mark.django_db
def test_structured_user_target_filters_disabled_users_but_legacy_stays_compatible():
    User.objects.create(
        username="disabled-user",
        display_name="Disabled",
        email="disabled@example.com",
        password="x",
        disabled=True,
    )

    assert (
        resolve_notification_target(
            {
                "type": "user",
                "usernames": ["disabled-user"],
                "organization_ids": [],
                "include_children": False,
            }
        )
        == []
    )
    assert resolve_notification_target(None, ["disabled-user"]) == ["disabled-user"]


@pytest.mark.django_db
def test_organization_target_resolves_direct_active_members_only():
    parent = Group.objects.create(name="运维中心")
    child = Group.objects.create(name="一线组", parent_id=parent.id)
    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[parent.id],
    )
    User.objects.create(
        username="bob",
        display_name="Bob",
        email="bob@example.com",
        password="x",
        group_list=[child.id],
    )
    User.objects.create(
        username="disabled",
        display_name="Disabled",
        email="disabled@example.com",
        password="x",
        disabled=True,
        group_list=[parent.id],
    )

    assert resolve_notification_target(
        {
            "type": "organization",
            "organization_ids": [parent.id],
            "include_children": False,
        }
    ) == ["alice"]


@pytest.mark.django_db
def test_organization_target_with_deleted_group_resolves_empty():
    existing = Group.objects.create(name="仍存在")
    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[existing.id],
    )

    assert (
        resolve_notification_target(
            {
                "type": "organization",
                "organization_ids": [existing.id, 999999],
                "include_children": False,
            }
        )
        == []
    )


@pytest.mark.django_db
def test_reminder_uses_current_organization_members_without_changing_operators():
    group = Group.objects.create(name="动态值班组")
    User.objects.create(
        username="new-member",
        display_name="New Member",
        email="new@example.com",
        password="x",
        group_list=[group.id],
    )
    assignment = AlertAssignment.objects.create(
        name="组织分派",
        match_type="all",
        personnel=[],
        notify_channels=[{"id": 1, "channel_type": "email"}],
        config={
            "notification_target": {
                "type": "organization",
                "organization_ids": [group.id],
                "include_children": False,
            }
        },
    )
    alert = Alert.objects.create(
        alert_id="ORG-REMINDER",
        level="0",
        title="CPU 高",
        content="content",
        fingerprint="org-reminder",
        status="pending",
        operator=["initial-member"],
    )

    with (
        mock.patch(
            "apps.alerts.common.notify.dispatcher.build_channel_params",
            return_value=[{"channel_type": "email"}],
        ) as build_params,
        mock.patch(
            "apps.alerts.common.notify.dispatcher.enqueue_notifications",
            return_value=True,
        ),
    ):
        assert ReminderService._send_reminder_notification(
            assignment,
            alert,
        )

    assert build_params.call_args.args[0] == ["new-member"]
    alert.refresh_from_db()
    assert alert.operator == ["initial-member"]


@pytest.mark.django_db
def test_escalation_stays_on_empty_organization_until_member_appears():
    group = Group.objects.create(name="空二线组")
    assignment = AlertAssignment.objects.create(
        name="组织升级",
        match_type="all",
        personnel=["initial-member"],
        notify_channels=[{"id": 1, "channel_type": "email"}],
        config={
            "escalation": {
                "enabled": True,
                "mode": "append",
                "layers": [
                    {
                        "personnel": [],
                        "wait_minutes": 1,
                        "notify_channels": [],
                        "notification_target": {
                            "type": "organization",
                            "organization_ids": [group.id],
                            "include_children": False,
                        },
                    }
                ],
            }
        },
    )
    alert = Alert.objects.create(
        alert_id="ORG-ESCALATION",
        level="0",
        title="CPU 高",
        content="content",
        fingerprint="org-escalation",
        status="pending",
        operator=["initial-member"],
    )
    task = EscalationService.create_escalation_task(alert, assignment)
    task.layer_started_at = timezone.now() - timedelta(minutes=2)
    task.save(update_fields=["layer_started_at"])

    with mock.patch.object(
        EscalationService,
        "_send_escalation_notification",
        return_value=True,
    ) as send_notification:
        first_result = EscalationService.check_and_process_escalations()

    task.refresh_from_db()
    assert first_result["escalated"] == 0
    assert task.current_layer_index == 0
    assert task.is_active is True
    send_notification.assert_not_called()

    User.objects.create(
        username="second-line",
        display_name="Second Line",
        email="second@example.com",
        password="x",
        group_list=[group.id],
    )
    with mock.patch.object(
        EscalationService,
        "_send_escalation_notification",
        return_value=True,
    ) as send_notification:
        second_result = EscalationService.check_and_process_escalations()

    task.refresh_from_db()
    alert.refresh_from_db()
    assert second_result["escalated"] == 1
    assert task.current_layer_index == 1
    assert "second-line" in alert.operator
    assert send_notification.call_args.args[2] == [
        "initial-member",
        "second-line",
    ]


@pytest.mark.django_db
def test_empty_organization_reminder_reschedules_without_consuming_attempt():
    group = Group.objects.create(name="暂无值班人员")
    assignment = AlertAssignment.objects.create(
        name="空组织提醒",
        match_type="all",
        personnel=[],
        notify_channels=[{"id": 1, "channel_type": "email"}],
        config={
            "notification_target": {
                "type": "organization",
                "organization_ids": [group.id],
                "include_children": False,
            }
        },
    )
    alert = Alert.objects.create(
        alert_id="EMPTY-ORG-REMINDER",
        level="0",
        title="CPU 高",
        content="content",
        fingerprint="empty-org-reminder",
        status="pending",
        operator=["initial-member"],
    )
    reminder = AlertReminderTask.objects.create(
        alert=alert,
        assignment=assignment,
        is_active=True,
        reminder_count=0,
        current_frequency_minutes=5,
        current_max_reminders=3,
        next_reminder_time=timezone.now() - timedelta(minutes=1),
    )

    assert not ReminderService._send_reminder_notification(
        assignment,
        alert,
        reminder_id=reminder.pk,
    )

    reminder.refresh_from_db()
    assert reminder.reminder_count == 0
    assert reminder.next_reminder_time > timezone.now()
