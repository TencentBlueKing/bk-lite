"""多指标试跑：逐条件说明、三种原因、缺数与零副作用。"""

import logging
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import (
    MonitorAlert,
    MonitorAlertMetricSnapshot,
    MonitorEvent,
    MonitorInstance,
    PolicyOrganization,
)
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.policy_dry_run import DRY_RUN_FAIL_TEMPLATE, PolicyDryRunService

pytestmark = pytest.mark.django_db

_TEAM = 7


@pytest.fixture
def metric_ctx():
    obj = MonitorObject.objects.create(
        name="MultiDryRunObj",
        level="base",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(name="MultiDryRunPlugin")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    cpu = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cpu_usage",
        display_name="CPU 使用率",
        query="cpu_usage{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="percent",
    )
    memory = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="mem_used",
        display_name="内存使用率",
        query="mem_used{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="percent",
    )
    uptime = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="uptime",
        display_name="系统运行时长",
        query="uptime{__$labels__}",
        instance_id_keys=["instance_id"],
        data_type="Number",
        unit="s",
    )
    return {"obj": obj, "cpu": cpu, "memory": memory, "uptime": uptime}


def _level(metric, ref, **overrides):
    data = {
        "ref": ref,
        "metric_id": metric.id,
        "filter": [],
        "group_algorithm": "avg",
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "metric_unit": "percent",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "role": "level",
        "threshold": [
            {"level": "critical", "method": ">", "value": 90},
            {"level": "warning", "method": ">", "value": 80},
        ],
    }
    data.update(overrides)
    return data


def _payload(metric_ctx, queries, **overrides):
    data = {
        "name": "cpu-and-memory",
        "alert_name": "${metric_name}",
        "monitor_object": metric_ctx["obj"].id,
        "query_condition": {
            "type": "multi",
            "result_name": "CPU 与内存双高",
            "combinator": "all",
            "queries": queries,
        },
        "source": {"type": "instance", "values": ["('h1',)"]},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "enable_alerts": ["threshold"],
        "trigger_count": 1,
        "recovery_condition": 1,
    }
    data.update(overrides)
    return data


def _vm(instance_id, *values):
    points = [[index + 1, str(value)] for index, value in enumerate(values)]
    return {
        "status": "success",
        "data": {"result": [{"metric": {"instance_id": instance_id}, "values": points}]},
    }


def _empty():
    return {"status": "success", "data": {"result": []}}


def _run(payload, mocker, *responses):
    def _fake(actor_context, object_id, require_operate=False):
        return MonitorInstance.objects.filter(monitor_object_id=object_id, is_deleted=False)

    mocker.patch(
        "apps.monitor.services.policy_dry_run.InstanceConfigService._get_authorized_monitor_instances",
        side_effect=_fake,
    )
    query = mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI.query_range",
        side_effect=list(responses),
    )
    actor = {
        "username": "tester",
        "is_superuser": False,
        "data_scope": SimpleNamespace(data_team_ids=[_TEAM]),
    }
    return query, PolicyDryRunService(payload, actor).run()


def _pair(metric_ctx):
    return [
        _level(metric_ctx["cpu"], "a"),
        _level(metric_ctx["memory"], "b"),
    ]


def test_dry_run_takes_lower_level_and_lists_each_condition(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    query, result = _run(
        _payload(metric_ctx, _pair(metric_ctx)),
        mocker,
        _vm("h1", 92),
        _vm("h1", 92),
        _vm("h1", 87.5),
    )
    assert query.call_count == 3
    item = result["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["reason"] == "各条件级别不同，取最低"
    assert item["compared_value"] == pytest.approx(92)
    assert item["matched_threshold"]["level"] == "warning"
    assert item["conditions"][0]["ref"] == "a"
    assert "expression" not in item["conditions"][0]
    assert item["conditions"][0]["metric_name"] == "CPU 使用率"
    assert item["conditions"][0]["value"] == pytest.approx(92)
    assert item["conditions"][0]["result_unit"] == "percent"
    assert item["conditions"][0]["hit_level"] == "critical"
    assert item["conditions"][0]["matched_threshold"]["level"] == "critical"
    assert "gate_passed" not in item["conditions"][0]
    assert item["conditions"][1]["metric_name"] == "内存使用率"
    assert item["conditions"][1]["value"] == pytest.approx(87.5)
    assert item["conditions"][1]["hit_level"] == "warning"


def test_dry_run_same_level_reason(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    _, result = _run(
        _payload(metric_ctx, _pair(metric_ctx)),
        mocker,
        _vm("h1", 93),
        _vm("h1", 93),
        _vm("h1", 96),
    )
    item = result["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["reason"] == "各条件级别一致"
    assert item["matched_threshold"]["level"] == "critical"


def test_dry_run_names_the_condition_that_misses_every_level(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    _, result = _run(
        _payload(metric_ctx, _pair(metric_ctx)),
        mocker,
        _vm("h1", 95),
        _vm("h1", 95),
        _vm("h1", 61),
    )
    item = result["items"][0]
    assert item["verdict"] == "ok"
    assert item["reason"] == "条件 b 未命中任何级别"
    assert item["conditions"][1]["hit_level"] is None


def test_dry_run_names_the_failing_gate(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    queries = _pair(metric_ctx) + [
        _level(
            metric_ctx["uptime"],
            "c",
            role="gate",
            metric_unit="s",
            calculation_unit="s",
            threshold_unit="s",
            threshold=[{"method": ">", "value": 600}],
        )
    ]
    _, result = _run(
        _payload(metric_ctx, queries),
        mocker,
        _vm("h1", 95),
        _vm("h1", 95),
        _vm("h1", 96),
        _vm("h1", 240),
    )
    item = result["items"][0]
    assert item["verdict"] == "ok"
    assert item["reason"] == "前置条件 c 未通过"
    assert item["conditions"][2]["gate_passed"] is False
    assert "hit_level" not in item["conditions"][2]
    assert item["compared_value"] == pytest.approx(95)


def test_dry_run_missing_condition_does_not_touch_active_alert(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    policy = MonitorPolicy.objects.create(
        monitor_object=metric_ctx["obj"],
        name="saved-multi",
        algorithm="avg_over_time",
        query_condition={"type": "multi", "result_name": "CPU 与内存双高", "queries": []},
        source={"type": "instance", "values": ["('h1',)"]},
        group_by=["instance_id"],
        last_run_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    PolicyOrganization.objects.create(policy=policy, organization=_TEAM)
    alert = MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        metric_instance_id="('h1',)",
        alert_type="alert",
        status="new",
        info_event_count=2,
    )
    MonitorEvent.objects.create(
        id="multi-dry-evt",
        alert=alert,
        policy_id=policy.id,
        monitor_instance_id="('h1',)",
        level="warning",
        content="seed",
    )
    event_manager = mocker.patch(
        "apps.monitor.tasks.services.policy_scan.event_alert_manager.EventAlertManager"
    )
    notifier = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier")
    detector_notifier = mocker.patch(
        "apps.monitor.tasks.services.policy_scan.alert_detector.AlertLifecycleNotifier"
    )
    before = (
        MonitorAlert.objects.count(),
        MonitorEvent.objects.count(),
        MonitorAlertMetricSnapshot.objects.count(),
        policy.last_run_time,
    )
    _, result = _run(
        _payload(metric_ctx, _pair(metric_ctx), id=policy.id),
        mocker,
        _vm("h1", 86),
        _vm("h1", 86),
        _empty(),
    )
    policy.refresh_from_db()
    alert.refresh_from_db()
    assert (
        MonitorAlert.objects.count(),
        MonitorEvent.objects.count(),
        MonitorAlertMetricSnapshot.objects.count(),
        policy.last_run_time,
    ) == before
    assert alert.status == "new"
    assert alert.info_event_count == 2
    event_manager.assert_not_called()
    notifier.assert_not_called()
    detector_notifier.assert_not_called()
    item = result["items"][0]
    assert item["verdict"] == "missing_condition_data"
    assert item["reason"] == "条件 b 无数据"
    assert item["conditions"][0]["value"] == pytest.approx(86)
    assert item["conditions"][1]["value"] is None


def test_dry_run_keeps_hit_count_copy_when_trigger_count_is_greater_than_one(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    _, result = _run(
        _payload(metric_ctx, _pair(metric_ctx), trigger_count=2),
        mocker,
        _vm("h1", 95),
        _vm("h1", 95, 95),
        _vm("h1", 96, 61),
    )
    item = result["items"][0]
    assert item["verdict"] == "ok"
    assert item["hit_count"] == 1
    assert item["reason"] == "条件 b 未命中任何级别；本轮命中 1/2，现网不会建告警"


def test_multi_vm_error_reuses_warning_template_without_response_body(metric_ctx, mocker, caplog):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])

    def _fake(actor_context, object_id, require_operate=False):
        return MonitorInstance.objects.filter(monitor_object_id=object_id, is_deleted=False)

    mocker.patch(
        "apps.monitor.services.policy_dry_run.InstanceConfigService._get_authorized_monitor_instances",
        side_effect=_fake,
    )
    sentinel = "vm-response-body-sentinel"
    mocker.patch(
        "apps.monitor.tasks.services.policy_scan.metric_query.VictoriaMetricsAPI.query_range",
        return_value={"status": "error", "error": sentinel, "data": {"result": [{"secret": sentinel}]}},
    )
    caplog.set_level(logging.DEBUG, logger="monitor")
    with pytest.raises(BaseAppException, match="预检失败"):
        PolicyDryRunService(
            _payload(metric_ctx, _pair(metric_ctx)),
            {"username": "tester", "is_superuser": True},
        ).run()
    records = [record for record in caplog.records if record.msg == DRY_RUN_FAIL_TEMPLATE]
    assert len(records) == 1
    formatted = records[0].getMessage()
    tb_text = "".join(traceback.format_exception(*records[0].exc_info))
    assert sentinel not in formatted
    assert sentinel not in tb_text
    assert "data" not in formatted


def _formula_queries(metric_ctx, gate_metric, gate_value):
    formula = {
        "ref": "a",
        "source": "formula",
        "metric_name": "错误率",
        "expression": "a1 / a2 * 100",
        "operands": [
            {
                "ref": "a1",
                "metric_id": metric_ctx["cpu"].id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
            {
                "ref": "a2",
                "metric_id": metric_ctx["memory"].id,
                "filter": [],
                "group_algorithm": "sum",
                "group_by": ["instance_id"],
            },
        ],
        "group_by": ["instance_id"],
        "algorithm": "avg_over_time",
        "metric_unit": "",
        "calculation_unit": "percent",
        "threshold_unit": "percent",
        "role": "level",
        "threshold": [
            {"level": "critical", "method": ">", "value": 20},
            {"level": "error", "method": ">", "value": 10},
            {"level": "warning", "method": ">", "value": 5},
        ],
    }
    gate = _level(
        gate_metric,
        "b",
        role="gate",
        metric_unit="s",
        calculation_unit="s",
        threshold_unit="s",
        threshold=[{"method": ">", "value": gate_value}],
    )
    return [formula, gate]


def test_dry_run_formula_condition_reports_result_name_and_expression(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    _, result = _run(
        _payload(metric_ctx, _formula_queries(metric_ctx, metric_ctx["uptime"], 100)),
        mocker,
        _vm("h1", 12),
        _vm("h1", 12),
        _vm("h1", 300),
    )
    item = result["items"][0]
    assert item["verdict"] == "would_trigger"
    assert item["matched_threshold"]["level"] == "error"
    assert item["conditions"][0]["metric_name"] == "错误率"
    assert item["conditions"][0]["expression"] == "a1 / a2 * 100"
    assert item["conditions"][0]["value"] == pytest.approx(12)
    assert "expression" not in item["conditions"][1]


def test_dry_run_formula_gate_failure_names_the_gate(metric_ctx, mocker):
    MonitorInstance.objects.create(id="('h1',)", name="主机1", monitor_object=metric_ctx["obj"])
    _, result = _run(
        _payload(metric_ctx, _formula_queries(metric_ctx, metric_ctx["uptime"], 100)),
        mocker,
        _vm("h1", 12),
        _vm("h1", 12),
        _vm("h1", 50),
    )
    item = result["items"][0]
    assert item["verdict"] == "ok"
    assert item["reason"] == "前置条件 b 未通过"
    assert item["conditions"][0]["metric_name"] == "错误率"
    assert item["conditions"][0]["expression"] == "a1 / a2 * 100"
