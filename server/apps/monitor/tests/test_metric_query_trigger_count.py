from datetime import datetime, timezone
from types import SimpleNamespace

from apps.monitor.tasks.services.policy_scan.metric_query import MetricQueryService


def test_query_comparison_metrics_uses_trigger_count_for_range_but_keeps_period_step(mocker):
    captured = {}

    def fake_query_range(query, start, end, step):
        captured.update(
            {
                "query": query,
                "start": start,
                "end": end,
                "step": step,
            }
        )
        return {"data": {"result": []}}

    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = fake_query_range

    policy = SimpleNamespace(
        last_run_time=datetime(2026, 6, 24, 10, 10, tzinfo=timezone.utc),
        query_condition={"type": "pmq", "query": "up{}"},
        group_by=["instance_id"],
        algorithm="avg",
        group_algorithm=None,
        metric_unit="",
        calculation_unit="",
        compare_mode="absolute",
        compare_value_kind="",
        collect_type="",
        monitor_object=None,
    )

    service = MetricQueryService(policy, {})
    service.query_comparison_metrics({"type": "min", "value": 5}, points=2)

    assert captured["end"] == int(policy.last_run_time.timestamp())
    assert captured["start"] == captured["end"] - 10 * 60
    assert captured["step"] == "5m"
    assert captured["query"] == "avg_over_time((avg(up{}) by (instance_id))[5m:10s])"


def test_query_comparison_metrics_uses_group_algorithm(mocker):
    captured = {}
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI"
    ).return_value.query_range.side_effect = (
        lambda query, start, end, step: captured.update({"query": query}) or {"data": {"result": []}}
    )

    policy = SimpleNamespace(
        last_run_time=datetime(2026, 6, 24, 10, 10, tzinfo=timezone.utc),
        query_condition={"type": "pmq", "query": "up{}"},
        group_by=["instance_id"],
        group_algorithm="max",
        algorithm="avg_over_time",
        metric_unit="",
        calculation_unit="",
        compare_mode="absolute",
        compare_value_kind="",
        collect_type="",
        monitor_object=None,
    )

    service = MetricQueryService(policy, {})
    service.query_comparison_metrics({"type": "min", "value": 5}, points=1)

    assert captured["query"] == "avg_over_time((max(up{}) by (instance_id))[5m:10s])"
