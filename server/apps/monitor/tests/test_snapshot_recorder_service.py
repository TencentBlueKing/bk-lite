"""SnapshotRecorder 规格测试。

聚焦活跃告警快照记录、原始数据映射、兜底查询、告警前快照构建。
MinIO 边界 stub；metric_query_service mock。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorAlert, MonitorAlertMetricSnapshot, MonitorEvent
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
    calls = kwargs.setdefault("calls", [])

    def query_policy_window_metrics(period, instance_ids=None, end_timestamp=None):
        calls.append({"period": period, "instance_ids": instance_ids, "end_timestamp": end_timestamp})
        if "raise" in kwargs:
            raise kwargs["raise"]
        return kwargs.get("raw", {"data": {"result": []}})

    return SimpleNamespace(
        query_policy_window_metrics=query_policy_window_metrics,
        calls=calls,
        format_pmq=lambda base_filters=None: kwargs.get("pmq", "up"),
        format_period=lambda period: kwargs.get("step", "5m"),
        get_result_group_by=lambda: kwargs.get("group_by", ["instance_id"]),
        query_overlay_last_values=lambda: kwargs.get("overlay", ({}, {})),
        get_effective_calculation_unit=lambda: kwargs.get("result_unit", ""),
    )


def _alert(metric_instance_id, monitor_instance_id, alert_type="alert"):
    return SimpleNamespace(
        id=hash((metric_instance_id, alert_type)) & 0xFFFF,
        metric_instance_id=metric_instance_id,
        monitor_instance_id=monitor_instance_id,
        alert_type=alert_type,
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
    """兜底补查只针对本轮 miss 的告警实例（issue #5777）。"""

    def test_queries_only_missing_alert_instances_in_one_call(self):
        raw = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[0, "5"]]},
            {"metric": {"instance_id": "h3"}, "values": [[0, "7"]]},
            {"metric": {"instance_id": "other"}, "values": [[0, "9"]]},
        ]}}
        mq = _mq(raw=raw)
        rec = SnapshotRecorder(_policy(), {}, [], mq)
        alerts = [
            _alert("('h1',)", "('h1',)"),
            _alert("('h2',)", "('h2',)"),            # 本轮已有 raw_data，不进兜底
            _alert("('h3',)", "('h3',)"),
            _alert("('h4',)", "('h4',)", "no_data"),  # 无数据告警不兜底
        ]
        out = rec._query_fallback_raw_data_map(alerts, {"('h2',)": {"values": [[0, "1"]]}})

        assert len(mq.calls) == 1
        assert mq.calls[0]["instance_ids"] == ["('h1',)", "('h3',)"]
        assert mq.calls[0]["end_timestamp"] is None
        assert set(out) == {"('h1',)", "('h3',)"}
        assert out["('h1',)"]["metric"]["instance_id"] == "h1"
        assert "('other',)" not in out

    def test_no_missing_alerts_issues_no_query(self):
        mq = _mq()
        rec = SnapshotRecorder(_policy(), {}, [], mq)
        out = rec._query_fallback_raw_data_map(
            [_alert("('h1',)", "('h1',)")], {"('h1',)": {"values": [[0, "1"]]}}
        )
        assert out == {}
        assert mq.calls == []

    def test_group_by_changed_skips_fallback_instead_of_full_scan(self, caplog):
        """磁盘策略 group_by 四维收窄成一维后，历史告警身份对不上，不能整库拉取空转。"""
        import logging

        mq = _mq(group_by=["instance_id"])
        rec = SnapshotRecorder(_policy(group_by=["instance_id"]), {}, [], mq)
        legacy_alerts = [
            _alert("('h1', '/dev/sda1', '/', 'ext4')", "('h1',)"),
            _alert("('h1', '/dev/sdb1', '/data', 'xfs')", "('h1',)"),
        ]
        with caplog.at_level(logging.DEBUG, logger="celery"):
            out = rec._query_fallback_raw_data_map(legacy_alerts, {})

        assert out == {}
        assert mq.calls == []
        skipped = [r for r in caplog.records if "event=snapshot_fallback_skipped" in r.getMessage()]
        assert len(skipped) == 1
        assert skipped[0].levelno == logging.DEBUG
        assert skipped[0].args == (1, 2)
        assert skipped[0].getMessage() == (
            "event=snapshot_fallback_skipped policy_id=1 reason=group_by_mismatch count=2"
        )
        # 历史身份原文不进日志
        assert "/dev/sda1" not in skipped[0].getMessage()

    def test_mixed_alerts_only_query_aligned_ones(self):
        raw = {"data": {"result": [
            {"metric": {"instance_id": "h2"}, "values": [[0, "5"]]},
        ]}}
        mq = _mq(raw=raw)
        rec = SnapshotRecorder(_policy(), {}, [], mq)
        alerts = [
            _alert("('h1', '/dev/sda1', '/', 'ext4')", "('h1',)"),
            _alert("('h2',)", "('h2',)"),
        ]
        out = rec._query_fallback_raw_data_map(alerts, {})
        assert mq.calls[0]["instance_ids"] == ["('h2',)"]
        assert set(out) == {"('h2',)"}

    def test_record_snapshots_uses_fallback_for_missing_active_alert(self, stub_s3):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="('h1',)", metric_instance_id="('h1',)",
            alert_type="alert", status="new",
        )
        raw = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[200, "42"]]},
        ]}}
        mq = _mq(raw=raw)
        rec = SnapshotRecorder(_policy(), {}, [alert], mq)
        rec.record_snapshots_for_active_alerts(info_events=[])
        assert mq.calls[0]["instance_ids"] == ["('h1',)"]
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        info_snap = next(s for s in snap.snapshots if s["type"] == "info")
        assert info_snap["compared_value"] == 42.0


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
        rec = SnapshotRecorder(
            _policy(),
            {},
            [alert],
            _mq(),
        )
        info_events = [{
            "metric_instance_id": "('h1',)",
            "raw_data": {"values": [[1, "75"]]},
        }]
        rec.record_snapshots_for_active_alerts(info_events=info_events)
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        assert snap.policy_id == 1
        info_snap = next(s for s in snap.snapshots if s["type"] == "info")
        assert info_snap["compared_value"] == 75.0
        assert info_snap["current_value"] == 75.0
        assert info_snap["baseline_value"] is None
        assert "result_unit" in info_snap

    def test_no_data_alert_records_no_data_snapshot(self, stub_s3):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="no_data", status="new",
        )
        rec = SnapshotRecorder(_policy(), {}, [alert], _mq())
        rec.record_snapshots_for_active_alerts()
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        assert any(s["type"] == "no_data" for s in snap.snapshots)

    def test_no_data_alert_does_not_copy_threshold_window_leftover(self, stub_s3, mocker):
        """无数据窗口更短时，阈值查询仍可能带回旧点；不能写到无数据告警上。"""
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="no_data", status="new",
        )
        event = MonitorEvent.objects.create(
            id="nd-ev1",
            alert_id=alert.id,
            policy_id=1,
            monitor_instance_id="h1",
            metric_instance_id="('h1',)",
            level="no_data",
            content="no data",
            event_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        rec = SnapshotRecorder(_policy(), {}, [], _mq())
        mocker.patch.object(
            rec,
            "_build_pre_alert_snapshot",
            return_value={
                "type": "pre_alert",
                "snapshot_time": "2026-01-01T11:55:00+00:00",
                "raw_data": {"values": [[100, "1"]]},
            },
        )
        rec.record_snapshots_for_active_alerts(
            info_events=[{
                "metric_instance_id": "('h1',)",
                "raw_data": {"values": [[200, "1"], [260, "1"]]},
            }],
            event_objs=[event],
            new_alerts=[alert],
        )
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        types = [item["type"] for item in snap.snapshots]
        assert types == ["pre_alert", "event"]
        assert snap.snapshots[1]["event_id"] == event.id
        assert snap.snapshots[1]["raw_data"] == {}

    def test_threshold_alert_still_records_info_from_raw_data(self, stub_s3):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="alert", status="new",
        )
        rec = SnapshotRecorder(_policy(), {}, [alert], _mq())
        rec.record_snapshots_for_active_alerts(
            info_events=[{
                "metric_instance_id": "('h1',)",
                "raw_data": {"values": [[200, "1"]]},
            }],
        )
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        assert [item["type"] for item in snap.snapshots] == ["info"]

    def test_recovered_event_records_event_snapshot(self, stub_s3):
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="alert", status="recovered",
        )
        event = MonitorEvent.objects.create(
            id="rec-ev1",
            alert_id=alert.id,
            policy_id=1,
            monitor_instance_id="h1",
            metric_instance_id="('h1',)",
            level="critical",
            action=MonitorEvent.Action.RECOVERED,
            content="recovered",
            event_time=datetime(2026, 1, 1, 12, 10, 0, tzinfo=timezone.utc),
        )
        rec = SnapshotRecorder(_policy(), {}, [alert], _mq())
        rec.record_snapshots_for_active_alerts(
            info_events=[{
                "metric_instance_id": "('h1',)",
                "raw_data": {"values": [[210, "1"]]},
            }],
            event_objs=[event],
        )
        snap = MonitorAlertMetricSnapshot.objects.get(alert_id=alert.id)
        assert [item["type"] for item in snap.snapshots] == ["event"]
        assert snap.snapshots[0]["event_id"] == event.id


class TestBuildPreAlertSnapshot:
    def test_query_failure_returns_none(self):
        from apps.core.exceptions.base_app_exception import BaseAppException

        mq = _mq(**{"raise": BaseAppException("bad algorithm")})
        rec = SnapshotRecorder(_policy(algorithm="bogus"), {}, [], mq)
        now = datetime.now(timezone.utc)
        assert rec._build_pre_alert_snapshot("('h1',)", now) is None

    def test_too_early_returns_none(self):
        # last_run_time 远在 7 天前 → pre_alert_time 早于 min_time → None
        old_policy = _policy(last_run_time=datetime(2020, 1, 1, tzinfo=timezone.utc))
        mq = _mq()
        rec = SnapshotRecorder(old_policy, {}, [], mq)
        assert rec._build_pre_alert_snapshot("('h1',)", old_policy.last_run_time) is None
        assert mq.calls == []

    def test_builds_snapshot_scoped_to_alert_instance(self):
        now = datetime.now(timezone.utc)
        pre_metrics = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[0, "9"]]},
        ]}}
        mq = _mq(raw=pre_metrics)
        rec = SnapshotRecorder(_policy(), {}, [], mq)
        snap = rec._build_pre_alert_snapshot("('h1',)", now, monitor_instance_id="('h1',)")
        assert snap["type"] == "pre_alert"
        assert snap["raw_data"]["metric"]["instance_id"] == "h1"
        assert mq.calls[0]["instance_ids"] == ["('h1',)"]
        # 窗口右端是告警前一个周期
        assert mq.calls[0]["end_timestamp"] == int(now.timestamp()) - 300

    def test_returns_none_when_no_matching_data(self):
        now = datetime.now(timezone.utc)
        pre_metrics = {"data": {"result": [
            {"metric": {"instance_id": "other"}, "values": [[0, "9"]]},
        ]}}
        rec = SnapshotRecorder(_policy(), {}, [], _mq(raw=pre_metrics))
        assert rec._build_pre_alert_snapshot("('h1',)", now) is None
