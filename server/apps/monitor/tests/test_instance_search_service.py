"""InstanceSearch (monitor_instance 服务) 静态方法规格测试。

VictoriaMetricsAPI mock；DB 用真实模型。
"""

import pytest

from apps.monitor.constants.plugin import PluginConstants as P
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
from apps.monitor.services.monitor_instance import InstanceSearch

pytestmark = pytest.mark.django_db


class TestGetParentInstanceIds:
    def test_extracts_instance_ids(self, mocker):
        vm = mocker.patch("apps.monitor.services.monitor_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [
            {"metric": {"instance_id": "h1"}},
            {"metric": {"instance_id": "h2"}},
        ]}}
        assert InstanceSearch.get_parent_instance_ids("any()") == ["h1", "h2"]


class TestGetParentInstanceList:
    def test_lists_parent_instances(self):
        parent = MonitorObject.objects.create(name="ISParent", level="base")
        child = MonitorObject.objects.create(name="ISChild", level="derivative", parent=parent)
        MonitorInstance.objects.create(id="('p1',)", name="父1", monitor_object=parent)
        data = InstanceSearch.get_parent_instance_list(child.id)
        assert data == [{"id": "p1", "name": "父1"}]


class TestGetQueryParamsEnum:
    def test_node_enum(self, mocker):
        vm = mocker.patch("apps.monitor.services.monitor_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [
            {"metric": {"instance_id": "k8s-prod"}},
        ]}}
        obj = MonitorObject.objects.create(name="Node", level="base")
        MonitorInstance.objects.create(id="('k8s-prod',)", name="生产集群", monitor_object=obj)
        out = InstanceSearch.get_query_params_enum("Node")
        assert out["cluster"][0]["id"] == "k8s-prod"
        assert out["cluster"][0]["name"] == "生产集群"

    def test_pod_enum(self, mocker):
        vm = mocker.patch("apps.monitor.services.monitor_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [
            {"metric": {"instance_id": "k8s-prod", "node": "worker-1"}},
        ]}}
        out = InstanceSearch.get_query_params_enum("Pod")
        assert out["cluster"][0]["id"] == "k8s-prod"
        assert out["node"][0]["id"] == "worker-1"

    def test_cvm_delegates(self, mocker):
        vm = mocker.patch("apps.monitor.services.monitor_instance.VictoriaMetricsAPI")
        vm.return_value.query.return_value = {"data": {"result": [
            {"metric": {"instance_id": "cvm-1"}},
        ]}}
        out = InstanceSearch.get_query_params_enum("CVM")
        assert out == ["cvm-1"]


class TestDedupeInstancePlugins:
    def test_keeps_distinct_templates(self):
        plugins = [
            {"collector": "Telegraf", "collect_type": "snmp", "name": "a",
             "collect_mode": P.COLLECT_MODE_AUTO, "status": P.STATUS_NORMAL},
            {"collector": "Exporter", "collect_type": "http", "name": "b",
             "collect_mode": P.COLLECT_MODE_AUTO, "status": P.STATUS_NORMAL},
        ]
        out = InstanceSearch._dedupe_instance_plugins(plugins)
        assert len(out) == 2

    def test_folds_duplicates_keeping_best_status(self):
        plugins = [
            {"collector": "Telegraf", "collect_type": "snmp", "name": "a",
             "collect_mode": P.COLLECT_MODE_MANUAL, "status": P.STATUS_NORMAL},
            {"collector": "Telegraf", "collect_type": "snmp", "name": "a",
             "collect_mode": P.COLLECT_MODE_AUTO, "status": P.STATUS_NORMAL},
        ]
        out = InstanceSearch._dedupe_instance_plugins(plugins)
        assert len(out) == 1
        # 自动正常优先级高于手动正常
        assert out[0]["collect_mode"] == P.COLLECT_MODE_AUTO


class TestEscapePromqlLabelValue:
    def test_escapes(self):
        assert InstanceSearch._escape_promql_label_value('a"b\\c') == 'a\\"b\\\\c'
