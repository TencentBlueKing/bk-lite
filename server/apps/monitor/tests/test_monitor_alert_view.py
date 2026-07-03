"""MonitorAlertViewSet / MonitorEventViewSet 视图规格测试。

权限规则 RPC mock 为放行；S3 边界 stub；AlertLifecycleNotifier mock。
"""

import pytest

from apps.monitor.models import (
    MonitorAlert,
    MonitorAlertMetricSnapshot,
    MonitorEvent,
    MonitorEventRawData,
)
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


@pytest.fixture
def grant_all(mocker):
    # 两个 ViewSet 各自 import 了 get_permissions_rules / check_instance_permission
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={"data": {"all": True}, "team": [1]},
    )
    mocker.patch(
        "apps.monitor.views.monitor_alert.check_instance_permission",
        return_value=True,
    )


@pytest.fixture
def stub_s3(mocker):
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._upload_to_s3",
        return_value="2026/01/01/fake.json.gz",
    )
    mocker.patch(
        "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
        return_value=[],
    )


def _policy():
    obj = MonitorObject.objects.create(name="AlertViewObj", level="base")
    return MonitorPolicy.objects.create(
        monitor_object=obj, name="p", algorithm="max",
        query_condition={}, source={}, group_by=[],
    )


class TestGetSnapshots:
    def test_alert_not_found(self, api_client, grant_all):
        api_client.cookies["current_team"] = "1"
        resp = api_client.get(f"{BASE}/api/monitor_alert/snapshots/999999/")
        assert resp.status_code == 404

    def test_no_snapshot_returns_empty(self, api_client, grant_all):
        api_client.cookies["current_team"] = "1"
        policy = _policy()
        alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id="h1", status="new")
        resp = api_client.get(f"{BASE}/api/monitor_alert/snapshots/{alert.id}/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["snapshots"] == []
        assert body["alert_info"]["id"] == alert.id

    def test_returns_snapshot_data(self, api_client, grant_all, mocker):
        api_client.cookies["current_team"] = "1"
        policy = _policy()
        alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id="h1", status="new")
        mocker.patch(
            "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
            return_value=[{"type": "info", "raw_data": {"v": 1}}],
        )
        MonitorAlertMetricSnapshot.objects.create(
            alert=alert, policy_id=policy.id, monitor_instance_id="h1",
        )
        resp = api_client.get(f"{BASE}/api/monitor_alert/snapshots/{alert.id}/")
        assert resp.status_code == 200
        snaps = resp.json()["data"]["snapshots"]
        assert snaps and snaps[0]["type"] == "info"


class TestAlertUpdateClose:
    def test_close_new_alert(self, api_client, grant_all, mocker):
        api_client.cookies["current_team"] = "1"
        notifier = mocker.patch("apps.monitor.views.monitor_alert.AlertLifecycleNotifier")
        policy = _policy()
        alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id="h1", status="new")
        resp = api_client.patch(
            f"{BASE}/api/monitor_alert/{alert.id}/",
            {"status": "closed"}, format="json",
        )
        assert resp.status_code == 200
        alert.refresh_from_db()
        assert alert.status == "closed"
        assert alert.operator == "testuser"
        assert alert.operation_logs[-1]["action"] == "closed"
        notifier.return_value.notify_alerts.assert_called_once()


class TestGetEvents:
    def test_alert_not_found(self, api_client, grant_all):
        api_client.cookies["current_team"] = "1"
        resp = api_client.get(f"{BASE}/api/monitor_event/query/999999/")
        assert resp.status_code == 404

    def test_returns_events(self, api_client, grant_all):
        api_client.cookies["current_team"] = "1"
        policy = _policy()
        alert = MonitorAlert.objects.create(policy_id=policy.id, monitor_instance_id="h1", status="new")
        MonitorEvent.objects.create(
            id="ev1", alert_id=alert.id, policy_id=policy.id,
            monitor_instance_id="h1", level="critical", value=9.0, content="c",
        )
        resp = api_client.get(f"{BASE}/api/monitor_event/query/{alert.id}/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["count"] == 1
        assert body["results"][0]["level"] == "critical"


class TestGetRawData:
    def test_event_not_found(self, api_client, grant_all):
        api_client.cookies["current_team"] = "1"
        resp = api_client.get(f"{BASE}/api/monitor_event/raw_data/999999/")
        assert resp.status_code == 404

    def test_no_raw_data_returns_empty(self, api_client, grant_all):
        api_client.cookies["current_team"] = "1"
        policy = _policy()
        MonitorEvent.objects.create(
            id="ev2", policy_id=policy.id, monitor_instance_id="h1", level="info", content="",
        )
        resp = api_client.get(f"{BASE}/api/monitor_event/raw_data/ev2/")
        assert resp.status_code == 200
        assert resp.json()["data"] == {}

    def test_returns_raw_data(self, api_client, grant_all, stub_s3, mocker):
        api_client.cookies["current_team"] = "1"
        policy = _policy()
        event = MonitorEvent.objects.create(
            id="ev3", policy_id=policy.id, monitor_instance_id="h1", level="info", content="",
        )
        MonitorEventRawData.objects.create(event=event, data={"v": 42})
        mocker.patch(
            "apps.core.fields.s3_json_field.S3JSONField._load_from_s3",
            return_value={"v": 42},
        )
        resp = api_client.get(f"{BASE}/api/monitor_event/raw_data/ev3/")
        assert resp.status_code == 200
        assert resp.json()["data"] == {"v": 42}
