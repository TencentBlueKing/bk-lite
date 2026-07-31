from importlib import import_module

import pytest
from django.apps import apps
from django.utils import timezone

from apps.apm.models import ApmAlertOutbox, ApmPolicy, ApmPolicyNotificationTarget, ApmService


pytestmark = pytest.mark.django_db


def test_legacy_notification_data_maps_deterministically_and_can_restore():
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    policy = ApmPolicy.objects.create(
        name="错误率",
        service=service,
        environment="prod",
        metric_type="error_rate",
        comparator="gt",
        threshold="0.1",
        duration_window=1,
        recovery_window=1,
        severity="error",
        notice=True,
        notice_type_ids=[9, "7", 9, "invalid"],
        notice_users=["42", "on-call"],
    )
    outbox = ApmAlertOutbox.objects.create(
        event_key="legacy:event:7",
        channel_id=7,
        receivers=["42"],
        payload={"title": "触发", "description": "错误率过高"},
        delivery_status="delivered",
    )
    migration = import_module("apps.apm.migrations.0004_notification_targets_and_delivery_state")

    migration.migrate_legacy_notification_configuration(apps, None)

    targets = list(ApmPolicyNotificationTarget.objects.filter(policy=policy).order_by("channel_id"))
    assert [target.channel_id for target in targets] == [7, 9]
    assert all(target.delivery_mode == "alert_event_copy" for target in targets)
    assert all(target.recipient_mode == "none" for target in targets)
    outbox.refresh_from_db()
    assert outbox.recipients == ["42"]
    assert outbox.title == "触发"
    assert outbox.body == "错误率过高"
    assert outbox.delivered_at is not None

    policy.notice = False
    policy.notice_type_ids = []
    policy.notice_users = []
    policy.save()
    migration.restore_legacy_notification_configuration(apps, None)
    policy.refresh_from_db()
    assert policy.notice is True
    assert policy.notice_type_ids == [7, 9]
    assert policy.notice_users == ["42", "on-call"]
