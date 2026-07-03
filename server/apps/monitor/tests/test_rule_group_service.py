"""RuleGrouping 规格测试。

聚焦分组规则 → 实例组织关联的构建逻辑。VictoriaMetricsAPI mock。
"""

import pytest

from apps.monitor.models import Metric
from apps.monitor.models.monitor_metrics import MetricGroup
from apps.monitor.models.monitor_object import (
    MonitorObject,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObjectOrganizationRule,
)
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.tasks.services.rule_group import RuleGrouping

pytestmark = pytest.mark.django_db


def _make_metric(obj):
    plugin = MonitorPlugin.objects.create(name=f"P-{obj.name}")
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
    return Metric.objects.create(
        monitor_object=obj, monitor_plugin=plugin, metric_group=group,
        name="m", query="m{__$labels__}", instance_id_keys=["instance_id"],
    )


def _make_obj(name="RGHost"):
    return MonitorObject.objects.create(
        name=name, level="base",
        default_metric="any({}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )


class TestGetQuery:
    def test_metric_not_found_returns_none(self):
        assert RuleGrouping.get_query({"metric_id": 999999, "filter": []}) is None

    def test_substitutes_filter(self):
        obj = _make_obj()
        metric = _make_metric(obj)
        query = RuleGrouping.get_query({
            "metric_id": metric.id,
            "filter": [{"name": "instance_id", "method": "=", "value": "h1"}],
        })
        assert query == 'm{instance_id="h1"}'

    def test_empty_filter(self):
        obj = _make_obj()
        metric = _make_metric(obj)
        assert RuleGrouping.get_query({"metric_id": metric.id, "filter": []}) == "m{}"


class TestGetAssoByConditionRule:
    def test_builds_asso_for_known_instances(self, mocker):
        obj = _make_obj()
        metric = _make_metric(obj)
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        rule = MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj, name="r1", organizations=[7, 8],
            rule={"metric_id": metric.id, "filter": []},
        )
        vm = mocker.patch("apps.monitor.tasks.services.rule_group.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [
            {"metric": {"instance_id": "h1"}},
            {"metric": {"instance_id": "unknown"}},  # 不在库中 → 跳过
        ]}}
        asso = RuleGrouping.get_asso_by_condition_rule(rule)
        assert set(asso) == {("('h1',)", 7), ("('h1',)", 8)}


class TestGetAssoBySelectRule:
    def test_filters_deleted_instances(self):
        from types import SimpleNamespace

        obj = _make_obj()
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        # select 类型规则用 grouping_rules.instances 指定实例；库中缺失的实例被剔除
        rule = SimpleNamespace(
            id=1, monitor_object_id=obj.id, organizations=[9],
            grouping_rules={"instances": ["('h1',)", "('missing',)"]},
        )
        asso = RuleGrouping().get_asso_by_select_rule(rule)
        assert asso == [("('h1',)", 9)]


class TestUpdateGrouping:
    def test_creates_missing_org_relations(self, mocker):
        obj = _make_obj()
        metric = _make_metric(obj)
        MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorObjectOrganizationRule.objects.create(
            monitor_object=obj, name="r3", organizations=[11],
            rule={"metric_id": metric.id, "filter": []},
        )
        vm = mocker.patch("apps.monitor.tasks.services.rule_group.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [
            {"metric": {"instance_id": "h1"}},
        ]}}
        RuleGrouping().update_grouping()
        assert MonitorInstanceOrganization.objects.filter(
            monitor_instance_id="('h1',)", organization=11
        ).exists()
