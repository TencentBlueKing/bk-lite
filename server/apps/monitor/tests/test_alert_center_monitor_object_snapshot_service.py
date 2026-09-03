"""Monitor 推送到告警中心的对象身份快照契约。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

import apps.node_mgmt.models  # noqa: F401
from apps.monitor.models import MonitorAlert, MonitorAlertCenterDelivery
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.services import alert_lifecycle_notify
from apps.monitor.services.alert_center_delivery import enqueue_alert_center_deliveries
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.system_mgmt.models import Channel

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_monitor_alert_center_payload_contains_monitor_and_cmdb_identity(monkeypatch):
    channel = Channel.objects.create(
        name="告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monitor_object = MonitorObject.objects.create(name="Host", display_name="主机")
    monitor_instance = MonitorInstance.objects.create(
        id="0001",
        name="ip1",
        monitor_object=monitor_object,
        cmdb_id="550e8400-e29b-41d4-a716-446655440000",
    )
    alert = MonitorAlert.objects.create(
        policy_id=7,
        monitor_instance_id=monitor_instance.id,
        monitor_instance_name=monitor_instance.name,
        metric_instance_id="cpu_usage",
        content="CPU usage exceeded 81%",
        level="warning",
        value=81,
        status="new",
        start_event_time=datetime(2026, 9, 3, 2, 42, 26, tzinfo=timezone.utc),
        notice_type_ids=[channel.id],
        dimensions={"region": "us-east"},
    )
    notifier = AlertLifecycleNotifier(
        policy=SimpleNamespace(
            id=7,
            name="CPU 使用率",
            organizations=[1],
            notice=True,
            monitor_object=monitor_object,
        )
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_DELIVERY_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.probe_notification_channel",
        lambda channel_id, capability_only=False: {"delivery_mode": "alert_event_copy"},
    )

    enqueue_alert_center_deliveries([alert], "created", notifier=notifier)

    payload = MonitorAlertCenterDelivery.objects.get(alert=alert).payload
    assert {
        "monitor_id": payload.get("monitor_id"),
        "cmdb_id": payload.get("cmdb_id"),
        "resource_id": payload.get("resource_id"),
        "resource_type": payload.get("resource_type"),
        "resource_name": payload.get("resource_name"),
    } == {
        "monitor_id": "0001",
        "cmdb_id": "550e8400-e29b-41d4-a716-446655440000",
        "resource_id": "0001",
        "resource_type": "Host",
        "resource_name": "ip1",
    }
    assert payload["external_id"] == str(alert.id)
    assert payload["action"] == "created"
    assert payload["organizations"] == [1]
    assert payload["tags"] == {"region": "us-east"}
    assert payload["labels"] == {
        "policy_name": "CPU 使用率（主机）",
        "metric_instance_id": "cpu_usage",
        "operator": "",
        "reason": "",
        "status": "new",
    }


def test_unlinked_monitor_instance_is_still_present_in_payload(monkeypatch):
    channel = Channel.objects.create(
        name="告警中心-未关联",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monitor_object = MonitorObject.objects.create(name="Switch", display_name="交换机")
    monitor_instance = MonitorInstance.objects.create(
        id="0002",
        name="ip2",
        monitor_object=monitor_object,
        cmdb_id=None,
    )
    alert = MonitorAlert.objects.create(
        policy_id=8,
        monitor_instance_id=monitor_instance.id,
        monitor_instance_name=monitor_instance.name,
        metric_instance_id="if_status",
        content="Interface down",
        level="warning",
        status="new",
        start_event_time=datetime(2026, 9, 3, 3, tzinfo=timezone.utc),
        notice_type_ids=[channel.id],
    )
    notifier = AlertLifecycleNotifier(
        policy=SimpleNamespace(
            id=8,
            name="端口状态",
            organizations=[1],
            notice=True,
            monitor_object=monitor_object,
        )
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.probe_notification_channel",
        lambda channel_id, capability_only=False: {"delivery_mode": "alert_event_copy"},
    )

    enqueue_alert_center_deliveries([alert], "created", notifier=notifier)

    payload = MonitorAlertCenterDelivery.objects.get(alert=alert).payload
    assert {
        "monitor_id": payload["monitor_id"],
        "cmdb_id": payload["cmdb_id"],
        "resource_type": payload["resource_type"],
        "resource_name": payload["resource_name"],
    } == {
        "monitor_id": "0002",
        "cmdb_id": None,
        "resource_type": "Switch",
        "resource_name": "ip2",
    }


def test_monitor_identity_snapshot_uses_one_batch_query(monkeypatch):
    channel = Channel.objects.create(
        name="告警中心-批量",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monitor_object = MonitorObject.objects.create(name="BatchHost")
    instances = [
        MonitorInstance.objects.create(
            id=f"batch-{index}",
            name=f"host-{index}",
            monitor_object=monitor_object,
        )
        for index in range(2)
    ]
    alerts = [
        MonitorAlert.objects.create(
            policy_id=9,
            monitor_instance_id=instance.id,
            monitor_instance_name=instance.name,
            metric_instance_id="cpu_usage",
            content="CPU high",
            level="warning",
            status="new",
            start_event_time=datetime(2026, 9, 3, 4, index, tzinfo=timezone.utc),
            notice_type_ids=[channel.id],
        )
        for index, instance in enumerate(instances)
    ]
    notifier = AlertLifecycleNotifier(
        policy=SimpleNamespace(
            id=9,
            name="批量策略",
            organizations=[1],
            notice=True,
            monitor_object=monitor_object,
        )
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.probe_notification_channel",
        lambda channel_id, capability_only=False: {"delivery_mode": "alert_event_copy"},
    )

    with CaptureQueriesContext(connection) as queries:
        enqueue_alert_center_deliveries(alerts, "created", notifier=notifier)

    identity_queries = [query["sql"] for query in queries.captured_queries if 'FROM "monitor_monitorinstance"' in query["sql"]]
    assert len(identity_queries) == 1


def test_saved_outbox_payload_keeps_original_cmdb_snapshot(monkeypatch):
    channel = Channel.objects.create(
        name="告警中心-快照",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monitor_object = MonitorObject.objects.create(name="SnapshotHost")
    instance = MonitorInstance.objects.create(
        id="snapshot-1",
        name="snapshot-host",
        monitor_object=monitor_object,
        cmdb_id="cmdb-before",
    )
    alert = MonitorAlert.objects.create(
        policy_id=10,
        monitor_instance_id=instance.id,
        monitor_instance_name=instance.name,
        metric_instance_id="cpu_usage",
        content="CPU high",
        level="warning",
        status="new",
        start_event_time=datetime(2026, 9, 3, 5, tzinfo=timezone.utc),
        notice_type_ids=[channel.id],
    )
    notifier = AlertLifecycleNotifier(
        policy=SimpleNamespace(
            id=10,
            name="快照策略",
            organizations=[1],
            notice=True,
            monitor_object=monitor_object,
        )
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.probe_notification_channel",
        lambda channel_id, capability_only=False: {"delivery_mode": "alert_event_copy"},
    )

    enqueue_alert_center_deliveries([alert], "created", notifier=notifier)
    delivery = MonitorAlertCenterDelivery.objects.get(alert=alert)
    MonitorInstance.objects.filter(pk=instance.pk).update(cmdb_id="cmdb-after")

    delivery.refresh_from_db()
    assert delivery.payload["cmdb_id"] == "cmdb-before"


def test_missing_monitor_instance_keeps_alert_identity_with_policy_type(monkeypatch):
    channel = Channel.objects.create(
        name="告警中心-实例缺失",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monitor_object = MonitorObject.objects.create(name="DeletedHost")
    alert = MonitorAlert.objects.create(
        policy_id=11,
        monitor_instance_id="deleted-1",
        monitor_instance_name="deleted-host",
        metric_instance_id="cpu_usage",
        content="CPU high",
        level="warning",
        status="new",
        start_event_time=datetime(2026, 9, 3, 6, tzinfo=timezone.utc),
        notice_type_ids=[channel.id],
    )
    notifier = AlertLifecycleNotifier(
        policy=SimpleNamespace(
            id=11,
            name="实例删除策略",
            organizations=[1],
            notice=True,
            monitor_object=monitor_object,
        )
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.probe_notification_channel",
        lambda channel_id, capability_only=False: {"delivery_mode": "alert_event_copy"},
    )

    enqueue_alert_center_deliveries([alert], "created", notifier=notifier)

    payload = MonitorAlertCenterDelivery.objects.get(alert=alert).payload
    assert {
        "monitor_id": payload["monitor_id"],
        "cmdb_id": payload["cmdb_id"],
        "resource_id": payload["resource_id"],
        "resource_type": payload["resource_type"],
        "resource_name": payload["resource_name"],
    } == {
        "monitor_id": "deleted-1",
        "cmdb_id": None,
        "resource_id": "deleted-1",
        "resource_type": "DeletedHost",
        "resource_name": "deleted-host",
    }


def test_legacy_and_outbox_payloads_share_monitor_identity(monkeypatch):
    channel = Channel.objects.create(
        name="告警中心-双链路",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )
    monitor_object = MonitorObject.objects.create(name="Router")
    instance = MonitorInstance.objects.create(
        id="router-1",
        name="core-router",
        monitor_object=monitor_object,
        cmdb_id="cmdb-router-1",
    )
    alert = MonitorAlert.objects.create(
        policy_id=12,
        monitor_instance_id=instance.id,
        monitor_instance_name=instance.name,
        metric_instance_id="packet_loss",
        content="Packet loss high",
        level="warning",
        status="new",
        start_event_time=datetime(2026, 9, 3, 7, tzinfo=timezone.utc),
        notice_type_ids=[channel.id],
    )
    notifier = AlertLifecycleNotifier(
        policy=SimpleNamespace(
            id=12,
            name="丢包策略",
            organizations=[1],
            notice=True,
            monitor_object=monitor_object,
        )
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.ALERT_CENTER_OUTBOX_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "apps.monitor.services.alert_center_delivery.SystemMgmtUtils.probe_notification_channel",
        lambda channel_id, capability_only=False: {"delivery_mode": "alert_event_copy"},
    )
    sent = {}
    monkeypatch.setattr(alert_lifecycle_notify, "ALERT_CENTER_ACK_TOKEN", "test-token")
    monkeypatch.setattr(
        alert_lifecycle_notify.SystemMgmtUtils,
        "send_msg_with_channel",
        lambda channel_id, title, content, receivers, **kwargs: sent.update(content=content) or {"result": True, "data": {}},
    )

    enqueue_alert_center_deliveries([alert], "created", notifier=notifier)
    notifier._push_to_alert_center(
        channel.id,
        channel.name,
        [alert],
        "created",
        "",
        "",
    )

    outbox_payload = MonitorAlertCenterDelivery.objects.get(alert=alert).payload
    legacy_payload = sent["content"]["events"][0]
    identity_fields = [
        "monitor_id",
        "cmdb_id",
        "resource_id",
        "resource_type",
        "resource_name",
    ]
    assert {key: legacy_payload[key] for key in identity_fields} == {key: outbox_payload[key] for key in identity_fields}
