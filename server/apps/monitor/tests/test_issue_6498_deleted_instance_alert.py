"""扫描落库前确认实例仍存在。

删除已经提交后，旧扫描不得再为该实例新建活动告警或 triggered 事件。
实例仍在、空实例 ID、以及不在本次 instances_map 中的事件保持原写入。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import apps.cmdb.models  # noqa: F401  INSTALL_APPS 需含 cmdb（monitor.nats.monitor 导入 cmdb.services）
import apps.node_mgmt.models  # noqa: F401  INSTALL_APPS 需含 node_mgmt（monitor.apps.ready → nats.monitor）
from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorInstance, MonitorObject
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.monitor.tasks.services.policy_scan.event_alert_manager import EventAlertManager

pytestmark = pytest.mark.django_db


def _policy(**kwargs):
    base = dict(
        id=1,
        notice=False,
        notice_type_ids=[],
        notice_users=[],
        handlers=[],
        no_data_level="warning",
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        organizations=[],
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _event(instance_id, *, metric="cpu", level="critical", value=95.0, content="超阈值"):
    return {
        "monitor_instance_id": instance_id,
        "metric_instance_id": f"('{instance_id}', '{metric}')",
        "dimensions": {},
        "value": value,
        "level": level,
        "content": content,
    }


def _create_instance(object_name, instance_id, instance_name):
    monitor_object = MonitorObject.objects.create(name=object_name, level="base")
    return MonitorInstance.objects.create(
        id=instance_id,
        name=instance_name,
        monitor_object=monitor_object,
    )


def _manager(instances_map, active_alerts=None, **policy_kwargs):
    return EventAlertManager(_policy(**policy_kwargs), instances_map, active_alerts or [])


@pytest.fixture
def stub_notifier(mocker):
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.event_alert_manager.AlertLifecycleNotifier"
    )


def test_deleted_instance_does_not_create_active_alert_or_triggered_event(stub_notifier):
    instance = _create_instance("Issue6498Deleted", "inst-6498-deleted", "已删除主机")
    instance_id = instance.id
    MonitorInstance.objects.filter(id=instance_id).delete()

    event_objs, new_alerts = _manager({instance_id: "已删除主机"}).create_events_and_alerts(
        [_event(instance_id)]
    )

    assert new_alerts == []
    assert event_objs == []
    assert MonitorAlert.objects.filter(monitor_instance_id=instance_id, status="new").count() == 0
    assert (
        MonitorEvent.objects.filter(
            monitor_instance_id=instance_id,
            action=MonitorEvent.Action.TRIGGERED,
        ).count()
        == 0
    )


def test_live_instance_still_creates_new_alert(stub_notifier):
    instance = _create_instance("Issue6498Live", "inst-6498-live", "仍在主机")

    event_objs, new_alerts = _manager({instance.id: instance.name}).create_events_and_alerts(
        [_event(instance.id)]
    )

    assert len(new_alerts) == 1
    assert new_alerts[0].status == "new"
    assert new_alerts[0].monitor_instance_id == instance.id
    assert len(event_objs) == 1
    assert event_objs[0].action == MonitorEvent.Action.TRIGGERED
    assert event_objs[0].alert_id == new_alerts[0].id


def test_empty_instance_id_with_empty_map_still_creates(stub_notifier):
    event_objs, new_alerts = _manager({}).create_events_and_alerts([_event("")])

    assert len(new_alerts) == 1
    assert new_alerts[0].status == "new"
    assert new_alerts[0].monitor_instance_id == ""
    assert len(event_objs) == 1
    assert event_objs[0].action == MonitorEvent.Action.TRIGGERED


def test_instance_id_outside_snapshot_still_creates_without_row(stub_notifier):
    event_objs, new_alerts = _manager({}).create_events_and_alerts([_event("inst-6498-unscoped")])

    assert len(new_alerts) == 1
    assert new_alerts[0].status == "new"
    assert new_alerts[0].monitor_instance_id == "inst-6498-unscoped"
    assert len(event_objs) == 1


def test_instance_id_absent_from_nonempty_map_still_creates(stub_notifier):
    live = _create_instance("Issue6498Scoped", "inst-6498-scoped", "快照内")

    event_objs, new_alerts = _manager({live.id: live.name}).create_events_and_alerts(
        [_event("inst-6498-outside-map")]
    )

    assert len(new_alerts) == 1
    assert new_alerts[0].status == "new"
    assert new_alerts[0].monitor_instance_id == "inst-6498-outside-map"
    assert len(event_objs) == 1


def test_deleted_instance_does_not_block_sibling_alert(stub_notifier):
    deleted = _create_instance("Issue6498MixedDeleted", "inst-6498-mixed-deleted", "已删")
    live = _create_instance("Issue6498MixedLive", "inst-6498-mixed-live", "仍在")
    deleted_id = deleted.id
    MonitorInstance.objects.filter(id=deleted_id).delete()

    event_objs, new_alerts = _manager(
        {deleted_id: "已删", live.id: live.name}
    ).create_events_and_alerts([_event(deleted_id), _event(live.id)])

    assert [alert.monitor_instance_id for alert in new_alerts] == [live.id]
    assert new_alerts[0].status == "new"
    assert [event.monitor_instance_id for event in event_objs] == [live.id]
    assert MonitorAlert.objects.filter(monitor_instance_id=deleted_id).count() == 0
    assert (
        MonitorEvent.objects.filter(
            monitor_instance_id=deleted_id,
            action=MonitorEvent.Action.TRIGGERED,
        ).count()
        == 0
    )


def test_committed_alert_is_closed_when_instance_is_removed(stub_notifier):
    instance = _create_instance("Issue6498Removal", "inst-6498-removal", "待删除主机")
    _, new_alerts = _manager({instance.id: instance.name}).create_events_and_alerts(
        [_event(instance.id)]
    )
    assert new_alerts[0].status == "new"

    MonitorInstanceRemovalService.remove([instance.id])

    new_alerts[0].refresh_from_db()
    assert new_alerts[0].status == "closed"
    assert not MonitorInstance.objects.filter(id=instance.id).exists()
