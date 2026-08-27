from types import SimpleNamespace

from apps.operation_analysis.services.application3d.metric_fields import (
    present_alarm_metric_fields,
    resolve_policy_metric_display_name,
    resolve_policy_metric_id,
)
from apps.operation_analysis.services.application3d.presenters import present_alarm_list_item


def test_resolve_metric_never_uses_alert_name():
    policy = SimpleNamespace(
        alert_name="[demo] CPU 持续超过 95%",
        query_condition={"type": "metric", "metric_id": 999999},
    )
    assert resolve_policy_metric_display_name(policy, metrics_by_id={}) is None
    assert resolve_policy_metric_id(policy) == "999999"


def test_resolve_formula_metric_uses_result_name():
    policy = SimpleNamespace(
        alert_name="should-not-appear",
        query_condition={"type": "formula", "result_name": "错误率"},
    )
    assert resolve_policy_metric_display_name(policy) == "错误率"
    assert resolve_policy_metric_id(policy) is None


def test_resolve_metric_display_name_from_metric_model():
    metric = SimpleNamespace(id=9, display_name="CPU 使用率", name="cpu_usage")
    policy = SimpleNamespace(
        alert_name="告警名称模板",
        query_condition={"type": "metric", "metric_id": 9},
    )
    assert resolve_policy_metric_display_name(policy, metrics_by_id={9: metric}) == "CPU 使用率"


def test_present_alarm_metric_fields_uses_definition_id_not_instance_id():
    alert = SimpleNamespace(value=96.5, metric_instance_id="instance-xyz")
    policy = SimpleNamespace(
        alert_name="告警名称模板",
        query_condition={"type": "metric", "metric_id": 9},
    )
    metric = SimpleNamespace(id=9, display_name="CPU 使用率", name="cpu_usage")
    fields = present_alarm_metric_fields(
        alert,
        policy,
        unit="%",
        metrics_by_id={9: metric},
    )
    assert fields == {
        "id": "9",
        "name": "CPU 使用率",
        "value": "96.5",
        "unit": "%",
    }


def test_list_item_metric_name_ignores_alert_name():
    alert = SimpleNamespace(
        id=1,
        content="内容",
        alert_type="alert",
        level="critical",
        start_event_time=None,
        end_event_time=None,
    )
    item = present_alarm_list_item(
        alert,
        host={"inst_uuid": "host-1", "inst_name": "host-1"},
        policy=SimpleNamespace(
            alert_name="告警名称模板",
            name="策略名",
            query_condition={"type": "formula", "result_name": "错误率"},
        ),
    )
    assert item["metricName"] == "错误率"
    assert item["alertType"] == "alert"
    assert item["policyName"] == "策略名"


def test_list_item_no_data_keeps_alert_type_and_severity():
    alert = SimpleNamespace(
        id=7,
        content="主机无数据",
        alert_type="no_data",
        level="critical",
        start_event_time=None,
        end_event_time=None,
    )
    item = present_alarm_list_item(
        alert,
        host={"inst_uuid": "host-1", "inst_name": "host-1"},
        policy=SimpleNamespace(alert_name="cpu", name="CPU", query_condition={}),
    )
    assert item["isNoData"] is True
    assert item["alertType"] == "no_data"
    assert item["severity"]["id"] == "critical"
    assert item["metricName"] is None
