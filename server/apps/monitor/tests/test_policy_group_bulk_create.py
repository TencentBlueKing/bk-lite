import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_celery_beat.models import PeriodicTask, PeriodicTasks

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.constants.database import DatabaseConstants
from apps.monitor.models import Metric, MetricGroup, MonitorObject, MonitorPlugin, MonitorPolicy, PolicyGroup, PolicyTemplate
from apps.monitor.services.policy import PolicyService
from apps.monitor.services.policy_group import PolicyGroupService

pytestmark = pytest.mark.django_db


def _object(name):
    return MonitorObject.objects.create(name=name, level="base")


def _plugin(monitor_object, name):
    plugin = MonitorPlugin.objects.create(name=name, collector="Telegraf", collect_type="host")
    plugin.monitor_object.add(monitor_object)
    return plugin


def _metric(monitor_object, plugin, name="cpu_usage_total"):
    metric_group = MetricGroup.objects.create(monitor_object=monitor_object, monitor_plugin=plugin, name=f"os-{name}")
    return Metric.objects.create(
        monitor_object=monitor_object,
        monitor_plugin=plugin,
        name=name,
        metric_group=metric_group,
    )


def _templates(monitor_object, plugin, count, *, schedule=None, metric_name="cpu_usage_total", label="rule"):
    config = {"metric_name": metric_name, "threshold": [{"level": "warning", "value": 80, "method": ">="}]}
    if schedule is not None:
        config["schedule"] = schedule
    created = [
        PolicyTemplate.objects.create(
            key=f"builtin-{monitor_object.name}-{plugin.name}-{label}-{index}",
            scope_key="builtin",
            template_type=PolicyTemplate.TYPE_BUILTIN,
            organization=None,
            monitor_object=monitor_object,
            plugin=plugin,
            name=f"{plugin.name} {index}",
            config=config,
        )
        for index in range(count)
    ]
    return list(PolicyTemplate.objects.filter(id__in=[item.id for item in created]).order_by("id"))


def _create(monitor_object, templates):
    return PolicyGroupService.create_from_templates(
        organization=1,
        monitor_object=monitor_object,
        name=f"{monitor_object.name}默认告警",
        templates=templates,
        operator="system",
        origin="system",
    )


def _query_count(monitor_object, templates):
    with CaptureQueriesContext(connection) as captured:
        group = _create(monitor_object, templates)
    return len(captured), group


def test_many_templates_stay_under_a_fixed_query_budget():
    small_object = _object("BulkSmall")
    small_plugin = _plugin(small_object, "BulkSmallPlugin")
    _metric(small_object, small_plugin)
    large_object = _object("BulkLarge")
    large_plugin = _plugin(large_object, "BulkLargePlugin")
    _metric(large_object, large_plugin)

    small_queries, small_group = _query_count(small_object, _templates(small_object, small_plugin, 8))
    large_queries, large_group = _query_count(large_object, _templates(large_object, large_plugin, 30))

    assert small_group.rules.count() == 8
    assert large_group.rules.count() == 30
    assert small_queries < 40, (small_queries, large_queries)
    assert large_queries < 40, (small_queries, large_queries)


def test_each_template_gets_one_disabled_scan_task():
    monitor_object = _object("BulkBatch")
    plugin = _plugin(monitor_object, "BulkBatchPlugin")
    _metric(monitor_object, plugin)
    count = DatabaseConstants.BULK_CREATE_BATCH_SIZE + 1
    before_change = PeriodicTasks.last_change()

    group = _create(monitor_object, _templates(monitor_object, plugin, count))

    rules = list(group.rules.select_related("policy"))
    assert len(rules) == count
    policy_ids = [rule.policy_id for rule in rules]
    tasks = list(PeriodicTask.objects.filter(name__in=[f"scan_policy_task_{policy_id}" for policy_id in policy_ids]))
    assert len(tasks) == count
    assert {task.enabled for task in tasks} == {False}
    assert sorted(json.loads(task.args) for task in tasks) == sorted([policy_id] for policy_id in policy_ids)
    assert {task.task for task in tasks} == {"apps.monitor.tasks.monitor_policy.scan_policy_task"}
    assert len({task.crontab_id for task in tasks}) == 1
    after_change = PeriodicTasks.last_change()
    assert after_change is not None
    assert before_change is None or after_change >= before_change
    policy = rules[0].policy
    assert policy.enable is True
    assert policy.source == {"type": "instance", "values": []}
    assert policy.schedule == {"type": "min", "value": 5}
    assert list(policy.policyorganization_set.values_list("organization", flat=True)) == [1]
    assert "metric_id" in policy.query_condition


def test_distinct_schedules_keep_distinct_crontabs():
    monitor_object = _object("BulkSchedule")
    plugin = _plugin(monitor_object, "BulkSchedulePlugin")
    _metric(monitor_object, plugin)
    default_templates = _templates(monitor_object, plugin, 2, label="default")
    hourly = _templates(monitor_object, plugin, 1, schedule={"type": "hour", "value": 2}, label="hourly")

    group = _create(monitor_object, default_templates + hourly)

    tasks = {
        task.name: task
        for task in PeriodicTask.objects.select_related("crontab").filter(
            name__in=[f"scan_policy_task_{policy_id}" for policy_id in group.rules.values_list("policy_id", flat=True)]
        )
    }
    default_tasks = [tasks[f"scan_policy_task_{rule.policy_id}"] for rule in group.rules.filter(source_template__in=default_templates)]
    hourly_task = tasks[f"scan_policy_task_{group.rules.get(source_template=hourly[0]).policy_id}"]
    assert default_tasks[0].crontab_id == default_tasks[1].crontab_id
    assert default_tasks[0].crontab.minute == "*/5"
    assert hourly_task.crontab_id != default_tasks[0].crontab_id
    assert hourly_task.crontab.minute == "0"
    assert hourly_task.crontab.hour == "*/2"
    assert hourly_task.enabled is False


def test_unknown_metric_rolls_back_the_group():
    monitor_object = _object("BulkMissing")
    plugin = _plugin(monitor_object, "BulkMissingPlugin")
    templates = _templates(monitor_object, plugin, 2, metric_name="missing_metric")

    with pytest.raises(BaseAppException, match="指标不存在"):
        _create(monitor_object, templates)

    assert not PolicyGroup.objects.filter(monitor_object=monitor_object).exists()
    assert not MonitorPolicy.objects.filter(monitor_object=monitor_object).exists()
    assert PeriodicTask.objects.count() == 0


def test_cached_metric_lookup_matches_the_query_lookup():
    monitor_object = _object("BulkDup")
    plugin = _plugin(monitor_object, "BulkDupPlugin")
    metric_group = MetricGroup.objects.create(monitor_object=monitor_object, name="loose")
    Metric.objects.create(monitor_object=monitor_object, monitor_plugin=None, name="cpu_usage_total", metric_group=metric_group)
    Metric.objects.create(monitor_object=monitor_object, monitor_plugin=None, name="cpu_usage_total", metric_group=metric_group)

    with PolicyService.cached_runtime_metrics(monitor_object):
        with pytest.raises(BaseAppException, match="指标不唯一"):
            PolicyService._resolve_runtime_metric(monitor_object, "cpu_usage_total")
    with pytest.raises(BaseAppException, match="指标不唯一"):
        PolicyService._resolve_runtime_metric(monitor_object, "cpu_usage_total")

    _metric(monitor_object, plugin, "disk_used")
    with PolicyService.cached_runtime_metrics(monitor_object):
        found = PolicyService._resolve_runtime_metric(monitor_object, "disk_used", plugin=plugin)
    assert found.name == "disk_used"
    assert found.monitor_plugin_id == plugin.id
