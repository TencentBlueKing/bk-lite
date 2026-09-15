"""AlertDetector 规格测试。

聚焦阈值/无数据告警检测、事件计数、告警恢复的 DB 副作用与契约。
metric_query_service / AlertLifecycleNotifier 为可 mock 外部边界。
MonitorAlert 走真实 DB 断言副作用。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.models import MonitorAlert, MonitorEvent
from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector


def _policy(**kwargs):
    base = dict(
        id=1,
        period={"type": "min", "value": 5},
        group_by=["instance_id"],
        alert_name="$instance_name 超阈值 $value",
        threshold=[{"method": ">", "value": 80, "level": "critical"}],
        source={"type": "instance", "values": ["h1"]},
        monitor_object=SimpleNamespace(name="Host"),
        query_condition={"type": "metric", "metric_id": 1},
        no_data_period={"type": "min", "value": 10},
        no_data_recovery_period={"type": "min", "value": 10},
        no_data_alert_name="$instance_name 无数据",
        no_data_level="warning",
        recovery_condition=2,
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mq(metric=None, **kwargs):
    default_agg = {"data": {"result": []}}
    comparison = kwargs.get("comparison", kwargs.get("agg", default_agg))
    existence = kwargs.get("existence", comparison)
    formatted_override = kwargs["formatted"] if "formatted" in kwargs else None

    def format_aggregation_metrics(data):
        if formatted_override is not None:
            return formatted_override
        result = {}
        for item in (data or {}).get("data", {}).get("result", []):
            instance_id = str(((item.get("metric") or {}).get("instance_id"),))
            values = item.get("values") or []
            if not values:
                continue
            result[instance_id] = {
                "value": float(values[-1][1]),
                "raw_data": item,
            }
        return result

    m = SimpleNamespace(
        metric=metric,
        query_comparison_metrics=lambda period, points=1: comparison,
        query_existence_metrics=lambda period, points=1: existence,
        convert_metric_values=lambda data: data,
        format_aggregation_metrics=format_aggregation_metrics,
        get_display_unit=lambda: kwargs.get("display_unit", ""),
        get_enum_value_map=lambda: kwargs.get("enum_map", {}),
        convert_thresholds=lambda thresholds: thresholds,
        query_overlay_last_values=lambda: ({}, {}),
        get_source_display_unit=lambda: kwargs.get("display_unit", ""),
    )
    return m


class TestDetectThresholdAlerts:
    def test_triggers_alert_when_above_threshold(self, mocker):
        agg = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "95"]]},
        ]}}
        detector = AlertDetector(
            _policy(), {"('h1',)": "主机1"}, {}, [],
            _mq(agg=agg),
        )
        alerts, infos, holds = detector.detect_threshold_alerts()
        assert len(alerts) == 1
        assert alerts[0]["level"] == "critical"
        assert alerts[0]["value"] == 95.0
        assert "主机1" in alerts[0]["content"]
        assert infos == []

    def test_below_threshold_yields_info(self, mocker):
        agg = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "10"]]},
        ]}}
        detector = AlertDetector(
            _policy(), {"('h1',)": "主机1"}, {}, [],
            _mq(agg=agg),
        )
        alerts, infos, holds = detector.detect_threshold_alerts()
        assert alerts == []
        assert holds == []
        assert len(infos) == 1
        assert infos[0]["level"] == "info"

    def test_hysteresis_band_yields_hold(self):
        agg = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "75"]]},
        ]}}
        detector = AlertDetector(
            _policy(recovery_threshold={"method": "<", "value": 70}),
            {"('h1',)": "主机1"}, {}, [],
            _mq(agg=agg),
        )
        alerts, infos, holds = detector.detect_threshold_alerts()
        assert alerts == []
        assert infos == []
        assert len(holds) == 1
        assert holds[0]["level"] == "hold"

    def test_filters_events_outside_scope(self, mocker):
        agg = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "95"]]},
            {"metric": {"instance_id": "h2"}, "values": [[100, "99"]]},
        ]}}
        # instances_map 只含 h1，h2 应被 source 过滤掉
        detector = AlertDetector(
            _policy(), {"('h1',)": "主机1"}, {}, [],
            _mq(agg=agg),
        )
        alerts, infos, holds = detector.detect_threshold_alerts()
        ids = {a["metric_instance_id"] for a in alerts}
        assert ids == {"('h1',)"}

    def test_derivative_instance_template_exposes_child_and_parent_names(self):
        agg = {"data": {"result": [
            {"metric": {"pod": "orders-7f9"}, "values": [[100, "95"]]},
        ]}}
        parent = SimpleNamespace(id=10, instance_id_keys=["instance_id"])
        monitor_object = SimpleNamespace(
            name="K3SPod",
            level="derivative",
            instance_id_keys=["instance_id", "pod"],
            parent=parent,
            parent_id=parent.id,
        )
        detector = AlertDetector(
            _policy(
                monitor_object=monitor_object,
                group_by=["pod"],
                alert_name="$parent_resource_name/$resource_name 超阈值",
            ),
            {"('cluster-a', 'orders-7f9')": "orders-7f9"},
            {},
            [],
            _mq(agg=agg),
            parent_instances_map={"('cluster-a',)": "生产集群"},
        )

        alerts, _, _ = detector.detect_threshold_alerts()

        assert alerts[0]["monitor_instance_id"] == "('cluster-a', 'orders-7f9')"
        assert alerts[0]["content"] == "生产集群/orders-7f9 超阈值"
        assert detector._build_metric_resource_context("('orders-7f9',)") == {
            "monitor_instance_id": "('cluster-a', 'orders-7f9')",
            "resource_id": "('cluster-a', 'orders-7f9')",
            "resource_name": "orders-7f9",
            "resource_ip": "",
            "parent_resource_id": "('cluster-a',)",
            "parent_resource_name": "生产集群",
        }

    def test_derivative_instance_does_not_guess_ambiguous_child_name(self):
        parent = SimpleNamespace(id=10, instance_id_keys=["instance_id"])
        monitor_object = SimpleNamespace(
            name="K3SPod",
            level="derivative",
            instance_id_keys=["instance_id", "pod"],
            parent=parent,
            parent_id=parent.id,
        )
        detector = AlertDetector(
            _policy(monitor_object=monitor_object, group_by=["pod"]),
            {
                "('cluster-a', 'api')": "api",
                "('cluster-b', 'api')": "api",
            },
            {},
            [],
            _mq(),
        )

        assert detector._match_scoped_monitor_instance("('api',)") == ""


class TestGetMetricDisplayName:
    def test_uses_metric_display_name(self):
        metric = SimpleNamespace(display_name="CPU使用率", name="cpu")
        detector = AlertDetector(_policy(), {}, {}, [], _mq(metric=metric))
        assert detector._get_metric_display_name() == "CPU使用率"

    def test_falls_back_to_metric_name(self):
        metric = SimpleNamespace(display_name="", name="cpu")
        detector = AlertDetector(_policy(), {}, {}, [], _mq(metric=metric))
        assert detector._get_metric_display_name() == "cpu"

    def test_no_metric_uses_query_condition(self):
        detector = AlertDetector(
            _policy(query_condition={"type": "metric", "metric_id": "mid-7"}),
            {}, {}, [], _mq(metric=None),
        )
        assert detector._get_metric_display_name() == "mid-7"


class TestDetectNoDataAlerts:
    def test_no_period_or_source_returns_empty(self):
        detector = AlertDetector(_policy(no_data_period={}), {}, {}, [], _mq())
        assert detector.detect_no_data_alerts() == []

    def test_emits_event_for_missing_instance(self):
        # baselines 有 h1，但聚合结果为空 → h1 无数据
        detector = AlertDetector(
            _policy(), {"('h1',)": "主机1"}, {"('h1',)": "('h1',)"}, [],
            _mq(formatted={}),
        )
        events = detector.detect_no_data_alerts()
        assert len(events) == 1
        assert events[0]["level"] == "no_data"
        assert events[0]["metric_instance_id"] == "('h1',)"
        assert "主机1" in events[0]["content"]

    def test_instance_with_data_not_reported(self):
        detector = AlertDetector(
            _policy(), {"('h1',)": "主机1"}, {"('h1',)": "('h1',)"}, [],
            _mq(formatted={"('h1',)": {"value": 1.0}}),
        )
        events = detector.detect_no_data_alerts()
        assert events == []

    def test_derivative_instance_no_data_template_uses_child_name(self):
        parent = SimpleNamespace(id=10, instance_id_keys=["instance_id"])
        monitor_object = SimpleNamespace(
            name="K3SPod",
            level="derivative",
            instance_id_keys=["instance_id", "pod"],
            parent=parent,
            parent_id=parent.id,
        )
        child_id = "('cluster-a', 'orders-7f9')"
        detector = AlertDetector(
            _policy(
                monitor_object=monitor_object,
                group_by=["instance_id", "pod", "container"],
                no_data_alert_name="$parent_resource_name/$resource_name 无数据",
            ),
            {child_id: "orders-7f9"},
            # 兼容历史错误基准：曾把子对象归属记录成父实例。
            {"('cluster-a', 'orders-7f9', 'api')": "('cluster-a',)"},
            [],
            _mq(formatted={}),
            parent_instances_map={"('cluster-a',)": "生产集群"},
        )

        events = detector.detect_no_data_alerts()

        assert events[0]["monitor_instance_id"] == child_id
        assert events[0]["content"] == "生产集群/orders-7f9 无数据"

    @pytest.mark.django_db
    def test_count_if_zero_match_row_is_info_not_no_data_and_increments_recovery(self):
        comparison = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "0"]]},
        ]}}
        existence = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "12"]]},
        ]}}
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="('h1',)",
            metric_instance_id="('h1',)",
            alert_type="alert", status="new", info_event_count=2,
        )
        detector = AlertDetector(
            _policy(
                algorithm="count_if_over_time",
                threshold=[{"method": ">", "value": 5, "level": "warning"}],
            ),
            {"('h1',)": "主机1"},
            {"('h1',)": "('h1',)"},
            [alert],
            _mq(comparison=comparison, existence=existence),
        )
        alerts, infos, holds = detector.detect_threshold_alerts()
        assert alerts == []
        assert holds == []
        assert len(infos) == 1
        assert infos[0]["value"] in (0, 0.0, "0")
        assert detector.detect_no_data_alerts() == []
        detector.count_events(alerts, infos)
        alert.refresh_from_db()
        assert alert.info_event_count == 3

    def test_missing_comparison_does_not_report_no_data(self):
        existence = {"data": {"result": [
            {"metric": {"instance_id": "h1"}, "values": [[100, "12"]]},
        ]}}
        comparison = {"data": {"result": []}}
        detector = AlertDetector(
            _policy(), {"('h1',)": "主机1"}, {"('h1',)": "('h1',)"}, [],
            _mq(comparison=comparison, existence=existence),
        )
        alerts, infos, holds = detector.detect_threshold_alerts()
        assert alerts == []
        assert infos == []
        assert holds == []
        assert detector.detect_no_data_alerts() == []


class TestBuildDimensionNameMap:
    def test_no_metric_returns_empty(self):
        detector = AlertDetector(_policy(), {}, {}, [], _mq(metric=None))
        assert detector._build_dimension_name_map() == {}

    def test_maps_name_to_display(self):
        metric = SimpleNamespace(dimensions=[
            {"name": "device", "display_name": "设备"},
            {"name": "mount", "description": "挂载点"},
            {"name": "plain"},
            "not-a-dict",
        ])
        detector = AlertDetector(_policy(), {}, {}, [], _mq(metric=metric))
        assert detector._build_dimension_name_map() == {
            "device": "设备", "mount": "挂载点", "plain": "plain",
        }


@pytest.mark.django_db
class TestCountEvents:
    def test_increments_info_and_clears_alert(self):
        a1 = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="alert", status="new", info_event_count=0,
        )
        a2 = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h2", metric_instance_id="('h2',)",
            alert_type="alert", status="new", info_event_count=3,
        )
        detector = AlertDetector(_policy(), {}, {}, [a1, a2], _mq())
        info_events = [{"metric_instance_id": "('h1',)"}]
        alert_events = [{"metric_instance_id": "('h2',)"}]
        detector.count_events(alert_events, info_events)
        a1.refresh_from_db()
        a2.refresh_from_db()
        assert a1.info_event_count == 1   # 命中 info → +1
        assert a2.info_event_count == 0   # 命中 alert → 清零

    def test_hold_does_not_change_info_count(self):
        a1 = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="alert", status="new", info_event_count=2,
        )
        detector = AlertDetector(_policy(), {}, {}, [a1], _mq())
        detector.count_events([], [])
        a1.refresh_from_db()
        assert a1.info_event_count == 2


@pytest.mark.django_db
class TestRecoverThresholdAlerts:
    def test_recovers_when_info_count_reaches_condition(
        self, mocker, django_capture_on_commit_callbacks
    ):
        notifier = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
        )
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", alert_type="alert",
            status="new", info_event_count=5,
        )
        detector = AlertDetector(_policy(recovery_condition=2), {}, {}, [alert], _mq())
        with django_capture_on_commit_callbacks(execute=True):
            recovered_events = detector.recover_threshold_alerts()
        alert.refresh_from_db()
        assert alert.status == "recovered"
        assert alert.operator == "system"
        assert alert.alert_center_notified is False
        assert alert.operation_logs[-1]["action"] == "recovered"
        assert len(recovered_events) == 1
        assert recovered_events[0].action == MonitorEvent.Action.RECOVERED
        notifier.return_value.notify_alerts.assert_called_once()

    def test_no_recovery_when_condition_not_met(self, mocker):
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
        )
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", alert_type="alert",
            status="new", info_event_count=1,
        )
        detector = AlertDetector(_policy(recovery_condition=5), {}, {}, [alert], _mq())
        detector.recover_threshold_alerts()
        alert.refresh_from_db()
        assert alert.status == "new"

    def test_recovery_condition_zero_skips(self, mocker):
        spy = mocker.patch.object(MonitorAlert.objects, "filter")
        detector = AlertDetector(_policy(recovery_condition=0), {}, {}, [], _mq())
        detector.recover_threshold_alerts()
        spy.assert_not_called()


@pytest.mark.django_db
class TestRecoverNoDataAlerts:
    def test_no_recovery_period_skips(self, mocker):
        detector = AlertDetector(_policy(no_data_recovery_period={}), {}, {}, [], _mq())
        # 不应抛错，直接返回
        assert detector.recover_no_data_alerts() == []

    def test_recovers_no_data_alert_when_data_returns(
        self, mocker, django_capture_on_commit_callbacks
    ):
        notifier = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
        )
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="no_data", status="new",
        )
        detector = AlertDetector(
            _policy(), {}, {}, [alert],
            _mq(formatted={"('h1',)": {"value": 1.0}}),
        )
        with django_capture_on_commit_callbacks(execute=True):
            recovered_events = detector.recover_no_data_alerts()
        alert.refresh_from_db()
        assert alert.status == "recovered"
        assert len(recovered_events) == 1
        assert recovered_events[0].action == MonitorEvent.Action.RECOVERED
        notifier.return_value.notify_alerts.assert_called_once()

    def test_no_recovery_when_still_no_data(self, mocker):
        mocker.patch(
            "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
        )
        alert = MonitorAlert.objects.create(
            policy_id=1, monitor_instance_id="h1", metric_instance_id="('h1',)",
            alert_type="no_data", status="new",
        )
        detector = AlertDetector(_policy(), {}, {}, [alert], _mq(formatted={}))
        detector.recover_no_data_alerts()
        alert.refresh_from_db()
        assert alert.status == "new"

    def test_aggregated_alert_waits_until_all_instance_baselines_have_data(
        self, mocker
    ):
        notifier = mocker.patch(
            "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
        )
        alert = MonitorAlert.objects.create(
            policy_id=1,
            monitor_instance_id="pod-1",
            metric_instance_id="('pod-1', 'api')",
            alert_type="no_data",
            status="new",
        )
        detector = AlertDetector(
            _policy(),
            {"pod-1": "orders-7f9"},
            {
                "('pod-1', 'api')": "pod-1",
                "('pod-1', 'worker')": "pod-1",
            },
            [alert],
            _mq(formatted={"('pod-1', 'api')": {"value": 1.0}}),
        )

        detector.recover_no_data_alerts()

        alert.refresh_from_db()
        assert alert.status == "new"
        notifier.return_value.notify_alerts.assert_not_called()
