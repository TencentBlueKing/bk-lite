from types import SimpleNamespace
import pytest
from unittest.mock import patch

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorObject, MonitorInstance
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.metrics import Metrics
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.views.monitor_metrics import collect_vm_field_names
from apps.monitor.utils.display_fields import validate_display_fields
from apps.monitor.utils.display_fields_metrics import (
    display_field_key,
    extract_field_bindings,
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


def test_display_field_key_supports_field_columns():
    assert (
        display_field_key("主机（Telegraf）", "node_info", "collector_ip")
        == "field::主机（Telegraf）::node_info::collector_ip"
    )


def test_extract_metric_bindings_skips_field_columns():
    display_fields = [
        {"name": "CPU", "sort_order": 0, "metrics": [{"plugin": "P", "metric": "cpu"}]},
        {
            "name": "采集IP",
            "type": "field",
            "sort_order": 1,
            "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}],
        },
    ]

    assert extract_metric_bindings(display_fields) == [{"plugin": "P", "metric": "cpu"}]


def test_extract_field_bindings_keeps_field_and_dedups_by_triplet():
    display_fields = [
        {"name": "CPU", "sort_order": 0, "metrics": [{"plugin": "P", "metric": "cpu"}]},
        {
            "name": "采集IP",
            "type": "field",
            "sort_order": 1,
            "metrics": [
                {"plugin": "P", "metric": "node_info", "field": "collector_ip"},
                {"plugin": "P", "metric": "node_info", "field": "collector_ip"},
                {"plugin": "P", "metric": "node_info", "field": "model"},
            ],
        },
    ]

    assert extract_field_bindings(display_fields) == [
        {"plugin": "P", "metric": "node_info", "field": "collector_ip"},
        {"plugin": "P", "metric": "node_info", "field": "model"},
    ]


class _FakeMetricQuerySet:
    def values(self, *args):
        return [
            {"monitor_plugin__name": "P", "name": "cpu"},
            {"monitor_plugin__name": "P", "name": "node_info"},
        ]


class _FakeMetricManager:
    def filter(self, **kwargs):
        return _FakeMetricQuerySet()


def test_validate_display_fields_accepts_metric_and_field_columns(monkeypatch):
    monkeypatch.setattr("apps.monitor.utils.display_fields.Metric.objects", _FakeMetricManager())

    normalized = validate_display_fields(object(), [
        {"name": "CPU", "sort_order": 1, "metrics": [{"plugin": "P", "metric": "cpu"}]},
        {
            "name": "采集IP",
            "type": "field",
            "sort_order": 0,
            "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}],
        },
    ])

    assert normalized == [
        {
            "name": "采集IP",
            "type": "field",
            "sort_order": 0,
            "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}],
        },
        {"name": "CPU", "sort_order": 1, "metrics": [{"plugin": "P", "metric": "cpu"}]},
    ]


def test_validate_display_fields_rejects_field_column_without_field(monkeypatch):
    monkeypatch.setattr("apps.monitor.utils.display_fields.Metric.objects", _FakeMetricManager())

    with pytest.raises(BaseAppException, match="field"):
        validate_display_fields(object(), [
            {
                "name": "采集IP",
                "type": "field",
                "sort_order": 0,
                "metrics": [{"plugin": "P", "metric": "node_info"}],
            },
        ])


def test_query_metric_field_values_reads_vm_label(monkeypatch):
    class FakeVM:
        def query(self, query, step=None):
            assert query == 'node_info{instance_id=~"i1|i2"}'
            assert step == "20m"
            return {"data": {"result": [
                {"metric": {"instance_id": "i1", "collector_ip": "10.0.0.1"}, "value": [0, "1"]},
                {"metric": {"instance_id": "i2"}, "value": [0, "1"]},
            ]}}

    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", lambda: FakeVM())

    metric_obj = SimpleNamespace(
        name="node_info",
        query="node_info{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    result = MonitorObjectService._query_metric_field_values(
        metric_obj,
        [
            {"instance_id": "('i1',)"},
            {"instance_id": "('i2',)"},
        ],
        "collector_ip",
    )

    assert result == {"('i1',)": "10.0.0.1"}


def test_query_metric_field_values_matches_storage_instance_key(monkeypatch):
    class FakeVM:
        def query(self, query, step=None):
            assert query == 'node_info{instance_id=~"i1"}'
            assert step == "20m"
            return {"data": {"result": [
                {"metric": {"instance_id": "('i1',)", "collector_ip": "10.0.0.1"}, "value": [0, "1"]},
            ]}}

    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", lambda: FakeVM())

    metric_obj = SimpleNamespace(
        name="node_info",
        query="node_info{__$labels__}",
        instance_id_keys=["instance_id"],
    )
    result = MonitorObjectService._query_metric_field_values(
        metric_obj,
        [{"instance_id": "('i1',)"}],
        "collector_ip",
    )

    assert result == {"('i1',)": "10.0.0.1"}


def test_query_metric_field_values_uses_metric_query_when_storage_name_differs(monkeypatch):
    class FakeVM:
        def query(self, query, step=None):
            assert query == 'cpu_usage_system_total_gauge{instance_type="os", instance_id=~"i1"}'
            assert step == "20m"
            return {"data": {"result": [
                {
                    "metric": {
                        "instance_id": "i1",
                        "host": "remote-host",
                    },
                    "value": [0, "1"],
                },
            ]}}

    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", lambda: FakeVM())

    metric_obj = SimpleNamespace(
        name="cpu_usage_system_total",
        query='cpu_usage_system_total_gauge{instance_type="os", __$labels__}',
        instance_id_keys=["instance_id"],
    )
    result = MonitorObjectService._query_metric_field_values(
        metric_obj,
        [{"instance_id": "('i1',)"}],
        "host",
    )

    assert result == {"('i1',)": "remote-host"}


def test_query_metric_values_uses_display_lookback_step(monkeypatch):
    class FakeVM:
        def query(self, query, step=None):
            assert query == 'host_cpu_usage_percent_gauge{instance_type="os", instance_id=~"i1"}'
            assert step == "20m"
            return {"data": {"result": [
                {"metric": {"instance_id": "i1"}, "value": [0, "8.52"]},
            ]}}

    monkeypatch.setattr("apps.monitor.services.monitor_object.VictoriaMetricsAPI", lambda: FakeVM())

    metric_obj = SimpleNamespace(
        query='host_cpu_usage_percent_gauge{instance_type="os", __$labels__}',
        instance_id_keys=["instance_id"],
    )
    result = MonitorObjectService._query_metric_values(
        metric_obj,
        [{"instance_id": "('i1',)"}],
    )

    assert result == {"('i1',)": "8.52"}


def test_collect_vm_field_names_queries_vm_without_dimensions(monkeypatch):
    class FakeVM:
        def labels(self, match=None):
            assert match == '{__name__="node_info"}'
            return {"data": ["__name__", "collector_ip", "instance_id", "model"]}

        def query(self, query):
            raise AssertionError("labels API should provide field candidates")

    monkeypatch.setattr("apps.monitor.views.monitor_metrics.VictoriaMetricsAPI", lambda: FakeVM())

    metric_obj = SimpleNamespace(name="node_info", query="node_info{__$labels__}")

    assert collect_vm_field_names(metric_obj) == ["collector_ip", "instance_id", "model"]


def test_collect_vm_field_names_removes_trailing_placeholder_comma(monkeypatch):
    class FakeVM:
        def labels(self, match=None):
            return {"data": []}

        def query(self, query):
            assert query == "node_info{instance_type='host'}"
            return {"data": {"result": []}}

    monkeypatch.setattr("apps.monitor.views.monitor_metrics.VictoriaMetricsAPI", lambda: FakeVM())

    collect_vm_field_names(SimpleNamespace(query="node_info{instance_type='host',__$labels__}"))


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
