from types import SimpleNamespace

from apps.monitor.nats.monitor import _attach_active_alert_metric_names, resolve_alert_metric_name


def test_resolve_alert_metric_name_uses_display_name_result_name_or_blank():
    metrics = {9: SimpleNamespace(display_name="CPU 使用率", name="cpu_usage")}

    assert resolve_alert_metric_name({"type": "metric", "metric_id": 9}, metrics) == "CPU 使用率"
    assert resolve_alert_metric_name({"type": "metric", "metric_id": "9"}, metrics) == "CPU 使用率"
    assert (
        resolve_alert_metric_name(
            {"type": "metric", "metric_id": 9},
            {9: SimpleNamespace(display_name="", name="cpu_usage")},
        )
        == "cpu_usage"
    )
    assert resolve_alert_metric_name({"type": "formula", "result_name": "错误率"}, {}) == "错误率"
    assert resolve_alert_metric_name({"type": "multi", "result_name": "双高"}, {}) == "双高"
    assert resolve_alert_metric_name({"type": "pmq"}, {}) == ""
    assert resolve_alert_metric_name(None, {}) == ""
    assert resolve_alert_metric_name({"type": "metric", "metric_id": 3}, metrics) == ""


class _Rows:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def only(self, *_fields):
        return self

    def __iter__(self):
        return iter(self.rows)


def test_attach_metric_name_batches_policies_and_skips_missing_policy(monkeypatch):
    from apps.monitor.nats import monitor as nm

    policies = _Rows(
        [
            SimpleNamespace(id=3, query_condition={"type": "metric", "metric_id": 9}),
            SimpleNamespace(id=4, query_condition={"type": "formula", "result_name": "错误率"}),
        ]
    )
    metrics = _Rows([SimpleNamespace(id=9, display_name="CPU 使用率", name="cpu_usage")])
    monkeypatch.setattr(nm.MonitorPolicy, "objects", policies)
    monkeypatch.setattr(nm.Metric, "objects", metrics)

    items = [
        {"policy_id": 3},
        {"policy_id": 4},
        {"policy_id": 0},
        {"policy_id": None},
    ]
    _attach_active_alert_metric_names(items)

    assert policies.filters == [{"id__in": {3, 4}}]
    assert metrics.filters == [{"id__in": {9}}]
    assert [item["metric_name"] for item in items] == ["CPU 使用率", "错误率", "", ""]
