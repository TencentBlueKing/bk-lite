"""展示列回填:派生/上报型实例(无 CollectConfig)也应命中其上报插件的列值。

回归场景:K8s 集群/Pod/Node 经集群内采集器上报,bk-lite 侧没有 CollectConfig。
修复前 _fill_display_metrics 只按 CollectConfig 判定插件归属,这些实例的插件绑定列
一律显示 --;修复后按对象各插件 status_query 反查上报实例,使其命中所属插件并回填列值。
"""

import pytest

from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject, MonitorPlugin
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.services import monitor_object as mo
from apps.monitor.services.monitor_object import MonitorObjectService


def _build_k8s_like_object():
    obj = MonitorObject.objects.create(
        name="K8sClusterTest",
        display_name="K8sClusterTest",
        instance_id_keys=["instance_id"],
    )
    plugin = MonitorPlugin.objects.create(
        name="K8STEST",
        display_name="K8STEST",
        template_id="k8stest",
        template_type="k8s",
        collector="K8S",
        collect_type="k8s",
        status_query="any({instance_type='k8stest'}) by (instance_id)",
        is_pre=False,
    )
    plugin.monitor_object.add(obj)
    group = MetricGroup.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        name="Quantity",
    )
    metric = Metric.objects.create(
        monitor_object=obj,
        monitor_plugin=plugin,
        metric_group=group,
        name="cluster_pod_count",
        display_name="Pod Count",
        query='round(count(some_kube_pod_info{instance_type="k8stest",__$labels__}) by (instance_id))',
        instance_id_keys=["instance_id"],
    )
    return obj, plugin, metric


@pytest.mark.django_db
def test_fill_display_metrics_reported_instance_without_collectconfig(monkeypatch):
    obj, plugin, metric = _build_k8s_like_object()

    class StubVictoriaMetricsAPI:
        def query(self, query, **kwargs):
            # 插件 status_query:上报实例 instance_id=mactest
            if "instance_type='k8stest'" in query and "count(" not in query:
                return {"data": {"result": [{"metric": {"instance_id": "mactest"}, "value": [0, "1"]}]}}
            # 展示指标 query:mactest 集群 pod 数 = 7
            if "some_kube_pod_info" in query:
                return {"data": {"result": [{"metric": {"instance_id": "mactest"}, "value": [0, "7"]}]}}
            return {"data": {"result": []}}

    monkeypatch.setattr(mo, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    # 派生实例:无 CollectConfig
    result = [{"instance_id": "('mactest',)", "instance_name": "mactest"}]
    obj_metric_map = {
        "display_fields": [
            {"name": "Pod Count", "metrics": [{"plugin": "K8STEST", "metric": "cluster_pod_count"}]}
        ],
        "supplementary_indicators": [],
    }

    MonitorObjectService._fill_display_metrics(obj.id, obj_metric_map, result)

    # 修复前:无 CollectConfig → 不命中插件 → 列值缺失(--);修复后:按上报插件命中 → 回填 7
    assert result[0].get("K8STEST::cluster_pod_count") == "7"


@pytest.mark.django_db
def test_fill_display_metrics_skips_status_query_when_all_collectconfig_covered(monkeypatch):
    """常规对象:实例全部有 CollectConfig 覆盖时,不应再为反查上报插件发 status_query。

    回归:_fill_display_metrics 被实例列表热路径调用。若对每个 status_query 插件无条件发 VM
    查询,Switch(65)/Firewall(28)/Router(26) 等对象会在每次分页加载串行发数十次 VM 往返。
    仅派生(无 CollectConfig)实例才需反查上报插件。
    """
    obj, plugin, metric = _build_k8s_like_object()
    instance = MonitorInstance.objects.create(id="('host1',)", name="host1", monitor_object=obj)
    CollectConfig.objects.create(
        id="host1-cfg",
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector="K8S",
        collect_type="k8s",
        config_type="k8stest",
        file_type="toml",
        is_child=True,
    )

    status_calls = []

    class StubVictoriaMetricsAPI:
        def query(self, query, **kwargs):
            if "instance_type='k8stest'" in query and "count(" not in query:
                status_calls.append(query)  # 不应被调用
                return {"data": {"result": []}}
            if "some_kube_pod_info" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host1"}, "value": [0, "5"]}]}}
            return {"data": {"result": []}}

    monkeypatch.setattr(mo, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = [{"instance_id": "('host1',)", "instance_name": "host1"}]
    obj_metric_map = {
        "display_fields": [
            {"name": "Pod Count", "metrics": [{"plugin": "K8STEST", "metric": "cluster_pod_count"}]}
        ],
        "supplementary_indicators": [],
    }

    MonitorObjectService._fill_display_metrics(obj.id, obj_metric_map, result)

    assert status_calls == [], "实例已被 CollectConfig 覆盖,不应再发插件 status_query 反查"
    # 经 CollectConfig 命中插件,展示列仍正常回填
    assert result[0].get("K8STEST::cluster_pod_count") == "5"
