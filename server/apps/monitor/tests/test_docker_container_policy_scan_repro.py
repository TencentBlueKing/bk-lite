"""Repro: Docker Container 策略预览超阈值但不触发告警。

用户场景：group_by 仅有 instance_id（前端 Docker Container groupIds 为空时的默认值），
指标预览能查到数据，但扫描侧无法把聚合结果归属到容器实例。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from apps.monitor.tasks.services.policy_scan.alert_detector import AlertDetector
from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService
from apps.monitor.utils.dimension import ScopedInstanceMatcher


def _docker_container_object():
    parent = SimpleNamespace(id=10, instance_id_keys=["instance_id"])
    return SimpleNamespace(
        name="Docker Container",
        level="derivative",
        instance_id_keys=["instance_id", "container_name"],
        parent=parent,
        parent_id=parent.id,
    )


def _policy(**kwargs):
    base = dict(
        id=99,
        period={"type": "min", "value": 1},
        group_by=["instance_id"],
        alert_name="$instance_name 超阈值 $value",
        threshold=[{"method": ">", "value": 10, "level": "critical"}],
        source={"type": "instance", "values": ["('host1', 'c1')"]},
        monitor_object=_docker_container_object(),
        query_condition={"type": "metric", "metric_id": 1},
        no_data_period={},
        recovery_condition=5,
        last_run_time=datetime(2026, 8, 12, 8, 0, 0, tzinfo=timezone.utc),
        trigger_count=1,
        metric_unit="percent",
        calculation_unit="percent",
        threshold_unit="percent",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _mq(agg):
    return SimpleNamespace(
        metric=SimpleNamespace(
            display_name="容器内存使用率",
            name="docker_container_mem_usage_percent",
            instance_id_keys=["instance_id", "container_name"],
            dimensions=[],
        ),
        query_aggregation_metrics=lambda period, points=1: agg,
        convert_metric_values=lambda data: data,
        format_aggregation_metrics=lambda data: {},
        get_display_unit=lambda: "%",
        get_enum_value_map=lambda: {},
        convert_thresholds=lambda thresholds: thresholds,
    )


def test_incomplete_groupby_two_containers_same_host_drops_alerts():
    """同宿主多容器 + group_by 只有 instance_id → 归属歧义 → 告警被 scope 过滤掉。"""
    instances = {
        "('host1', 'c1')": "c1",
        "('host1', 'c2')": "c2",
    }
    agg = {
        "data": {
            "result": [
                {"metric": {"instance_id": "host1"}, "values": [[1, "24.05"]]},
            ]
        }
    }
    detector = AlertDetector(
        _policy(source={"type": "instance", "values": list(instances)}),
        instances,
        {},
        [],
        _mq(agg),
    )

    alerts, infos = detector.detect_threshold_alerts()

    # 用户症状：预览 24%>10% 应告警，但实际 0 条
    assert alerts == [], f"expected no alerts due to ambiguity, got {alerts}"
    assert infos == []


def test_incomplete_groupby_single_container_still_matches():
    """单容器范围内仅按 instance_id 聚合时仍可唯一归属（对照）。"""
    instances = {"('host1', 'c1')": "c1"}
    agg = {
        "data": {
            "result": [
                {"metric": {"instance_id": "host1"}, "values": [[1, "24.05"]]},
            ]
        }
    }
    detector = AlertDetector(_policy(), instances, {}, [], _mq(agg))

    alerts, _ = detector.detect_threshold_alerts()

    assert len(alerts) == 1
    assert alerts[0]["monitor_instance_id"] == "('host1', 'c1')"
    assert alerts[0]["value"] == 24.05


def test_full_groupby_triggers_even_with_sibling_containers():
    """补齐 container_name 后，同宿主多容器也能正确触发。"""
    instances = {
        "('host1', 'c1')": "c1",
        "('host1', 'c2')": "c2",
    }
    agg = {
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "host1", "container_name": "c1"},
                    "values": [[1, "24.05"]],
                },
            ]
        }
    }
    detector = AlertDetector(
        _policy(
            group_by=["instance_id", "container_name"],
            source={"type": "instance", "values": list(instances)},
        ),
        instances,
        {},
        [],
        _mq(agg),
    )

    alerts, _ = detector.detect_threshold_alerts()

    assert len(alerts) == 1
    assert alerts[0]["monitor_instance_id"] == "('host1', 'c1')"


def test_format_aggregation_filters_ambiguous_host_series():
    """无数据路径同样会把仅含 instance_id 的歧义序列丢掉。"""
    instances = {
        "('host1', 'c1')": "c1",
        "('host1', 'c2')": "c2",
    }
    policy = _policy(group_by=["instance_id"])
    svc = MetricQueryService(policy, instances)
    svc._scoped_instance_matcher = ScopedInstanceMatcher(
        ["instance_id", "container_name"], instances
    )
    metrics = {
        "data": {
            "result": [
                {"metric": {"instance_id": "host1"}, "values": [[1, "24.05"]]},
            ]
        }
    }

    assert svc.format_aggregation_metrics(metrics) == {}
