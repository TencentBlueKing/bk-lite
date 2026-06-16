import pytest
from unittest.mock import patch

from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.metrics import Metrics
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.utils.display_fields_metrics import (
    display_field_key,
    extract_metric_bindings,
    extract_metric_names,
)


def test_extract_metric_names_union_preserves_order_and_dedups():
    display_fields = [
        {"name": "CPU", "sort_order": 0, "metrics": [
            {"plugin": "A", "metric": "cpu"}, {"plugin": "B", "metric": "cpu_b"}]},
        {"name": "MEM", "sort_order": 1, "metrics": [
            {"plugin": "A", "metric": "mem"}, {"plugin": "A", "metric": "cpu"}]},
    ]
    assert extract_metric_names(display_fields) == ["cpu", "cpu_b", "mem"]


def test_extract_metric_names_empty():
    assert extract_metric_names([]) == []
    assert extract_metric_names(None) == []


def test_extract_metric_bindings_keeps_plugin_and_dedups_by_pair():
    # 同名指标分属不同插件应各保留一条;完全相同的 (plugin, metric) 去重
    display_fields = [
        {"name": "温度", "sort_order": 0, "metrics": [
            {"plugin": "Switch Huawei SNMP", "metric": "device_temperature_celsius"},
            {"plugin": "Switch Cisco SNMP", "metric": "device_temperature_celsius"}]},
        {"name": "CPU", "sort_order": 1, "metrics": [
            {"plugin": "Switch Huawei SNMP", "metric": "device_temperature_celsius"},  # dup pair
            {"plugin": "Switch Huawei SNMP", "metric": "device_cpu_usage"}]},
    ]
    assert extract_metric_bindings(display_fields) == [
        {"plugin": "Switch Huawei SNMP", "metric": "device_temperature_celsius"},
        {"plugin": "Switch Cisco SNMP", "metric": "device_temperature_celsius"},
        {"plugin": "Switch Huawei SNMP", "metric": "device_cpu_usage"},
    ]


def test_display_field_key_composite_and_legacy():
    assert display_field_key("Switch Huawei SNMP", "device_temperature_celsius") == \
        "Switch Huawei SNMP::device_temperature_celsius"
    # 无插件(遗留)退化为裸指标名
    assert display_field_key("", "device_temperature_celsius") == "device_temperature_celsius"


def _mk_metric(obj, plugin, name):
    group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name=f"G-{plugin.name}")
    return Metric.objects.create(
        monitor_object=obj, monitor_plugin=plugin, metric_group=group, name=name,
        display_name=name, query=f"{name}{{__$labels__}}", unit="percent",
        data_type="Number", instance_id_keys=["instance_id"],
    )


def _mk_collect_config(cfg_id, instance, plugin):
    return CollectConfig.objects.create(
        id=cfg_id, monitor_instance=instance, monitor_plugin=plugin,
        collector="Telegraf", collect_type="snmp", config_type="child", file_type="toml",
    )


@pytest.mark.django_db
@patch("apps.monitor.services.monitor_object.VictoriaMetricsAPI")
def test_get_monitor_instance_queries_display_fields_metrics(mock_vm):
    # 实例有 CollectConfig 归属插件 P → 该绑定取数会跑,且回填用复合 key
    mock_vm.return_value.query.return_value = {"data": {"result": [
        {"metric": {"instance_id": "i1"}, "value": [0, "42"]},
    ]}}
    obj = MonitorObject.objects.create(
        name="UTHostU", level="base",
        default_metric="any({instance_type='UTHostU'}) by (instance_id)",
        instance_id_keys=["instance_id"], supplementary_indicators=[],
        display_fields=[{"name": "CPU", "sort_order": 0,
                         "metrics": [{"plugin": "P", "metric": "cpu_usage_total"}]}],
    )
    plugin = MonitorPlugin.objects.create(name="P")
    _mk_metric(obj, plugin, "cpu_usage_total")
    inst = MonitorInstance.objects.create(id="('i1',)", name="i1", monitor_object=obj)
    _mk_collect_config("cc-i1-P", inst, plugin)

    res = MonitorObjectService.get_monitor_instance(
        obj.id, page=1, page_size=10, name=None,
        qs=MonitorInstance.objects.all(), add_metrics=True,
    )
    queried = [c.args[0] for c in mock_vm.return_value.query.call_args_list]
    assert any("cpu_usage_total" in q for q in queried)
    assert res["count"] == 1
    # 复合 key 回填,而非裸指标名
    assert res["results"][0]["P::cpu_usage_total"] == "42"
    assert "cpu_usage_total" not in res["results"][0]

    # convert 须用同一复合 key 包成 {value, unit}(回归:类内自引用曾误用别名 MetricsService)
    Metrics.convert_instance_list_metrics(obj.id, res["results"])
    converted = res["results"][0]["P::cpu_usage_total"]
    assert isinstance(converted, dict) and float(converted["value"]) == 42.0


@pytest.mark.django_db
@patch("apps.monitor.services.monitor_object.VictoriaMetricsAPI")
def test_display_fields_isolated_by_plugin(mock_vm):
    # 同名指标(温度)绑了 Huawei + Cisco 两个插件;实例只归属 Huawei →
    # 只在 Huawei 复合 key 上有值,Cisco 复合 key 不应出现(别的品牌不串)。
    mock_vm.return_value.query.return_value = {"data": {"result": [
        {"metric": {"instance_id": "hw1"}, "value": [0, "55"]},
    ]}}
    obj = MonitorObject.objects.create(
        name="UTSwitchU", level="base",
        default_metric="any({instance_type='UTSwitchU'}) by (instance_id)",
        instance_id_keys=["instance_id"], supplementary_indicators=[],
        display_fields=[{"name": "温度", "sort_order": 0, "metrics": [
            {"plugin": "Switch Huawei SNMP", "metric": "device_temperature_celsius"},
            {"plugin": "Switch Cisco SNMP", "metric": "device_temperature_celsius"}]}],
    )
    huawei = MonitorPlugin.objects.create(name="Switch Huawei SNMP")
    cisco = MonitorPlugin.objects.create(name="Switch Cisco SNMP")
    _mk_metric(obj, huawei, "device_temperature_celsius")
    _mk_metric(obj, cisco, "device_temperature_celsius")
    hw = MonitorInstance.objects.create(id="('hw1',)", name="huawei-switch", monitor_object=obj)
    _mk_collect_config("cc-hw1", hw, huawei)
    # 一台没有任何 CollectConfig 的实例(演示数据形态)
    MonitorInstance.objects.create(id="('mock1',)", name="netgear-switch", monitor_object=obj)

    res = MonitorObjectService.get_monitor_instance(
        obj.id, page=1, page_size=10, name=None,
        qs=MonitorInstance.objects.all(), add_metrics=True,
    )
    rows = {r["instance_id"]: r for r in res["results"]}
    hw_row = rows["('hw1',)"]
    mock_row = rows["('mock1',)"]
    hw_key = "Switch Huawei SNMP::device_temperature_celsius"
    cisco_key = "Switch Cisco SNMP::device_temperature_celsius"
    # Huawei 实例:只在 Huawei key 有值,不串到 Cisco key
    assert hw_row.get(hw_key) == "55"
    assert cisco_key not in hw_row
    # 无 CollectConfig 的实例:两个插件 key 都不出现(显示 --)
    assert hw_key not in mock_row
    assert cisco_key not in mock_row


@pytest.mark.django_db
@patch("apps.monitor.services.monitor_object.VictoriaMetricsAPI")
def test_display_fields_batches_one_query_per_metric(mock_vm):
    # 同名指标绑了华为+思科两个插件、两台实例各归属其一:应只发 1 次该指标的 VM 查询(批量),
    # 且各自只在自己品牌的复合 key 上拿到值(隔离)。
    mock_vm.return_value.query.return_value = {"data": {"result": [
        {"metric": {"instance_id": "hw1"}, "value": [0, "55"]},
        {"metric": {"instance_id": "ci1"}, "value": [0, "60"]},
    ]}}
    obj = MonitorObject.objects.create(
        name="UTSwitchB", level="base",
        default_metric="any({instance_type='UTSwitchB'}) by (instance_id)",
        instance_id_keys=["instance_id"], supplementary_indicators=[],
        display_fields=[{"name": "温度", "sort_order": 0, "metrics": [
            {"plugin": "Switch Huawei SNMP", "metric": "device_temperature_celsius"},
            {"plugin": "Switch Cisco SNMP", "metric": "device_temperature_celsius"}]}],
    )
    huawei = MonitorPlugin.objects.create(name="Switch Huawei SNMP")
    cisco = MonitorPlugin.objects.create(name="Switch Cisco SNMP")
    _mk_metric(obj, huawei, "device_temperature_celsius")
    _mk_metric(obj, cisco, "device_temperature_celsius")
    hw = MonitorInstance.objects.create(id="('hw1',)", name="hw", monitor_object=obj)
    ci = MonitorInstance.objects.create(id="('ci1',)", name="ci", monitor_object=obj)
    _mk_collect_config("cc-hw1b", hw, huawei)
    _mk_collect_config("cc-ci1b", ci, cisco)

    res = MonitorObjectService.get_monitor_instance(
        obj.id, page=1, page_size=10, name=None,
        qs=MonitorInstance.objects.all(), add_metrics=True,
    )
    queried = [c.args[0] for c in mock_vm.return_value.query.call_args_list]
    # 两个品牌同名同 query → 合并成一次查询(而非每品牌一次)
    temp_queries = [q for q in queried if "device_temperature_celsius" in q]
    assert len(temp_queries) == 1, f"expected 1 batched query, got {len(temp_queries)}: {temp_queries}"
    rows = {r["instance_id"]: r for r in res["results"]}
    hw_key = "Switch Huawei SNMP::device_temperature_celsius"
    cisco_key = "Switch Cisco SNMP::device_temperature_celsius"
    assert rows["('hw1',)"].get(hw_key) == "55" and cisco_key not in rows["('hw1',)"]
    assert rows["('ci1',)"].get(cisco_key) == "60" and hw_key not in rows["('ci1',)"]
