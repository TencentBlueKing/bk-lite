"""SnapshotRecorder 规格测试。

聚焦活跃告警快照记录、原始数据映射、兜底查询、告警前快照构建。
MinIO 边界 stub；metric_query_service mock。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorAlert, MonitorAlertMetricSnapshot
from apps.monitor.tasks.services.policy_scan.snapshot_recorder import SnapshotRecorder

pytestmark = pytest.mark.django_db


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


def _policy(**kwargs):
    base = dict(
        id=1,
        group_by=["instance_id"],
        algorithm="max",
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mq(**kwargs):
    return SimpleNamespace(
        query_raw_metrics=lambda period: kwargs.get("raw", {"data": {"result": []}}),
        format_pmq=lambda: kwargs.get("pmq", "up"),
        format_period=lambda period: kwargs.get("step", "5m"),
    )


class TestGetAlertMetricInstanceId:
    def test_uses_metric_instance_id(self):
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        a = SimpleNamespace(metric_instance_id="('h1',)", monitor_instance_id="h1")
        assert rec._get_alert_metric_instance_id(a) == "('h1',)"

    def test_fallback_to_monitor_instance(self):
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        a = SimpleNamespace(metric_instance_id="", monitor_instance_id="h2")
        assert rec._get_alert_metric_instance_id(a) == "('h2',)"


class TestBuildInstanceRawDataMap:
    def test_maps_info_events_raw_data(self):
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        info_events = [
            {"metric_instance_id": "('h1',)", "raw_data": {"v": 1}},
            {"monitor_instance_id": "h2", "raw_data": {"v": 2}},
            {"metric_instance_id": "('h3',)"},  # 无 raw_data → 跳过
        ]
        result = rec._build_instance_raw_data_map(None, info_events)
        assert result["('h1',)"] == {"v": 1}
        assert result["('h2',)"] == {"v": 2}
        assert "('h3',)" not in result


class TestQueryFallbackRawData:
    def test_builds_and_caches_fallback_map(self):
        raw = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[0, "5"]]},
        ]}}
        rec = SnapshotRecorder(_policy(), {}, [], _mq(raw=raw))
        out = rec._query_fallback_raw_data("('h1',)")
        assert out["metric"]["instance_id"] == "h1"
        # 缓存命中
        assert rec._fallback_raw_data_map is not None
        assert rec._query_fallback_raw_data("('missing',)") == {}


class TestRecordSnapshotsForActiveAlerts:
    def test_no_alerts_does_nothing(self):
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        # 不抛错即可
        assert rec.record_snapshots_for_active_alerts() is None

    def test_creates_info_snapshot_for_active_alert(self, stub_s3):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="alert", status="new",
        )
        rec = SnapshotRecorder(_policy(), {}, [alert], _mq())
        info_events = [{"metric_instance_id": "('h1',)", "raw_data": {"v": 1}}]
        rec.record_snapshots_for_active_alerts(info_events=info_events)
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        assert snap.policy_id == 1
        assert any(s["type"] == "info" for s in snap.snapshots)

    def test_no_data_alert_records_no_data_snapshot(self, stub_s3):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="no_data", status="new",
        )
        rec = SnapshotRecorder(_policy(), {}, [alert], _mq())
        rec.record_snapshots_for_active_alerts()
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        assert any(s["type"] == "no_data" for s in snap.snapshots)


class TestBuildPreAlertSnapshot:
    def test_invalid_algorithm_returns_none(self):
        rec = SnapshotRecorder(_policy(algorithm="bogus"), {}, [], _mq())
        now = datetime.now(timezone.utc)
        assert rec._build_pre_alert_snapshot("('h1',)", now) is None

    def test_too_early_returns_none(self):
        # last_run_time 远在 7 天前 → pre_alert_time 早于 min_time → None
        old_policy = _policy(last_run_time=datetime(2020, 1, 1, tzinfo=timezone.utc))
        rec = SnapshotRecorder(old_policy, {}, [], _mq())
        assert rec._build_pre_alert_snapshot("('h1',)", old_policy.last_run_time) is None

    def test_builds_snapshot_when_data_matches(self, mocker):
        now = datetime.now(timezone.utc)
        pre_metrics = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[0, "9"]]},
        ]}}
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        mocker.patch.dict(
            "apps.monitor.tasks.services.policy_scan.snapshot_recorder.METHOD",
            {"max": mocker.Mock(return_value=pre_metrics)},
            clear=False,
        )
        snap = rec._build_pre_alert_snapshot("('h1',)", now)
        assert snap["type"] == "pre_alert"
        assert snap["raw_data"]["metric"]["instance_id"] == "h1"

    def test_returns_none_when_no_matching_data(self, mocker):
        now = datetime.now(timezone.utc)
        pre_metrics = {"data": {"result": [
            {"metric": {"instance_id": "other"}, "values": [[0, "9"]]},
        ]}}
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        mocker.patch.dict(
            "apps.monitor.tasks.services.policy_scan.snapshot_recorder.METHOD",
            {"max": mocker.Mock(return_value=pre_metrics)},
            clear=False,
        )
        assert rec._build_pre_alert_snapshot("('h1',)", now) is None
