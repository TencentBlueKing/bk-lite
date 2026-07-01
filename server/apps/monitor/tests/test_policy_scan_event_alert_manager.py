"""EventAlertManager 规格测试。

聚焦事件落库、告警创建/复用/升级、通知调度的 DB 副作用与契约。
MinIO 上传/回读边界 stub；AlertLifecycleNotifier mock。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorAlert, MonitorEvent, MonitorEventRawData
from apps.monitor.tasks.services.policy_scan.event_alert_manager import EventAlertManager

pytestmark = pytest.mark.django_db


@pytest.fixture
def stub_s3(mocker):
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="2026/01/01/fake.json.gz",
    )
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value={},
    )


def _policy(**kwargs):
    base = dict(
        id=1,
        notice=False,
        notice_type_ids=[],
        notice_users=[],
        no_data_level="warning",
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestCreateEvents:
    def test_empty_returns_empty(self):
        mgr = EventAlertManager(_policy(), {}, [])
        assert mgr.create_events([]) == []

    def test_creates_event_rows(self):
        mgr = EventAlertManager(_policy(), {}, [])
        events = [{
            "monitor_instance_id": "h1", "metric_instance_id": "('h1',)",
            "dimensions": {"instance_id": "h1"}, "value": 95.0,
            "level": "critical", "content": "超阈值", "alert_id": None,
        }]
        objs = mgr.create_events(events)
        assert len(objs) == 1
        assert MonitorEvent.objects.filter(policy_id=1, level="critical").count() == 1

    def test_creates_raw_data_record(self, stub_s3):
        alert = MonitorAlert.objects.create(policy_id=1, monitor_instance_id="h1", status="new")
        mgr = EventAlertManager(_policy(), {}, [])
        events = [{
            "monitor_instance_id": "h1", "metric_instance_id": "('h1',)",
            "dimensions": {}, "value": 95.0, "level": "critical",
            "content": "x", "alert_id": alert.id, "raw_data": {"k": "v"},
        }]
        objs = mgr.create_events(events)
        assert MonitorEventRawData.objects.filter(event_id=objs[0].id).count() == 1


class TestAlertTypeHelpers:
    def test_get_event_alert_type(self):
        mgr = EventAlertManager(_policy(), {}, [])
        assert mgr._get_event_alert_type({"level": "no_data"}) == "no_data"
        assert mgr._get_event_alert_type({"level": "critical"}) == "alert"

    def test_get_alert_metric_instance_id_fallback(self):
        mgr = EventAlertManager(_policy(), {}, [])
        a1 = SimpleNamespace(metric_instance_id="('h1',)", monitor_instance_id="h1")
        a2 = SimpleNamespace(metric_instance_id="", monitor_instance_id="h2")
        assert mgr._get_alert_metric_instance_id(a1) == "('h1',)"
        assert mgr._get_alert_metric_instance_id(a2) == "('h2',)"

    def test_build_alert_key(self):
        mgr = EventAlertManager(_policy(), {}, [])
        assert mgr._build_alert_key("('h1',)", "alert") == ("('h1',)", "alert")


class TestCreateEventsAndAlerts:
    def test_empty_returns_empty(self):
        mgr = EventAlertManager(_policy(), {}, [])
        assert mgr.create_events_and_alerts([]) == ([], [])

    def test_creates_new_alert_and_event(self, stub_s3, mocker):
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.event_alert_manager.AlertLifecycleNotifier"
        )
        mgr = EventAlertManager(_policy(), {"h1": "主机1"}, [])
        events = [{
            "monitor_instance_id": "h1", "metric_instance_id": "('h1',)",
            "dimensions": {}, "value": 95.0, "level": "critical",
            "content": "超阈值", "raw_data": {"k": "v"},
        }]
        event_objs, new_alerts = mgr.create_events_and_alerts(events)
        assert len(new_alerts) == 1
        assert new_alerts[0].monitor_instance_name == "主机1"
        assert new_alerts[0].level == "critical"
        assert len(event_objs) == 1
        # 事件 alert_id 关联到新建告警
        assert event_objs[0].alert_id == new_alerts[0].id

    def test_reuses_existing_active_alert(self, stub_s3, mocker):
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.event_alert_manager.AlertLifecycleNotifier"
        )
        existing = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="alert", level="warning", status="new",
        )
        mgr = EventAlertManager(_policy(), {"h1": "主机1"}, [existing])
        events = [{
            "monitor_instance_id": "h1", "metric_instance_id": "('h1',)",
            "dimensions": {}, "value": 99.0, "level": "critical",
            "content": "升级", "raw_data": {},
        }]
        event_objs, new_alerts = mgr.create_events_and_alerts(events)
        # 复用既有告警 → 不新建
        assert new_alerts == []
        assert MonitorAlert.objects.filter(policy_id=1).count() == 1
        existing.refresh_from_db()
        # critical(4) > warning(2) → 升级
        assert existing.level == "critical"
        assert existing.value == 99.0

    def test_no_data_alert_uses_policy_level(self, stub_s3, mocker):
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.event_alert_manager.AlertLifecycleNotifier"
        )
        mgr = EventAlertManager(_policy(no_data_level="error"), {"h1": "主机1"}, [])
        events = [{
            "monitor_instance_id": "h1", "metric_instance_id": "('h1',)",
            "dimensions": {}, "value": None, "level": "no_data",
            "content": "无数据",
        }]
        _, new_alerts = mgr.create_events_and_alerts(events)
        assert new_alerts[0].alert_type == "no_data"
        assert new_alerts[0].level == "error"
        assert new_alerts[0].value is None


class TestUpdateExistingAlerts:
    def test_no_upgrade_when_level_not_higher(self):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", level="critical", status="new",
        )
        mgr = EventAlertManager(_policy(), {}, [])
        event = {"_alert_obj": alert, "level": "warning", "value": 1.0, "content": "c"}
        updated = mgr._update_existing_alerts_from_events([event])
        assert updated == []

    def test_skips_no_data_events(self):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", level="warning", status="new",
        )
        mgr = EventAlertManager(_policy(), {}, [])
        event = {"_alert_obj": alert, "level": "no_data", "value": None, "content": "c"}
        assert mgr._update_existing_alerts_from_events([event]) == []
